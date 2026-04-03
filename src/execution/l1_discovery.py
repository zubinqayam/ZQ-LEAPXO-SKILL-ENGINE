"""L1 Discovery Layer — embedding-based skill retrieval.

Features:
* Top-3 candidate retrieval (configurable).
* Semantic deduplication: filters candidates with identical (intent, output_format).
* Semantic cache: avoids redundant embedding calls.
* Similarity guard: scores in [0.85, 0.95) are flagged for human review.
* Alias mapping: merged/renamed skills are transparently redirected.
* Region-based filtering: strips skills whose region_code doesn't match.

This module uses simple cosine similarity over numpy float32 vectors so that
the engine works without a running vector DB.  In production the similarity
calculation is delegated to the Skill Registry which uses HNSW indexing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

try:
    import numpy as np

    _NUMPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NUMPY_AVAILABLE = False
    np = None  # type: ignore

from src.core.exceptions import SkillNotFoundError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOP_K = 3
SIMILARITY_REVIEW_LOW = 0.85  # Below this → reject (too dissimilar)
SIMILARITY_REVIEW_HIGH = 0.95  # In [low, high) → flag for human review
SIMILARITY_AUTO_ACCEPT = 0.95  # Above this → auto-accept


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SkillCandidate:
    skill_id: str
    score: float
    region_code: str
    output_format: str
    intent_summary: str
    requires_review: bool = False


# ---------------------------------------------------------------------------
# Alias map
# ---------------------------------------------------------------------------


class AliasMap:
    """Tracks renamed/merged skills and transparently redirects lookups."""

    def __init__(self) -> None:
        self._aliases: dict[str, str] = {}

    def register(self, old_id: str, new_id: str) -> None:
        self._aliases[old_id] = new_id

    def resolve(self, skill_id: str) -> str:
        seen: set[str] = set()
        while skill_id in self._aliases:
            if skill_id in seen:
                break  # cycle guard
            seen.add(skill_id)
            skill_id = self._aliases[skill_id]
        return skill_id


# ---------------------------------------------------------------------------
# L1 Discovery
# ---------------------------------------------------------------------------


class L1Discovery:
    """Retrieves the top-K most relevant skills for a given query embedding.

    In production this wraps a vector DB client.  Here it operates over an
    in-memory index for portability.
    """

    def __init__(
        self,
        alias_map: AliasMap | None = None,
        top_k: int = TOP_K,
    ) -> None:
        self._alias_map = alias_map or AliasMap()
        self._top_k = top_k
        # Index: skill_id → (embedding, metadata_dict)
        self._index: dict[str, tuple[list, dict]] = {}
        # Semantic cache: query_hash → list[SkillCandidate]
        self._cache: dict[str, list[SkillCandidate]] = {}

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def index_skill(
        self,
        skill_id: str,
        embedding: list[float],
        *,
        region_code: str = "GL",
        output_format: str = "text",
        intent_summary: str = "",
    ) -> None:
        """Add or update a skill in the in-memory index."""
        resolved = self._alias_map.resolve(skill_id)
        self._index[resolved] = (
            embedding,
            {
                "region_code": region_code,
                "output_format": output_format,
                "intent_summary": intent_summary,
            },
        )
        # Invalidate cache on index change
        self._cache.clear()

    # ------------------------------------------------------------------
    # Similarity
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if _NUMPY_AVAILABLE:
            va = np.array(a, dtype=np.float32)
            vb = np.array(b, dtype=np.float32)
            denom = np.linalg.norm(va) * np.linalg.norm(vb)
            if denom == 0:
                return 0.0
            return float(np.dot(va, vb) / denom)
        # Pure-Python fallback
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query_embedding: list[float],
        *,
        region_code: str = "GL",
        cache_key: str | None = None,
    ) -> list[SkillCandidate]:
        """Return up to top_k matching skills, filtered and deduplicated.

        Args:
            query_embedding: Dense float vector for the user query.
            region_code: Request region; used to filter skills.
            cache_key: Optional cache key (e.g. hash of user query text).

        Returns:
            Ordered list of SkillCandidate (highest score first).

        Raises:
            SkillNotFoundError: If no candidate exceeds the minimum threshold.
        """
        # Semantic cache hit
        if cache_key and cache_key in self._cache:
            return self._cache[cache_key]

        if not self._index:
            raise SkillNotFoundError("Skill index is empty — no skills registered.")

        scored: list[tuple[float, str, dict]] = []
        for skill_id, (emb, meta) in self._index.items():
            # Region filter: accept skill if skill is global OR matches request region
            skill_region = meta.get("region_code", "GL")
            if skill_region != "GL" and skill_region != region_code:
                continue
            score = self._cosine(query_embedding, emb)
            scored.append((score, skill_id, meta))

        if not scored:
            raise SkillNotFoundError(f"No skills available for region '{region_code}'.")

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)

        # Deduplicate by (output_format, intent_summary)
        seen_keys: set[tuple[str, str]] = set()
        candidates: list[SkillCandidate] = []

        for score, skill_id, meta in scored:
            if score < SIMILARITY_REVIEW_LOW:
                continue  # below minimum relevance threshold

            dedup_key = (meta.get("output_format", ""), meta.get("intent_summary", ""))
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            requires_review = SIMILARITY_REVIEW_LOW <= score < SIMILARITY_REVIEW_HIGH

            candidates.append(
                SkillCandidate(
                    skill_id=self._alias_map.resolve(skill_id),
                    score=score,
                    region_code=meta.get("region_code", "GL"),
                    output_format=meta.get("output_format", "text"),
                    intent_summary=meta.get("intent_summary", ""),
                    requires_review=requires_review,
                )
            )

            if len(candidates) >= self._top_k:
                break

        if not candidates:
            raise SkillNotFoundError(
                f"No skills scored above the minimum similarity threshold "
                f"{SIMILARITY_REVIEW_LOW} for the given query."
            )

        # Populate cache
        if cache_key:
            self._cache[cache_key] = candidates

        return candidates
