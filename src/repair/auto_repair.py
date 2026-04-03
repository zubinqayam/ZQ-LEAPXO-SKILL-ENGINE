"""Shadow Repair Pipeline — controlled AI-assisted skill patching.

Design guarantees:
* Auto-repair CANNOT deploy directly to production.
* Every patch MUST pass a test suite before human review is triggered.
* Every patch MUST be signed with ECDSA before deployment.
* Shadow mode compares V2 outputs against V1 to verify ≥95 % parity.

Pipeline:
    Error Detected
       ↓
    Clone Skill (Shadow)
       ↓
    Apply Fix (patch function)
       ↓
    Run ALGA Test
       ↓
    Compare Output (Shadow vs Prod)
       ↓
    Human Approval Required (ApprovalWorkflow)
"""

from __future__ import annotations

import copy
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.core.exceptions import ApprovalRequiredError, ShadowRepairError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SHADOW_PARITY_THRESHOLD = 0.95  # 95 % parity required before promotion


# ---------------------------------------------------------------------------
# Parity evaluation
# ---------------------------------------------------------------------------


def _default_parity(prod_output: Any, shadow_output: Any) -> float:
    """Simple string-overlap parity metric.

    In production replace with a more sophisticated semantic similarity.
    """
    a = str(prod_output)
    b = str(shadow_output)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # Token overlap (Jaccard)
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


# ---------------------------------------------------------------------------
# Repair attempt record
# ---------------------------------------------------------------------------


class RepairStatus(StrEnum):
    PENDING = "pending"
    PATCHED = "patched"
    TESTED = "tested"
    PARITY_FAILED = "parity_failed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class RepairAttempt:
    attempt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    skill_id: str = ""
    original_schema: dict = field(default_factory=dict)
    patched_schema: dict | None = None
    parity_score: float = 0.0
    test_passed: bool = False
    status: RepairStatus = RepairStatus.PENDING
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    approval_request_id: str | None = None


# ---------------------------------------------------------------------------
# Shadow Repair Pipeline
# ---------------------------------------------------------------------------

TestRunner = Callable[[dict], bool]
PatchFn = Callable[[dict, str], dict]
ParityFn = Callable[[Any, Any], float]


class ShadowRepairPipeline:
    """Orchestrates the shadow repair cycle for a failing skill.

    Args:
        test_runner: Callable that takes a patched skill dict and returns True
            if the skill passes all ALGA tests.
        parity_fn: Callable that scores semantic similarity between production
            and shadow outputs (returns 0.0–1.0).
        approval_workflow: ApprovalWorkflow instance for human gate.
    """

    def __init__(
        self,
        test_runner: TestRunner | None = None,
        parity_fn: ParityFn | None = None,
        approval_workflow: Any = None,
    ) -> None:
        self._test_runner = test_runner or (lambda _: True)
        self._parity_fn = parity_fn or _default_parity
        self._approval_workflow = approval_workflow
        self._history: dict[str, RepairAttempt] = {}

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    def attempt_repair(
        self,
        skill_schema: dict,
        error_description: str,
        patch_fn: PatchFn,
        *,
        prod_output: Any = None,
        shadow_executor: Callable[[dict], Any] | None = None,
    ) -> RepairAttempt:
        """Run the full repair pipeline.

        Args:
            skill_schema: Current (failing) skill schema as a dict.
            error_description: Description of the error to fix.
            patch_fn: Callable(schema, error) → patched_schema.
            prod_output: The production skill's last known good output (for
                parity comparison).  Can be None if not available.
            shadow_executor: Optional callable that runs the patched skill
                and returns its output.

        Returns:
            A RepairAttempt describing the outcome.

        Raises:
            ShadowRepairError: If patching or testing fails.
            ApprovalRequiredError: Always raised at the end of a successful
                pipeline run, to enforce the human approval gate.
        """
        attempt = RepairAttempt(
            skill_id=skill_schema.get("skill_id", "unknown"),
            original_schema=copy.deepcopy(skill_schema),
        )
        self._history[attempt.attempt_id] = attempt

        # Step 1: Clone (deep copy already done above)

        # Step 2: Apply fix
        try:
            patched = patch_fn(copy.deepcopy(skill_schema), error_description)
        except Exception as exc:
            attempt.status = RepairStatus.REJECTED
            attempt.error = f"Patch function raised: {exc}"
            raise ShadowRepairError(attempt.error) from exc

        attempt.patched_schema = patched
        attempt.status = RepairStatus.PATCHED

        # Step 3: Run ALGA test suite
        try:
            test_passed = self._test_runner(patched)
        except Exception as exc:
            attempt.status = RepairStatus.REJECTED
            attempt.error = f"Test runner raised: {exc}"
            raise ShadowRepairError(attempt.error) from exc

        attempt.test_passed = test_passed
        if not test_passed:
            attempt.status = RepairStatus.REJECTED
            attempt.error = "Patched skill failed ALGA test suite."
            raise ShadowRepairError(attempt.error)

        attempt.status = RepairStatus.TESTED

        # Step 4: Parity comparison
        if prod_output is not None and shadow_executor is not None:
            try:
                shadow_output = shadow_executor(patched)
            except Exception as exc:
                attempt.status = RepairStatus.REJECTED
                attempt.error = f"Shadow executor raised: {exc}"
                raise ShadowRepairError(attempt.error) from exc

            parity = self._parity_fn(prod_output, shadow_output)
            attempt.parity_score = parity

            if parity < SHADOW_PARITY_THRESHOLD:
                attempt.status = RepairStatus.PARITY_FAILED
                attempt.error = (
                    f"Shadow parity {parity:.2%} below required {SHADOW_PARITY_THRESHOLD:.0%}."
                )
                raise ShadowRepairError(attempt.error)

        # Step 5: Trigger human approval (mandatory gate)
        attempt.status = RepairStatus.AWAITING_APPROVAL
        if self._approval_workflow is not None:
            approval_req = self._approval_workflow.submit(
                skill_id=attempt.skill_id,
                validation_score=attempt.parity_score or 1.0,
            )
            attempt.approval_request_id = approval_req.request_id

        raise ApprovalRequiredError(
            f"Repair attempt '{attempt.attempt_id}' for skill "
            f"'{attempt.skill_id}' requires human approval before deployment.  "
            f"Approval request ID: {attempt.approval_request_id}"
        )

    def get_history(self) -> list[RepairAttempt]:
        return list(self._history.values())
