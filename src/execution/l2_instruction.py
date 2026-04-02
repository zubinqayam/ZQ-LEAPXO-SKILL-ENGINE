"""L2 Instruction Layer — token-aware dynamic instruction loading.

Loads skill instructions on demand (not pre-loaded), applies the token
predictor to prune low-priority entries, and guarantees NON-PRUNABLE
instructions are always preserved.

Contract:
* Instructions are loaded ONLY when a skill is selected for execution.
* Token predictor runs BEFORE sending to the LLM.
* 15 % safety buffer is applied (enforced by token_predictor.predict_tokens).
* Hard cutoff at 90 % context window (enforced by token_predictor).
* Instructions tagged prunable=False are always kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.core.token_predictor import predict_tokens, prune_instructions
from src.core.exceptions import TokenBudgetExceededError


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LoadedInstructions:
    skill_id: str
    instructions: List[dict]
    token_estimate: int
    was_pruned: bool


# ---------------------------------------------------------------------------
# L2 Loader
# ---------------------------------------------------------------------------

class L2InstructionLoader:
    """Loads and prunes instructions for a given skill.

    In production the raw instructions are fetched from the Skill Registry
    (backed by an encrypted store).  Here the registry is an in-memory dict
    keyed by skill_id.
    """

    def __init__(
        self,
        context_window: int = 8192,
        reserved_tokens: int = 512,
    ) -> None:
        self._context_window = context_window
        self._reserved_tokens = reserved_tokens
        # Raw store: skill_id → list of instruction dicts
        self._store: Dict[str, List[dict]] = {}

    # ------------------------------------------------------------------
    # Store management
    # ------------------------------------------------------------------

    def register_instructions(self, skill_id: str, instructions: List[dict]) -> None:
        """Store raw instructions for *skill_id*."""
        self._store[skill_id] = list(instructions)

    # ------------------------------------------------------------------
    # Load + prune
    # ------------------------------------------------------------------

    def load(
        self,
        skill_id: str,
        *,
        extra_context_tokens: int = 0,
    ) -> LoadedInstructions:
        """Load and prune instructions for *skill_id*.

        Args:
            skill_id: The skill to load instructions for.
            extra_context_tokens: Additional tokens already consumed by the
                conversation history / system prompt.

        Returns:
            A LoadedInstructions instance with the pruned instruction list
            and estimated token count.

        Raises:
            KeyError: If skill_id is not registered.
            TokenBudgetExceededError: If even non-prunable instructions exceed
                the hard token limit.
        """
        raw = self._store[skill_id]

        effective_reserved = self._reserved_tokens + extra_context_tokens

        pruned = prune_instructions(
            raw,
            context_window=self._context_window,
            reserved_tokens=effective_reserved,
        )

        was_pruned = len(pruned) < len(raw)

        # Final token estimate (raises if over hard limit)
        combined_text = " ".join(i.get("content", "") for i in pruned)
        token_estimate = predict_tokens(combined_text, context_window=self._context_window)

        return LoadedInstructions(
            skill_id=skill_id,
            instructions=pruned,
            token_estimate=token_estimate,
            was_pruned=was_pruned,
        )

    def reload_pruned(
        self,
        skill_id: str,
        *,
        aggressive: bool = True,
    ) -> LoadedInstructions:
        """Reload with more aggressive pruning (L2 circuit-breaker recovery).

        In aggressive mode the reserved token budget is doubled to create
        more headroom.
        """
        multiplier = 2 if aggressive else 1
        return self.load(
            skill_id,
            extra_context_tokens=self._reserved_tokens * multiplier,
        )
