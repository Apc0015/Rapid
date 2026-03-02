"""
Circuit Breaker for RAPID — prevents cascading failures when downstream
services (ChromaDB, LLMs) degrade or become unavailable.

States:
  CLOSED    — normal operation, all calls go through
  OPEN      — failure threshold exceeded; all calls immediately use fallback
  HALF_OPEN — recovery test; one real call allowed to probe health

Transition rules:
  CLOSED  + failure_threshold consecutive failures → OPEN
  OPEN    + recovery_timeout seconds elapsed       → HALF_OPEN
  HALF_OPEN + success                              → CLOSED
  HALF_OPEN + failure                              → OPEN (reset timer)
"""

import time
import logging
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_CLOSED = "CLOSED"
_OPEN = "OPEN"
_HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit is OPEN and no fallback is provided."""


class CircuitBreaker:
    """
    Thread-safe 3-state circuit breaker.

    Usage::

        cb = CircuitBreaker("chromadb", failure_threshold=5, recovery_timeout=60)

        result = cb.call(
            chromadb_search,
            query_text, top_k,
            fallback=bm25_fallback_fn,
        )
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = _CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state

    def call(
        self,
        func: Callable,
        *args,
        fallback: Optional[Callable] = None,
        **kwargs,
    ) -> Any:
        """
        Execute *func* with circuit-breaker protection.

        Args:
            func:     The primary function to call.
            *args:    Positional arguments forwarded to func (and fallback).
            fallback: Optional callable with the same signature as func.
                      Called automatically when the circuit is OPEN or func fails.
            **kwargs: Keyword arguments forwarded to func (and fallback).

        Returns:
            Result of func on success, or result of fallback on failure/open.

        Raises:
            CircuitBreakerOpenError: if circuit is OPEN and no fallback provided.
            Exception: re-raised from func if no fallback and circuit is CLOSED.
        """
        with self._lock:
            current_state = self._get_state()

        if current_state == _OPEN:
            logger.warning("CircuitBreaker[%s] OPEN — using fallback", self.name)
            return self._run_fallback(fallback, *args, **kwargs)

        # CLOSED or HALF_OPEN: attempt the real call
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure(exc)
            logger.warning(
                "CircuitBreaker[%s] failure #%d: %s",
                self.name, self._failure_count, exc,
            )
            return self._run_fallback(fallback, *args, **kwargs)

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._state = _CLOSED
            self._failure_count = 0
            self._last_failure_time = None
        logger.info("CircuitBreaker[%s] manually reset to CLOSED", self.name)

    # ── State machine ──────────────────────────────────────────────────────────

    def _get_state(self) -> str:
        """Return current effective state, handling OPEN → HALF_OPEN transition."""
        if self._state == _OPEN:
            if (
                self._last_failure_time is not None
                and time.monotonic() - self._last_failure_time >= self.recovery_timeout
            ):
                self._state = _HALF_OPEN
                logger.info(
                    "CircuitBreaker[%s] OPEN → HALF_OPEN (probing recovery)", self.name
                )
        return self._state

    def _on_success(self) -> None:
        with self._lock:
            if self._state == _HALF_OPEN:
                logger.info(
                    "CircuitBreaker[%s] HALF_OPEN → CLOSED (recovery confirmed)", self.name
                )
            self._state = _CLOSED
            self._failure_count = 0
            self._last_failure_time = None

    def _on_failure(self, exc: Exception) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == _HALF_OPEN or self._failure_count >= self.failure_threshold:
                self._state = _OPEN
                logger.error(
                    "CircuitBreaker[%s] → OPEN after %d failure(s): %s",
                    self.name, self._failure_count, exc,
                )

    # ── Fallback helper ────────────────────────────────────────────────────────

    @staticmethod
    def _run_fallback(
        fallback: Optional[Callable], *args, **kwargs
    ) -> Any:
        if fallback is not None:
            try:
                return fallback(*args, **kwargs)
            except Exception as fb_exc:
                logger.error("CircuitBreaker fallback also failed: %s", fb_exc)
                return []
        raise CircuitBreakerOpenError(
            "Circuit breaker is OPEN and no fallback was provided."
        )
