"""Circuit Breaker System — tiered failure isolation.

Implements a three-state machine per skill/layer:
  CLOSED   → normal operation
  OPEN     → failing; fast-fail without attempting execution
  HALF_OPEN → trial run to probe recovery

Tiers:
  L1 Failure  → Retry with a different skill
  L2 Failure  → Prune instructions + reload
  L3 Failure  → Isolate the specific skill
  System      → Partial degrade (NOT full stop)

Safety limits:
  * Depth limit = 3 (recursion chain)
  * Max skill chain = 5
  * Intent loop detection: 3 identical intents → abort
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Deque, Dict, Optional

from src.core.exceptions import CircuitBreakerOpenError, IntentLoopError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_DEPTH = 3
MAX_SKILL_CHAIN = 5
INTENT_LOOP_THRESHOLD = 3

DEFAULT_FAILURE_THRESHOLD = 3      # failures before OPEN
DEFAULT_RECOVERY_TIMEOUT = 30.0    # seconds before trying HALF_OPEN
DEFAULT_SUCCESS_THRESHOLD = 2      # successes in HALF_OPEN before CLOSED


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerStats:
    state: BreakerState = BreakerState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0


# ---------------------------------------------------------------------------
# Per-skill circuit breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Single circuit breaker for one skill or layer."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: float = DEFAULT_RECOVERY_TIMEOUT,
        success_threshold: int = DEFAULT_SUCCESS_THRESHOLD,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold
        self._stats = BreakerStats()
        self._lock = Lock()

    @property
    def state(self) -> BreakerState:
        return self._stats.state

    def call_allowed(self) -> bool:
        """Return True if a call should be attempted."""
        with self._lock:
            if self._stats.state == BreakerState.OPEN:
                elapsed = time.monotonic() - self._stats.last_failure_time
                if elapsed >= self._recovery_timeout:
                    self._stats.state = BreakerState.HALF_OPEN
                    self._stats.success_count = 0
                    return True
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._stats.state == BreakerState.HALF_OPEN:
                self._stats.success_count += 1
                if self._stats.success_count >= self._success_threshold:
                    self._stats.state = BreakerState.CLOSED
                    self._stats.failure_count = 0
            elif self._stats.state == BreakerState.CLOSED:
                self._stats.failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self._stats.failure_count += 1
            self._stats.last_failure_time = time.monotonic()
            if self._stats.failure_count >= self._failure_threshold:
                self._stats.state = BreakerState.OPEN

    def assert_closed(self) -> None:
        """Raise CircuitBreakerOpenError if the breaker is open."""
        if not self.call_allowed():
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN — "
                "service degraded, fast-failing without execution."
            )


# ---------------------------------------------------------------------------
# Registry of all breakers + guard utilities
# ---------------------------------------------------------------------------

class CircuitBreakerRegistry:
    """Manages all circuit breakers and cross-cutting safety limits."""

    def __init__(self) -> None:
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = Lock()
        # Intent loop detection: maps session_id → deque of recent intents
        self._intent_history: Dict[str, Deque[str]] = defaultdict(
            lambda: deque(maxlen=INTENT_LOOP_THRESHOLD + 1)
        )

    def get_or_create(self, name: str, **kwargs) -> CircuitBreaker:
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, **kwargs)
            return self._breakers[name]

    def record_intent(self, session_id: str, intent: str) -> None:
        """Record an intent for a session and raise IntentLoopError on loop.

        Raises:
            IntentLoopError: If the same intent has been seen
                INTENT_LOOP_THRESHOLD times consecutively.
        """
        history = self._intent_history[session_id]
        history.append(intent)
        if len(history) >= INTENT_LOOP_THRESHOLD and len(set(history)) == 1:
            raise IntentLoopError(
                f"Intent loop detected in session '{session_id}': "
                f"'{intent}' repeated {INTENT_LOOP_THRESHOLD} times — aborting."
            )

    def check_depth(self, depth: int) -> None:
        """Raise CircuitBreakerOpenError if recursion depth exceeds MAX_DEPTH."""
        if depth > MAX_DEPTH:
            raise CircuitBreakerOpenError(
                f"Execution depth {depth} exceeds maximum allowed depth {MAX_DEPTH}."
            )

    def check_chain_length(self, chain_length: int) -> None:
        """Raise CircuitBreakerOpenError if skill chain exceeds MAX_SKILL_CHAIN."""
        if chain_length > MAX_SKILL_CHAIN:
            raise CircuitBreakerOpenError(
                f"Skill chain length {chain_length} exceeds maximum allowed {MAX_SKILL_CHAIN}."
            )

    def reset(self, name: str) -> None:
        """Reset a named circuit breaker to CLOSED state."""
        with self._lock:
            if name in self._breakers:
                self._breakers[name] = CircuitBreaker(name)


# Singleton registry
_registry = CircuitBreakerRegistry()


def get_registry() -> CircuitBreakerRegistry:
    """Return the global CircuitBreakerRegistry singleton."""
    return _registry
