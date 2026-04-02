"""Tests for the PolicyEngine."""

import pytest

from src.security.policy_engine import PolicyEngine
from src.core.exceptions import PolicyViolationError


@pytest.fixture()
def policy():
    return PolicyEngine()


class TestRegionalFiltering:
    def test_global_skill_any_region(self, policy):
        decision = policy.evaluate(
            skill_region_code="GL",
            request_region_code="US",
            skill_tags=["general"],
        )
        assert decision.allowed is True

    def test_regional_skill_matching_region(self, policy):
        decision = policy.evaluate(
            skill_region_code="OM",
            request_region_code="OM",
            skill_tags=["general"],
        )
        assert decision.allowed is True

    def test_regional_skill_wrong_region_raises(self, policy):
        with pytest.raises(PolicyViolationError):
            policy.evaluate(
                skill_region_code="OM",
                request_region_code="US",
                skill_tags=["general"],
            )


class TestMedicalCompliance:
    def test_medical_skill_in_compliance_region_flagged(self, policy):
        decision = policy.evaluate(
            skill_region_code="OM",
            request_region_code="OM",
            skill_tags=["medical", "triage"],
        )
        assert decision.requires_medical_compliance is True

    def test_medical_skill_non_compliance_region_not_flagged(self, policy):
        decision = policy.evaluate(
            skill_region_code="GL",
            request_region_code="JP",
            skill_tags=["medical"],
        )
        assert decision.requires_medical_compliance is False

    def test_non_medical_skill_no_compliance(self, policy):
        decision = policy.evaluate(
            skill_region_code="GL",
            request_region_code="OM",
            skill_tags=["general", "qa"],
        )
        assert decision.requires_medical_compliance is False


class TestP0Escalation:
    def test_p0_skill_requires_escalation(self, policy):
        decision = policy.evaluate(
            skill_region_code="GL",
            request_region_code="GL",
            skill_tags=["system"],
            security_level="P0",
        )
        assert decision.escalation_required is True

    def test_p1_no_escalation(self, policy):
        decision = policy.evaluate(
            skill_region_code="GL",
            request_region_code="GL",
            skill_tags=[],
            security_level="P1",
        )
        assert decision.escalation_required is False


class TestExtraBlocked:
    def test_extra_blocked_tag_raises(self):
        policy = PolicyEngine(extra_blocked={"US": {"financial-advice"}})
        with pytest.raises(PolicyViolationError):
            policy.evaluate(
                skill_region_code="GL",
                request_region_code="US",
                skill_tags=["financial-advice"],
            )
