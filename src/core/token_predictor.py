"""Token prediction module (tiktoken-based).

Estimates token counts for prompts/instructions BEFORE sending to the LLM,
preventing context-window overflows.

Key guarantees:
* 15 % safety buffer applied on top of raw count.
* Hard cut-off at 90 % of the provided context window.
* JSON-aware: extra tokens for JSON structural overhead are accounted for.
* Multilingual: uses `cl100k_base` encoding which handles non-Latin scripts.
"""

from __future__ import annotations

import json
from typing import Any

from src.core.exceptions import TokenBudgetExceededError

_ENCODING: Any = None

try:
    import tiktoken  # type: ignore

    _ENCODING = tiktoken.get_encoding("cl100k_base")
    _TIKTOKEN_AVAILABLE = True
except Exception:  # pragma: no cover
    _TIKTOKEN_AVAILABLE = False
    _ENCODING = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAFETY_BUFFER_FACTOR = 1.15  # 15 % safety margin
HARD_CUTOFF_RATIO = 0.90  # refuse if predicted > 90 % of context window
JSON_OVERHEAD_TOKENS = 8  # rough estimate for JSON structural tokens


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def count_tokens(text: str) -> int:
    """Return the number of tokens in *text* using cl100k_base encoding.

    Falls back to a word-based heuristic when tiktoken is unavailable (e.g.
    in minimal test environments).
    """
    if _TIKTOKEN_AVAILABLE and _ENCODING is not None:
        return len(_ENCODING.encode(text))
    # Heuristic fallback: ~1.3 tokens per word
    return max(1, int(len(text.split()) * 1.3))


def predict_tokens(
    payload: str | dict | list,
    *,
    context_window: int = 8192,
) -> int:
    """Estimate token usage for *payload* and enforce budget limits.

    Args:
        payload: The text, dict, or list to evaluate.
        context_window: Maximum tokens supported by the target model.

    Returns:
        Predicted token count including the safety buffer.

    Raises:
        TokenBudgetExceededError: If the predicted count exceeds 90 % of
            *context_window*.
    """
    if isinstance(payload, (dict, list)):
        text = json.dumps(payload, ensure_ascii=False)
        raw = count_tokens(text) + JSON_OVERHEAD_TOKENS
    else:
        raw = count_tokens(str(payload))

    predicted = int(raw * SAFETY_BUFFER_FACTOR)
    hard_limit = int(context_window * HARD_CUTOFF_RATIO)

    if predicted > hard_limit:
        raise TokenBudgetExceededError(
            f"Predicted token count {predicted} exceeds hard limit "
            f"{hard_limit} (90 % of context window {context_window})."
        )

    return predicted


def prune_instructions(
    instructions: list[dict],
    *,
    context_window: int = 8192,
    reserved_tokens: int = 512,
) -> list[dict]:
    """Remove low-priority instructions until the budget fits.

    Instructions with ``prunable=False`` are NEVER removed.
    Prunable instructions are removed in ascending *weight* order (lowest
    weight first) until the payload fits within the available budget.

    Args:
        instructions: List of instruction dicts (must have 'content',
            'prunable', 'weight' keys).
        context_window: Max model context in tokens.
        reserved_tokens: Tokens reserved for the user prompt and response.

    Returns:
        Pruned list of instructions that fits within the token budget.
    """
    available = int(context_window * HARD_CUTOFF_RATIO) - reserved_tokens

    # Split into non-prunable (always kept) and prunable (candidates).
    non_prunable = [i for i in instructions if not i.get("prunable", True)]
    prunable = [i for i in instructions if i.get("prunable", True)]

    # Sort prunable ascending by weight so lowest-weight items are dropped first.
    prunable.sort(key=lambda x: x.get("weight", 1.0))

    retained: list[dict] = list(non_prunable)

    # Count tokens already committed by non-prunable instructions.
    committed = count_tokens(" ".join(i.get("content", "") for i in non_prunable))

    for instr in prunable:
        cost = count_tokens(instr.get("content", ""))
        if committed + cost <= available:
            retained.append(instr)
            committed += cost

    return retained
