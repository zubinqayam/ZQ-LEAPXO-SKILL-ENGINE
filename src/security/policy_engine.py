"""Policy Engine — region-based filtering and compliance routing.

Responsibilities:
* Enforce immutable P0 policies outside LLM context.
* Route requests to compliant skills based on region_code.
* Block medical/sensitive skill execution in non-compliant regions.
* Immutable policies are defined at module load time and cannot be overridden
  by runtime configuration or LLM output.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.exceptions import PolicyViolationError

# ---------------------------------------------------------------------------
# Immutable P0 policy definitions (never modified at runtime)
# ---------------------------------------------------------------------------

# Regions where medical skills require additional compliance checks.
_MEDICAL_COMPLIANCE_REGIONS: frozenset[str] = frozenset(
    {
        "OM",  # Oman
        "SA",  # Saudi Arabia
        "AE",  # UAE
        "KW",  # Kuwait
        "QA",  # Qatar
        "BH",  # Bahrain
        "EG",  # Egypt
        "US",  # USA (HIPAA)
        "EU",  # European Union (GDPR)
        "GB",  # UK
        "DE",  # Germany
        "FR",  # France
    }
)

# Skill categories that require medical compliance in the above regions.
_MEDICAL_SKILL_TAGS: frozenset[str] = frozenset(
    {
        "medical",
        "clinical",
        "diagnosis",
        "triage",
        "prescription",
        "health",
        "pharma",
    }
)

# Regions where certain skill categories are fully blocked.
_REGION_BLOCKED_CATEGORIES: dict[str, frozenset[str]] = {
    # Example: no financial-advice skills in these sandboxed regions.
    "GL": frozenset(),
}


# ---------------------------------------------------------------------------
# Policy dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    requires_medical_compliance: bool = False
    escalation_required: bool = False


# ---------------------------------------------------------------------------
# Policy Engine
# ---------------------------------------------------------------------------


class PolicyEngine:
    """Evaluates whether a (skill, region) combination is allowed.

    Policies are immutable and enforced before any LLM call.
    """

    def __init__(
        self,
        extra_blocked: dict[str, set[str]] | None = None,
    ) -> None:
        # Additional runtime blocks can be injected (e.g., from config),
        # but CANNOT override the hardcoded _MEDICAL_COMPLIANCE_REGIONS.
        self._extra_blocked: dict[str, set[str]] = extra_blocked or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        *,
        skill_region_code: str,
        request_region_code: str,
        skill_tags: list[str],
        security_level: str = "P2",
    ) -> PolicyDecision:
        """Return a PolicyDecision for the given (skill, request) context.

        Args:
            skill_region_code: The region the skill is designed for ('GL' = global).
            request_region_code: The region of the incoming request.
            skill_tags: Tags attached to the skill (used for compliance routing).
            security_level: Skill security level ('P0', 'P1', 'P2').

        Returns:
            A PolicyDecision describing whether the action is permitted.

        Raises:
            PolicyViolationError: If the skill is hard-blocked for this region.
        """
        # --- Regional skill match check ---
        if skill_region_code != "GL" and skill_region_code != request_region_code:
            decision = PolicyDecision(
                allowed=False,
                reason=(
                    f"Skill is restricted to region '{skill_region_code}' "
                    f"but request originated from '{request_region_code}'."
                ),
            )
            raise PolicyViolationError(decision.reason)

        # --- Medical compliance check ---
        tags_lower = {t.lower() for t in skill_tags}
        is_medical = bool(tags_lower & _MEDICAL_SKILL_TAGS)
        needs_compliance = is_medical and request_region_code in _MEDICAL_COMPLIANCE_REGIONS

        # --- Extra blocked categories check ---
        blocked_for_region = self._extra_blocked.get(request_region_code, set())
        if tags_lower & blocked_for_region:
            decision = PolicyDecision(
                allowed=False,
                reason=(
                    f"Skill tags {tags_lower & blocked_for_region} are blocked "
                    f"in region '{request_region_code}'."
                ),
            )
            raise PolicyViolationError(decision.reason)

        return PolicyDecision(
            allowed=True,
            reason="Policy check passed.",
            requires_medical_compliance=needs_compliance,
            escalation_required=(security_level == "P0"),
        )

    def assert_allowed(
        self,
        *,
        skill_region_code: str,
        request_region_code: str,
        skill_tags: list[str],
        security_level: str = "P2",
    ) -> PolicyDecision:
        """Like evaluate() but always raises PolicyViolationError on denial."""
        return self.evaluate(
            skill_region_code=skill_region_code,
            request_region_code=request_region_code,
            skill_tags=skill_tags,
            security_level=security_level,
        )
