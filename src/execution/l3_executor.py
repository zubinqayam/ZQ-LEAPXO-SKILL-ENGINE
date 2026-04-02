"""L3 Execution Layer — sandboxed skill execution.

Security model:
* Each skill runs in an isolated execution context.
* No outbound network access (enforced at orchestration layer; container policy).
* File system access restricted to read-only mount.
* IPC exclusively via Redis with TTL-based keys and mTLS.
* AppArmor profile annotations embedded in execution metadata.
* TOCTOU protections: the skill payload is hashed before execution; any
  modification between load and run raises SandboxExecutionError.

This module provides the abstract executor interface and a default in-process
executor for testing.  In production the executor dispatches to gVisor/Docker.
"""

from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.core.exceptions import SandboxExecutionError


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    skill_id: str
    success: bool
    output: Any
    latency_ms: float
    token_usage: int = 0
    error: Optional[str] = None
    sandbox_metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract executor
# ---------------------------------------------------------------------------

class BaseL3Executor(ABC):
    """Abstract base class for L3 sandboxed executors."""

    @abstractmethod
    def execute(
        self,
        skill_id: str,
        instructions: list[dict],
        user_input: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Execute the skill and return a structured result."""


# ---------------------------------------------------------------------------
# Sandbox descriptor (metadata passed to container runtimes)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SandboxPolicy:
    """Immutable sandbox security policy for a skill execution."""

    no_network: bool = True
    read_only_fs: bool = True
    no_exec: bool = True           # noexec mount flag
    apparmor_profile: str = "leapxo-skill-default"
    no_shared_memory: bool = True
    ipc_via_redis_only: bool = True
    max_cpu_seconds: int = 30
    max_memory_mb: int = 256


# ---------------------------------------------------------------------------
# Payload integrity (TOCTOU protection)
# ---------------------------------------------------------------------------

def _compute_payload_hash(
    skill_id: str,
    instructions: list[dict],
    user_input: str,
) -> str:
    payload = json.dumps(
        {"skill_id": skill_id, "instructions": instructions, "input": user_input},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Default in-process executor (for testing / local dev)
# ---------------------------------------------------------------------------

class InProcessL3Executor(BaseL3Executor):
    """Executes skill instructions in-process (no real isolation).

    ONLY for local development and testing.  In production deploy the
    Docker/gVisor executor.
    """

    def execute(
        self,
        skill_id: str,
        instructions: list[dict],
        user_input: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        start = time.monotonic()

        # Compute pre-execution payload hash (TOCTOU protection)
        pre_hash = _compute_payload_hash(skill_id, instructions, user_input)

        try:
            # Simulate execution: concatenate non-empty instruction content.
            contents = [
                i["content"] for i in instructions if i.get("content")
            ]
            if not contents:
                raise SandboxExecutionError(
                    f"Skill '{skill_id}' has no executable instructions."
                )

            # Post-execution integrity check
            post_hash = _compute_payload_hash(skill_id, instructions, user_input)
            if pre_hash != post_hash:
                raise SandboxExecutionError(
                    f"TOCTOU violation detected for skill '{skill_id}': "
                    "payload was modified during execution."
                )

            output = {
                "skill_id": skill_id,
                "instructions_applied": len(contents),
                "user_input": user_input,
                "result": f"Executed {len(contents)} instruction(s) for skill '{skill_id}'.",
            }

            latency_ms = (time.monotonic() - start) * 1000

            return ExecutionResult(
                skill_id=skill_id,
                success=True,
                output=output,
                latency_ms=latency_ms,
                token_usage=sum(len(c.split()) for c in contents),
                sandbox_metadata={
                    "executor": "in-process",
                    "policy": SandboxPolicy().__dict__,
                    "payload_hash": post_hash,
                },
            )

        except SandboxExecutionError:
            raise
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return ExecutionResult(
                skill_id=skill_id,
                success=False,
                output=None,
                latency_ms=latency_ms,
                error=str(exc),
            )
