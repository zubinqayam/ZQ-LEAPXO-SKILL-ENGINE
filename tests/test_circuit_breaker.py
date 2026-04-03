"""Tests for the circuit breaker system."""

import time

import pytest
from src.core.exceptions import CircuitBreakerOpenError, IntentLoopError
from src.execution.circuit_breaker import (
    BreakerState,
    CircuitBreaker,
    CircuitBreakerRegistry,
)


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == BreakerState.CLOSED

    def test_opens_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == BreakerState.OPEN

    def test_assert_closed_raises_when_open(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        with pytest.raises(CircuitBreakerOpenError):
            cb.assert_closed()

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state == BreakerState.OPEN
        time.sleep(0.02)
        assert cb.call_allowed() is True
        assert cb.state == BreakerState.HALF_OPEN

    def test_closes_after_successes(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01, success_threshold=2)
        cb.record_failure()
        time.sleep(0.02)
        cb.call_allowed()  # transition to HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == BreakerState.CLOSED

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # Should still be closed and failure count reset
        assert cb.state == BreakerState.CLOSED


class TestCircuitBreakerRegistry:
    def test_get_or_create_same_instance(self):
        registry = CircuitBreakerRegistry()
        cb1 = registry.get_or_create("skill-a")
        cb2 = registry.get_or_create("skill-a")
        assert cb1 is cb2

    def test_intent_loop_detection(self):
        registry = CircuitBreakerRegistry()
        with pytest.raises(IntentLoopError):
            for _ in range(3):
                registry.record_intent("session-1", "same intent")

    def test_different_intents_no_loop(self):
        registry = CircuitBreakerRegistry()
        registry.record_intent("session-2", "intent A")
        registry.record_intent("session-2", "intent B")
        registry.record_intent("session-2", "intent C")
        # No exception expected

    def test_depth_limit(self):
        registry = CircuitBreakerRegistry()
        with pytest.raises(CircuitBreakerOpenError, match="depth"):
            registry.check_depth(4)

    def test_chain_length_limit(self):
        registry = CircuitBreakerRegistry()
        with pytest.raises(CircuitBreakerOpenError, match="chain"):
            registry.check_chain_length(6)

    def test_reset(self):
        registry = CircuitBreakerRegistry()
        cb = registry.get_or_create("reset-test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == BreakerState.OPEN
        registry.reset("reset-test")
        cb2 = registry.get_or_create("reset-test")
        assert cb2.state == BreakerState.CLOSED
