"""Tests for SkillSchema — v2.1 strict validation."""

import pytest
from pydantic import ValidationError

from src.core.skill_schema import SkillSchema, SecurityLevel, OutputFormat


def _valid_payload(**overrides) -> dict:
    base = {
        "skill_id": "test-skill",
        "version": "2.1",
        "intent": "Test the skill schema validation logic",
        "output_format": "text",
        "region_code": "GL",
        "security_level": "P2",
    }
    base.update(overrides)
    return base


class TestSkillIdValidation:
    def test_valid_kebab_case(self):
        s = SkillSchema(**_valid_payload(skill_id="valid-skill-123"))
        assert s.skill_id == "valid-skill-123"

    def test_invalid_uppercase(self):
        with pytest.raises(ValidationError, match="kebab-case"):
            SkillSchema(**_valid_payload(skill_id="InvalidSkill"))

    def test_invalid_spaces(self):
        with pytest.raises(ValidationError):
            SkillSchema(**_valid_payload(skill_id="has spaces"))

    def test_invalid_underscore(self):
        with pytest.raises(ValidationError):
            SkillSchema(**_valid_payload(skill_id="has_underscore"))


class TestVersionValidation:
    def test_two_part_version(self):
        s = SkillSchema(**_valid_payload(version="2.1"))
        assert s.version == "2.1"

    def test_three_part_version(self):
        s = SkillSchema(**_valid_payload(version="2.1.0"))
        assert s.version == "2.1.0"

    def test_invalid_version(self):
        with pytest.raises(ValidationError):
            SkillSchema(**_valid_payload(version="v2.1"))


class TestRegionCode:
    def test_valid_gl(self):
        s = SkillSchema(**_valid_payload(region_code="GL"))
        assert s.region_code == "GL"

    def test_valid_om(self):
        s = SkillSchema(**_valid_payload(region_code="OM"))
        assert s.region_code == "OM"

    def test_invalid_lowercase(self):
        with pytest.raises(ValidationError):
            SkillSchema(**_valid_payload(region_code="om"))

    def test_invalid_three_letters(self):
        with pytest.raises(ValidationError):
            SkillSchema(**_valid_payload(region_code="OMN"))


class TestP0RequiresSignature:
    def test_p0_without_signature_raises(self):
        with pytest.raises(ValidationError, match="ECDSA signature"):
            SkillSchema(**_valid_payload(security_level="P0", signature=None))

    def test_p0_with_signature_allowed(self):
        s = SkillSchema(**_valid_payload(security_level="P0", signature="dummysig"))
        assert s.security_level == SecurityLevel.P0

    def test_p1_without_signature_allowed(self):
        s = SkillSchema(**_valid_payload(security_level="P1"))
        assert s.security_level == SecurityLevel.P1


class TestExtraFieldsForbidden:
    def test_extra_field_raises(self):
        with pytest.raises(ValidationError):
            SkillSchema(**_valid_payload(unknown_field="oops"))


class TestInstructions:
    def test_non_prunable_instruction(self):
        s = SkillSchema(
            **_valid_payload(
                instructions=[
                    {"content": "Critical instruction", "prunable": False, "weight": 1.0}
                ]
            )
        )
        assert s.instructions[0].prunable is False

    def test_empty_instructions_allowed(self):
        s = SkillSchema(**_valid_payload(instructions=[]))
        assert s.instructions == []
