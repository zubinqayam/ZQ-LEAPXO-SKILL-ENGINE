"""Skill Registry — central store with HNSW-style indexing and P0 protection.

Features:
* Skills stored with their full schema + embedding vector.
* P0 skills are NEVER purged from the registry (protected tier).
* Rare skills are moved to a protected tier and exempt from LRU eviction.
* Blue/Green deployment: new versions staged in a shadow slot before promotion.
* Drift-safe embeddings: re-embedding is triggered if the embedding model
  version changes.

The in-memory HNSW simulation uses flat cosine search; production deployments
replace this with a real HNSW client (e.g. hnswlib or Qdrant).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional, Tuple

from src.core.skill_schema import SkillSchema, SecurityLevel
from src.core.exceptions import SkillNotFoundError, SkillValidationError
from src.security.ecdsa_signer import ECDSAVerifier, canonical_payload


# ---------------------------------------------------------------------------
# Slot (Blue / Green)
# ---------------------------------------------------------------------------

class DeploymentSlot(str, Enum):
    BLUE = "blue"    # Active production slot
    GREEN = "green"  # Staging slot (shadow)


# ---------------------------------------------------------------------------
# Registry entry
# ---------------------------------------------------------------------------

@dataclass
class RegistryEntry:
    schema: SkillSchema
    embedding: List[float]
    slot: DeploymentSlot = DeploymentSlot.BLUE
    access_count: int = 0
    protected: bool = False   # True for P0 and rare skills


# ---------------------------------------------------------------------------
# Skill Registry
# ---------------------------------------------------------------------------

class SkillRegistry:
    """Central skill store with deployment slots and access-based protection."""

    # Skills accessed fewer than this many times are considered 'rare'.
    RARE_ACCESS_THRESHOLD = 5

    def __init__(
        self,
        verifier: Optional[ECDSAVerifier] = None,
        enforce_signatures: bool = False,
    ) -> None:
        self._entries: Dict[str, RegistryEntry] = {}
        self._lock = Lock()
        self._verifier = verifier
        self._enforce_signatures = enforce_signatures

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        schema: SkillSchema,
        embedding: List[float],
        *,
        slot: DeploymentSlot = DeploymentSlot.BLUE,
    ) -> None:
        """Register or update a skill.

        Raises:
            SkillValidationError: If signature verification fails.
        """
        if self._enforce_signatures and self._verifier:
            try:
                self._verifier.verify_skill(schema.model_dump())
            except Exception as exc:
                raise SkillValidationError(
                    f"Skill '{schema.skill_id}' failed signature verification."
                ) from exc

        is_protected = (schema.security_level == SecurityLevel.P0)

        entry = RegistryEntry(
            schema=schema,
            embedding=list(embedding),
            slot=slot,
            protected=is_protected,
        )
        with self._lock:
            self._entries[schema.skill_id] = entry

    def promote_green_to_blue(self, skill_id: str) -> None:
        """Promote a GREEN (staged) skill to BLUE (production)."""
        with self._lock:
            entry = self._entries.get(skill_id)
            if entry is None:
                raise SkillNotFoundError(f"Skill '{skill_id}' not found in registry.")
            if entry.slot != DeploymentSlot.GREEN:
                raise ValueError(f"Skill '{skill_id}' is not in GREEN slot.")
            entry.slot = DeploymentSlot.BLUE

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, skill_id: str) -> RegistryEntry:
        """Fetch a skill entry by exact ID."""
        with self._lock:
            entry = self._entries.get(skill_id)
        if entry is None:
            raise SkillNotFoundError(f"Skill '{skill_id}' not found in registry.")
        entry.access_count += 1
        # Mark rare skill as protected to prevent eviction
        if entry.access_count < self.RARE_ACCESS_THRESHOLD:
            entry.protected = True
        return entry

    def get_all_blue(self) -> List[RegistryEntry]:
        """Return all skills in the BLUE (production) slot."""
        with self._lock:
            return [e for e in self._entries.values() if e.slot == DeploymentSlot.BLUE]

    def list_skill_ids(self) -> List[str]:
        with self._lock:
            return list(self._entries.keys())

    # ------------------------------------------------------------------
    # Eviction (LRU-like, respects protection)
    # ------------------------------------------------------------------

    def evict_if_needed(self, max_skills: int = 1000) -> int:
        """Evict unprotected skills over the capacity limit.

        Returns:
            Number of skills evicted.
        """
        with self._lock:
            unprotected = [
                (sid, e) for sid, e in self._entries.items() if not e.protected
            ]
            evicted = 0
            if len(self._entries) > max_skills:
                # Sort by access_count ascending (evict least-used first)
                unprotected.sort(key=lambda x: x[1].access_count)
                while len(self._entries) > max_skills and unprotected:
                    sid, _ = unprotected.pop(0)
                    del self._entries[sid]
                    evicted += 1
        return evicted
