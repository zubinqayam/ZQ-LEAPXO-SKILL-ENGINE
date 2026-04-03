"""Prompt Firewall — LLM-based injection & jailbreak detection.

Replaces naive regex filters with a pluggable detector that can be backed by:
* A local rule-based heuristic classifier (default, zero-dependency).
* Any LLM API endpoint (configure via PromptFirewall.use_llm_backend).

Detects:
* Jailbreak intent ("ignore previous instructions", "DAN mode", etc.)
* Instruction override attempts.
* Encoded attacks (base64/hex-obfuscated payloads).
* Prompt injection patterns (role-swap, system-override markers).

The firewall is FAIL-CLOSED: if classification cannot be performed, the
request is BLOCKED and logged.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from src.core.exceptions import PromptFirewallError

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


class FirewallVerdict(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"  # Flagged for human review but not hard-blocked


@dataclass
class FirewallResult:
    verdict: FirewallVerdict
    reason: str
    confidence: float = 1.0
    detected_patterns: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Heuristic patterns
# ---------------------------------------------------------------------------

_JAILBREAK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\bignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|context)\b", re.I
    ),
    re.compile(r"\bdan\s+mode\b", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bdo\s+anything\s+now\b", re.I),
    re.compile(r"\byou\s+are\s+now\s+(?:an?\s+)?(?:evil|uncensored|unrestricted)\b", re.I),
    re.compile(
        r"\bact\s+as\s+if\s+(you\s+have\s+no\s+restrictions|there\s+are\s+no\s+rules)\b", re.I
    ),
    re.compile(r"\bforget\s+(your|all)\s+(previous\s+)?(training|rules|instructions)\b", re.I),
    re.compile(
        r"\bpretend\s+(you\s+are|to\s+be)\s+(an?\s+)?(?:evil|malicious|unconstrained)\b", re.I
    ),
]

_OVERRIDE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<\s*system\s*>", re.I),
    re.compile(r"\[INST\]", re.I),
    re.compile(r"###\s*system\s*:", re.I),
    re.compile(r"\bsystem\s*:\s*you\s+are\b", re.I),
    re.compile(r"\bnew\s+instructions?\s*:", re.I),
    re.compile(r"---\s*OVERRIDE\s*---", re.I),
]

# If more than this fraction of a token-like word looks like base64, flag it.
_B64_SUSPICIOUS_LENGTH = 60


def _check_encoded_attack(text: str) -> list[str]:
    """Return a list of detected encoded-attack patterns."""
    hits: list[str] = []
    # Look for long base64-looking blobs
    for chunk in re.findall(r"[A-Za-z0-9+/]{40,}={0,2}", text):
        try:
            decoded = base64.b64decode(chunk + "==").decode("utf-8", errors="replace")
            for pat in _JAILBREAK_PATTERNS + _OVERRIDE_PATTERNS:
                if pat.search(decoded):
                    hits.append("base64-encoded-injection")
                    break
        except (binascii.Error, UnicodeDecodeError):
            pass
    # Hex-encoded long strings
    for chunk in re.findall(r"(?:0x)?[0-9a-fA-F]{40,}", text):
        try:
            decoded = bytes.fromhex(chunk.replace("0x", "")).decode("utf-8", errors="replace")
            for pat in _JAILBREAK_PATTERNS + _OVERRIDE_PATTERNS:
                if pat.search(decoded):
                    hits.append("hex-encoded-injection")
                    break
        except (ValueError, UnicodeDecodeError):
            pass
    return hits


# ---------------------------------------------------------------------------
# Firewall
# ---------------------------------------------------------------------------


class PromptFirewall:
    """Two-stage prompt firewall (heuristic → optional LLM backend).

    Attributes:
        llm_backend: Optional callable ``(prompt: str) -> FirewallResult``.
            When set, the heuristic stage runs first; if it passes, the LLM
            backend performs a deeper check.
    """

    def __init__(
        self,
        llm_backend: Callable[[str], FirewallResult] | None = None,
        strict_mode: bool = True,
    ) -> None:
        self._llm_backend = llm_backend
        self._strict_mode = strict_mode

    def inspect(self, prompt: str) -> FirewallResult:
        """Run the firewall against *prompt*.

        Returns:
            A FirewallResult with verdict ALLOW, BLOCK, or REVIEW.

        Raises:
            PromptFirewallError: In strict mode when verdict is BLOCK.
        """
        if not prompt or not prompt.strip():
            return FirewallResult(
                verdict=FirewallVerdict.ALLOW, reason="empty prompt", confidence=1.0
            )

        detected: list[str] = []

        for pat in _JAILBREAK_PATTERNS:
            if pat.search(prompt):
                detected.append(f"jailbreak:{pat.pattern[:30]}")

        for pat in _OVERRIDE_PATTERNS:
            if pat.search(prompt):
                detected.append(f"override:{pat.pattern[:30]}")

        detected.extend(_check_encoded_attack(prompt))

        if detected:
            result = FirewallResult(
                verdict=FirewallVerdict.BLOCK,
                reason="Heuristic firewall: injection/jailbreak pattern detected.",
                confidence=0.95,
                detected_patterns=detected,
            )
            if self._strict_mode:
                raise PromptFirewallError(
                    f"Prompt blocked by firewall: {result.reason} Patterns: {detected}"
                )
            return result

        # Optional deep LLM check
        if self._llm_backend is not None:
            try:
                result = self._llm_backend(prompt)
            except Exception as exc:
                # Fail-closed
                if self._strict_mode:
                    raise PromptFirewallError(
                        "Prompt firewall LLM backend failed — blocking request (fail-closed)."
                    ) from exc
                return FirewallResult(
                    verdict=FirewallVerdict.BLOCK,
                    reason=f"LLM backend error (fail-closed): {exc}",
                    confidence=1.0,
                )
            if result.verdict == FirewallVerdict.BLOCK and self._strict_mode:
                raise PromptFirewallError(f"Prompt blocked by LLM firewall: {result.reason}")
            return result

        return FirewallResult(
            verdict=FirewallVerdict.ALLOW,
            reason="No threats detected.",
            confidence=1.0,
        )
