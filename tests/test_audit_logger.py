"""Tests for audit logger and approval workflow."""

import time

import pytest

from src.governance.audit_logger import (
    AuditLogger,
    ApprovalWorkflow,
    ApprovalStatus,
    RiskLevel,
)


class TestAuditLogger:
    def test_append_and_retrieve(self):
        logger = AuditLogger()
        entry = logger.log("skill_created", "system", {"skill_id": "test"})
        assert entry.event_type == "skill_created"
        entries = logger.get_entries()
        assert len(entries) == 1

    def test_chain_valid_after_multiple_entries(self):
        logger = AuditLogger()
        for i in range(5):
            logger.log(f"event_{i}", "actor", {"i": i})
        assert logger.verify_chain() is True

    def test_tampered_chain_invalid(self):
        logger = AuditLogger()
        logger.log("event", "actor", {})
        # Tamper with the last entry's hash
        logger._entries[-1].entry_hash = "deadbeef"
        assert logger.verify_chain() is False

    def test_ring_buffer_eviction(self):
        logger = AuditLogger(max_in_memory=3)
        for i in range(5):
            logger.log("ev", "a", {"i": i})
        assert len(logger.get_entries()) == 3


class TestApprovalWorkflow:
    @pytest.fixture()
    def workflow(self):
        return ApprovalWorkflow()

    def test_submit_creates_pending_request(self, workflow):
        req = workflow.submit("my-skill", validation_score=0.8)
        assert req.status == ApprovalStatus.PENDING
        assert req.risk_level == RiskLevel.MEDIUM

    def test_risk_classification(self, workflow):
        assert workflow.submit("s", 0.95).risk_level == RiskLevel.LOW
        assert workflow.submit("s", 0.8).risk_level == RiskLevel.MEDIUM
        assert workflow.submit("s", 0.6).risk_level == RiskLevel.HIGH
        assert workflow.submit("s", 0.3).risk_level == RiskLevel.CRITICAL

    def test_approve_before_cooldown_raises(self, workflow):
        req = workflow.submit("skill", validation_score=0.9)
        with pytest.raises(ValueError, match="Cooldown"):
            workflow.approve(req.request_id, approver="admin")

    def test_approve_after_cooldown(self, workflow):
        req = workflow.submit("skill", validation_score=0.9)
        # Override submitted_at to bypass cooldown in test
        workflow._requests[req.request_id].submitted_at = time.time() - 400
        approved = workflow.approve(req.request_id, approver="admin", notes="LGTM")
        assert approved.status == ApprovalStatus.APPROVED
        assert approved.approved_by == "admin"

    def test_reject(self, workflow):
        req = workflow.submit("skill", validation_score=0.5)
        rejected = workflow.reject(req.request_id, actor="reviewer", reason="unsafe")
        assert rejected.status == ApprovalStatus.REJECTED

    def test_approve_unknown_id_raises(self, workflow):
        with pytest.raises(ValueError, match="not found"):
            workflow.approve("no-such-id", approver="admin")

    def test_sla_breach_escalation(self, workflow):
        req = workflow.submit("slow-skill", validation_score=0.7)
        # Set submitted_at to > SLA threshold in the past
        workflow._requests[req.request_id].submitted_at = (
            time.time() - (workflow.SLA_HOURS * 3600 + 1)
        )
        breached = workflow.check_sla()
        assert any(b.request_id == req.request_id for b in breached)
        assert workflow._requests[req.request_id].status == ApprovalStatus.ESCALATED
