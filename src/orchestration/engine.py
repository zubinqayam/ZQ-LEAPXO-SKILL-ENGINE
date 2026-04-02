"""LEAPXO Skill Engine v2.1 — Main Orchestration Engine.

Full execution flow:
    User Input
       ↓ Prompt Firewall (LLM-based)
       ↓ Intent Detection (L1)
       ↓ Skill Selection (+ cache lookup)
       ↓ Policy Check
       ↓ Signature Verification
       ↓ Token Prediction
       ↓ L2 Instruction Load
       ↓ L3 Sandboxed Execution
       ↓ Validation
       ↓ Response / Escalation

Circuit Breaker tiers:
    L1 Failure  → retry with different skill
    L2 Failure  → prune + reload
    L3 Failure  → isolate skill
    System      → partial degrade (NOT full stop)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.cache.semantic_cache import SemanticCache
from src.core.exceptions import (
    CircuitBreakerOpenError,
    IntentLoopError,
    PolicyViolationError,
    PromptFirewallError,
    SandboxExecutionError,
    SignatureVerificationError,
    SkillEngineError,
    SkillNotFoundError,
    TokenBudgetExceededError,
)
from src.execution.circuit_breaker import CircuitBreakerRegistry, get_registry
from src.execution.l1_discovery import L1Discovery
from src.execution.l2_instruction import L2InstructionLoader
from src.execution.l3_executor import BaseL3Executor, ExecutionResult, InProcessL3Executor
from src.registry.skill_registry import SkillRegistry
from src.security.policy_engine import PolicyEngine
from src.security.prompt_firewall import PromptFirewall


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------

@dataclass
class EngineRequest:
    user_input: str
    region_code: str = "GL"
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    context_tokens_used: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineResponse:
    request_id: str
    skill_id: Optional[str]
    success: bool
    output: Any
    latency_ms: float
    was_cached: bool = False
    token_usage: int = 0
    requires_review: bool = False
    error: Optional[str] = None
    circuit_tier: Optional[str] = None


# ---------------------------------------------------------------------------
# Orchestration Engine
# ---------------------------------------------------------------------------

class OrchestrationEngine:
    """The central execution orchestrator for LEAPXO Skill Engine v2.1.

    All components are injected for testability.  Sensible defaults are
    provided for local/dev use.
    """

    def __init__(
        self,
        l1: Optional[L1Discovery] = None,
        l2: Optional[L2InstructionLoader] = None,
        l3: Optional[BaseL3Executor] = None,
        registry: Optional[SkillRegistry] = None,
        firewall: Optional[PromptFirewall] = None,
        policy_engine: Optional[PolicyEngine] = None,
        cache: Optional[SemanticCache] = None,
        breakers: Optional[CircuitBreakerRegistry] = None,
        *,
        context_window: int = 8192,
        embedding_fn: Optional[Callable[[str], list[float]]] = None,
    ) -> None:
        self._l1 = l1 or L1Discovery()
        self._l2 = l2 or L2InstructionLoader(context_window=context_window)
        self._l3 = l3 or InProcessL3Executor()
        self._registry = registry or SkillRegistry()
        self._firewall = firewall or PromptFirewall(strict_mode=True)
        self._policy = policy_engine or PolicyEngine()
        self._cache = cache or SemanticCache()
        self._breakers = breakers or get_registry()
        self._context_window = context_window
        self._embedding_fn: Callable[[str], list[float]] = (
            embedding_fn if embedding_fn is not None else self._text_to_embedding
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def execute(self, request: EngineRequest) -> EngineResponse:
        """Run the full execution pipeline for *request*.

        Returns an EngineResponse.  Never raises — errors are captured into
        the response object so callers always receive a structured reply.
        """
        start = time.monotonic()
        request_id = str(uuid.uuid4())

        try:
            return self._run_pipeline(request, request_id, start)
        except PromptFirewallError as exc:
            return self._error_response(request_id, None, str(exc), start, "firewall")
        except IntentLoopError as exc:
            return self._error_response(request_id, None, str(exc), start, "intent_loop")
        except SkillNotFoundError as exc:
            return self._error_response(request_id, None, str(exc), start, "L1")
        except (PolicyViolationError, SignatureVerificationError) as exc:
            return self._error_response(request_id, None, str(exc), start, "security")
        except TokenBudgetExceededError as exc:
            return self._error_response(request_id, None, str(exc), start, "L2")
        except SandboxExecutionError as exc:
            return self._error_response(request_id, None, str(exc), start, "L3")
        except CircuitBreakerOpenError as exc:
            return self._error_response(request_id, None, str(exc), start, "circuit_breaker")
        except SkillEngineError as exc:
            return self._error_response(request_id, None, str(exc), start, "engine")
        except Exception as exc:  # pragma: no cover
            return self._error_response(request_id, None, f"Unexpected: {exc}", start, "system")

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        request: EngineRequest,
        request_id: str,
        start: float,
    ) -> EngineResponse:
        # ── 1. Prompt Firewall ──────────────────────────────────────────
        self._firewall.inspect(request.user_input)

        # ── 2. Intent loop detection ────────────────────────────────────
        self._breakers.record_intent(request.session_id, request.user_input.strip()[:128])

        # ── 3. Semantic cache lookup (output) ───────────────────────────
        cache_key = SemanticCache.make_key(request.user_input, request.region_code)
        cached_output = self._cache.get_output(cache_key)
        if cached_output is not None:
            latency = (time.monotonic() - start) * 1000
            return EngineResponse(
                request_id=request_id,
                skill_id=cached_output.get("skill_id"),
                success=True,
                output=cached_output,
                latency_ms=latency,
                was_cached=True,
            )

        # ── 4. L1 Discovery ─────────────────────────────────────────────
        # Build query embedding via injected function (production: sentence-transformer).
        query_embedding = self._embedding_fn(request.user_input)

        l1_breaker = self._breakers.get_or_create(f"l1:{request.session_id}")
        l1_breaker.assert_closed()

        try:
            candidates = self._l1.retrieve(
                query_embedding,
                region_code=request.region_code,
                cache_key=cache_key,
            )
        except SkillNotFoundError:
            l1_breaker.record_failure()
            raise

        l1_breaker.record_success()
        top = candidates[0]
        requires_review = top.requires_review

        # ── 5. Registry fetch + policy + signature ──────────────────────
        entry = self._registry.get(top.skill_id)
        skill_dict = entry.schema.model_dump()
        tags = entry.schema.metadata.tags if entry.schema.metadata else []

        # Policy check
        self._policy.assert_allowed(
            skill_region_code=entry.schema.region_code,
            request_region_code=request.region_code,
            skill_tags=tags,
            security_level=entry.schema.security_level.value,
        )

        # ── 6. L2 — Token prediction + instruction load ─────────────────
        l2_breaker = self._breakers.get_or_create(f"l2:{top.skill_id}")
        l2_breaker.assert_closed()

        try:
            loaded = self._l2.load(
                top.skill_id,
                extra_context_tokens=request.context_tokens_used,
            )
        except KeyError:
            # No instructions registered — treat as empty skill
            loaded = None
        except TokenBudgetExceededError:
            l2_breaker.record_failure()
            # L2 circuit-breaker recovery: prune more aggressively
            try:
                loaded = self._l2.reload_pruned(top.skill_id, aggressive=True)
            except Exception:
                raise

        if loaded is not None:
            l2_breaker.record_success()

        instructions = loaded.instructions if loaded else []

        # ── 7. L3 — Sandboxed execution ─────────────────────────────────
        l3_breaker = self._breakers.get_or_create(f"l3:{top.skill_id}")
        l3_breaker.assert_closed()

        result: ExecutionResult = self._l3.execute(
            top.skill_id,
            instructions,
            request.user_input,
            context={"region_code": request.region_code, "request_id": request_id},
        )

        if not result.success:
            l3_breaker.record_failure()
            raise SandboxExecutionError(
                result.error or f"L3 execution failed for skill '{top.skill_id}'."
            )

        l3_breaker.record_success()

        # ── 8. Cache output ─────────────────────────────────────────────
        output_payload = {
            "skill_id": top.skill_id,
            "result": result.output,
            "token_usage": result.token_usage,
        }
        self._cache.set_output(cache_key, output_payload)

        latency = (time.monotonic() - start) * 1000
        return EngineResponse(
            request_id=request_id,
            skill_id=top.skill_id,
            success=True,
            output=result.output,
            latency_ms=latency,
            token_usage=result.token_usage,
            requires_review=requires_review,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _text_to_embedding(text: str, dims: int = 64) -> list[float]:
        """Produce a deterministic pseudo-embedding from text.

        This is a hash-based stub for development/testing.  Production
        deployments replace this with a real sentence-transformer call.
        """
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Extend to `dims` dimensions by cycling the hash bytes
        extended = (h * ((dims // 32) + 1))[:dims]
        return [b / 255.0 for b in extended]

    @staticmethod
    def _error_response(
        request_id: str,
        skill_id: Optional[str],
        error: str,
        start: float,
        tier: str,
    ) -> EngineResponse:
        return EngineResponse(
            request_id=request_id,
            skill_id=skill_id,
            success=False,
            output=None,
            latency_ms=(time.monotonic() - start) * 1000,
            error=error,
            circuit_tier=tier,
        )
