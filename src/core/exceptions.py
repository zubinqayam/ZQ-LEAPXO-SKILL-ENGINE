"""Custom exceptions for LEAPXO Skill Engine v2.1."""

from __future__ import annotations


class SkillEngineError(Exception):
    """Base exception for all skill engine errors."""


class SkillValidationError(SkillEngineError):
    """Raised when a skill fails schema or signature validation."""


class SkillNotFoundError(SkillEngineError):
    """Raised when no matching skill is found in the registry."""


class SignatureVerificationError(SkillEngineError):
    """Raised when ECDSA signature verification fails."""


class PromptFirewallError(SkillEngineError):
    """Raised when the prompt firewall blocks a request."""


class PolicyViolationError(SkillEngineError):
    """Raised when a skill or request violates a governance policy."""


class TokenBudgetExceededError(SkillEngineError):
    """Raised when the predicted token count exceeds the hard context limit."""


class CircuitBreakerOpenError(SkillEngineError):
    """Raised when a circuit breaker is in the OPEN state."""


class SandboxExecutionError(SkillEngineError):
    """Raised when L3 sandboxed execution fails."""


class ApprovalRequiredError(SkillEngineError):
    """Raised when an action requires human approval before proceeding."""


class ShadowRepairError(SkillEngineError):
    """Raised when the shadow repair pipeline cannot produce a safe patch."""


class IntentLoopError(SkillEngineError):
    """Raised when the orchestrator detects a repeated-intent loop."""
