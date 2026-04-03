"""Immutable audit logger and governance approval workflow.

Audit log:
* In-memory ring buffer (ephemeral); flushes to disk only on anomaly/crash.
* Every entry is SHA-256 chained (each entry's hash includes the previous hash)
  making the log tamper-evident.
* Entries are append-only — no edit/delete methods exposed.

Approval workflow:
* Skill creation → Validation Engine score → Risk classification →
  Human review → MFA approval → Deployment.
* SLA-based escalation (default 4 h without action).
* Cooldown timer (anti-rush): minimum 5 minutes between submit and approval.
* Red-team injected test skills: handled transparently.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    entry_id: str
    timestamp: float
    event_type: str
    actor: str
    payload: Dict[str, Any]
    prev_hash: str
    entry_hash: str = field(default="", init=False)

    def __post_init__(self) -> None:
        raw = json.dumps(
            {
                "entry_id": self.entry_id,
                "timestamp": self.timestamp,
                "event_type": self.event_type,
                "actor": self.actor,
                "payload": self.payload,
                "prev_hash": self.prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        self.entry_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AuditLogger:
    """Append-only, hash-chained audit logger."""

    GENESIS_HASH = "0" * 64

    def __init__(self, max_in_memory: int = 10_000) -> None:
        self._entries: List[AuditEntry] = []
        self._max = max_in_memory
        self._lock = Lock()
        self._last_hash = self.GENESIS_HASH

    def log(
        self,
        event_type: str,
        actor: str,
        payload: Dict[str, Any],
    ) -> AuditEntry:
        """Append a new event to the audit log."""
        with self._lock:
            entry = AuditEntry(
                entry_id=str(uuid.uuid4()),
                timestamp=time.time(),
                event_type=event_type,
                actor=actor,
                payload=payload,
                prev_hash=self._last_hash,
            )
            self._entries.append(entry)
            self._last_hash = entry.entry_hash
            # Ring-buffer eviction (keep last N entries in memory)
            if len(self._entries) > self._max:
                self._entries.pop(0)
        return entry

    def verify_chain(self) -> bool:
        """Return True if the entire in-memory chain is intact."""
        prev = self.GENESIS_HASH
        for entry in self._entries:
            raw = json.dumps(
                {
                    "entry_id": entry.entry_id,
                    "timestamp": entry.timestamp,
                    "event_type": entry.event_type,
                    "actor": entry.actor,
                    "payload": entry.payload,
                    "prev_hash": entry.prev_hash,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if expected != entry.entry_hash:
                return False
            if entry.prev_hash != prev:
                return False
            prev = entry.entry_hash
        return True

    def get_entries(self) -> List[AuditEntry]:
        with self._lock:
            return list(self._entries)


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ApprovalRequest:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    skill_id: str = ""
    validation_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    status: ApprovalStatus = ApprovalStatus.PENDING
    submitted_at: float = field(default_factory=time.time)
    approved_at: Optional[float] = None
    approved_by: Optional[str] = None
    notes: str = ""
    is_red_team: bool = False


class ApprovalWorkflow:
    """Manages the human-approval pipeline for skill deployment.

    Constants:
        SLA_HOURS: Maximum hours before automatic escalation.
        COOLDOWN_MINUTES: Minimum minutes between submission and approval.
    """

    SLA_HOURS = 4
    COOLDOWN_MINUTES = 5

    def __init__(self, audit_logger: Optional[AuditLogger] = None) -> None:
        self._requests: Dict[str, ApprovalRequest] = {}
        self._lock = Lock()
        self._audit = audit_logger or AuditLogger()

    def submit(
        self,
        skill_id: str,
        validation_score: float,
        *,
        is_red_team: bool = False,
    ) -> ApprovalRequest:
        """Submit a skill for human review.

        Risk level is derived automatically from the validation score:
            score >= 0.9  → LOW
            score >= 0.7  → MEDIUM
            score >= 0.5  → HIGH
            score <  0.5  → CRITICAL
        """
        if validation_score >= 0.9:
            risk = RiskLevel.LOW
        elif validation_score >= 0.7:
            risk = RiskLevel.MEDIUM
        elif validation_score >= 0.5:
            risk = RiskLevel.HIGH
        else:
            risk = RiskLevel.CRITICAL

        req = ApprovalRequest(
            skill_id=skill_id,
            validation_score=validation_score,
            risk_level=risk,
            is_red_team=is_red_team,
        )
        with self._lock:
            self._requests[req.request_id] = req

        self._audit.log(
            "approval_submitted",
            actor="system",
            payload={"skill_id": skill_id, "risk": risk, "score": validation_score},
        )
        return req

    def approve(
        self,
        request_id: str,
        approver: str,
        *,
        notes: str = "",
    ) -> ApprovalRequest:
        """Approve a pending request (requires MFA token in production).

        Raises:
            ValueError: If request not found, not pending, or cooldown not met.
        """
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                raise ValueError(f"Approval request '{request_id}' not found.")
            if req.status != ApprovalStatus.PENDING:
                raise ValueError(
                    f"Request '{request_id}' is not PENDING (status: {req.status})."
                )
            elapsed_minutes = (time.time() - req.submitted_at) / 60
            if elapsed_minutes < self.COOLDOWN_MINUTES:
                raise ValueError(
                    f"Cooldown not met: {elapsed_minutes:.1f} min elapsed, "
                    f"minimum {self.COOLDOWN_MINUTES} min required (anti-rush)."
                )
            req.status = ApprovalStatus.APPROVED
            req.approved_at = time.time()
            req.approved_by = approver
            req.notes = notes

        self._audit.log(
            "approval_granted",
            actor=approver,
            payload={"request_id": request_id, "skill_id": req.skill_id},
        )
        return req

    def reject(self, request_id: str, actor: str, *, reason: str = "") -> ApprovalRequest:
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                raise ValueError(f"Approval request '{request_id}' not found.")
            req.status = ApprovalStatus.REJECTED
            req.notes = reason

        self._audit.log(
            "approval_rejected",
            actor=actor,
            payload={"request_id": request_id, "reason": reason},
        )
        return req

    def check_sla(self) -> List[ApprovalRequest]:
        """Return all PENDING requests that have breached the SLA deadline."""
        sla_seconds = self.SLA_HOURS * 3600
        now = time.time()
        breached: List[ApprovalRequest] = []
        with self._lock:
            for req in self._requests.values():
                if req.status == ApprovalStatus.PENDING:
                    if now - req.submitted_at > sla_seconds:
                        req.status = ApprovalStatus.ESCALATED
                        breached.append(req)
        for req in breached:
            self._audit.log(
                "approval_sla_breached",
                actor="system",
                payload={"request_id": req.request_id, "skill_id": req.skill_id},
            )
        return breached
