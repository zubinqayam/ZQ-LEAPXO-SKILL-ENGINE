"""Strict v2.1 skill schema with Pydantic validation.

Every skill loaded by the engine MUST conform to this schema.
Unknown fields are forbidden to prevent injection via extra keys.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SecurityLevel(StrEnum):
    P0 = "P0"  # Critical / never decay
    P1 = "P1"  # High
    P2 = "P2"  # Standard


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"
    STRUCTURED = "structured"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class SkillInstruction(BaseModel):
    """A single instruction entry within a skill."""

    model_config = {"extra": "forbid"}

    content: str = Field(..., min_length=1, max_length=4096)
    prunable: bool = Field(
        default=True,
        description="Set to False to mark as NON-PRUNABLE (kept even under tight token budgets).",
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Priority weight used during dynamic pruning (higher = kept longer).",
    )


class SkillMetadata(BaseModel):
    """Optional rich metadata attached to a skill."""

    model_config = {"extra": "forbid"}

    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# Primary skill schema
# ---------------------------------------------------------------------------

_KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_REGION_RE = re.compile(r"^[A-Z]{2}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")


class SkillSchema(BaseModel):
    """LEAPXO Skill Engine v2.1 canonical skill definition.

    Fields are strictly validated.  Extra fields are forbidden to prevent
    injection via additional JSON keys.
    """

    model_config = {"extra": "forbid"}

    skill_id: Annotated[str, Field(min_length=3, max_length=128)] = Field(
        ...,
        description="Unique kebab-case identifier, e.g. 'chest-pain-triage-om'.",
    )
    version: str = Field(..., description="Semantic version string, e.g. '2.1'.")
    intent: str = Field(..., min_length=5, max_length=512)
    output_format: OutputFormat
    region_code: Annotated[str, Field(min_length=2, max_length=2)] = Field(
        default="GL",
        description="ISO 3166-1 alpha-2 country code.  'GL' = global (no regional restriction).",
    )
    security_level: SecurityLevel = Field(default=SecurityLevel.P2)
    signature: str | None = Field(
        default=None,
        description="Base64-encoded ECDSA P-256 signature over the canonical skill payload.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="List of skill_ids this skill depends on (max chain depth enforced by engine).",
    )
    instructions: list[SkillInstruction] = Field(
        default_factory=list,
        description="Ordered list of instruction blocks (L2 layer).",
    )
    metadata: SkillMetadata | None = None

    # ------------------------------------------------------------------
    # Field validators
    # ------------------------------------------------------------------

    @field_validator("skill_id")
    @classmethod
    def validate_skill_id(cls, v: str) -> str:
        if not _KEBAB_RE.match(v):
            raise ValueError(
                f"skill_id '{v}' must be kebab-case (lowercase letters, digits, hyphens)."
            )
        return v

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(
                f"version '{v}' must follow semantic versioning (e.g. '2.1' or '2.1.0')."
            )
        return v

    @field_validator("region_code")
    @classmethod
    def validate_region_code(cls, v: str) -> str:
        if not _REGION_RE.match(v):
            raise ValueError(
                f"region_code '{v}' must be a 2-letter uppercase ISO country code or 'GL'."
            )
        return v

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, v: list[str]) -> list[str]:
        for dep in v:
            if not _KEBAB_RE.match(dep):
                raise ValueError(f"Dependency '{dep}' must be a valid kebab-case skill_id.")
        return v

    @model_validator(mode="after")
    def validate_p0_requires_signature(self) -> SkillSchema:
        if self.security_level == SecurityLevel.P0 and not self.signature:
            raise ValueError("P0 skills MUST carry an ECDSA signature.")
        return self
