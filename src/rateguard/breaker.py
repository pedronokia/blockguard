"""Circuit breaker for externally-imposed, undocumented rate limits.

Unlike client-side rate limiters (ratelimit, django-ratelimit, ...),
which cap how fast *you* call out, this reacts to a block the *remote
server* already imposed on you. Once a key is tripped, every caller
that checks ``in_cooldown`` first can skip the real network call
entirely instead of hammering a server that has already signaled "no" --
repeated attempts against an active block tend to extend it, not clear
it, which is the exact failure mode this class exists to avoid.

Ported and generalized from a production circuit breaker built for the
Steam Community Market (undocumented, IP-scoped, time-varying rate
limits) -- see the project README for the original story. The escalation
math and state shape are unchanged; what changed is that state now lives
on an instance (so independent breakers don't share state by accident)
instead of a single module-level dict.
"""
from __future__ import annotations

import time
from dataclasses import dataclass


class InCooldownError(Exception):
    """Raised by :meth:`CircuitBreaker.guard` when the key is tripped."""

    def __init__(self, key: str, seconds_remaining: float):
        self.key = key
        self.seconds_remaining = seconds_remaining
        super().__init__(
            f"{key!r} is in cooldown for another "
            f"{seconds_remaining:.1f}s -- call skipped"
        )


@dataclass
class _KeyState:
    strikes: int = 0
    until: float = 0.0


class CircuitBreaker:
    """Tracks per-key cooldowns with exponential backoff and a ceiling.

    Each call to :meth:`trip` doubles the next cooldown for that key
    (first strike = ``base_cooldown_s``, second = ``2x``, third = ``4x``,
    ...), capped at ``max_cooldown_s``. :meth:`clear` resets a key back
    to "never tripped" -- call it after a real success, not just after
    any response, so a key that is merely untested stays untested.

    Keys are arbitrary strings ("families" of calls that share a rate
    limit budget, e.g. one per logical endpoint) and are tracked fully
    independently: tripping one never affects another.
    """

    def __init__(self, base_cooldown_s: float = 60.0,
                 max_cooldown_s: float = 1800.0):
        if base_cooldown_s <= 0:
            raise ValueError("base_cooldown_s must be positive")
        if max_cooldown_s < base_cooldown_s:
            raise ValueError("max_cooldown_s must be >= base_cooldown_s")
        self.base_cooldown_s = base_cooldown_s
        self.max_cooldown_s = max_cooldown_s
        self._state: dict[str, _KeyState] = {}

    def trip(self, key: str) -> None:
        """Record a block for ``key``, escalating its next cooldown."""
        st = self._state.setdefault(key, _KeyState())
        st.strikes += 1
        cooldown = min(self.base_cooldown_s * (2 ** (st.strikes - 1)),
                       self.max_cooldown_s)
        st.until = time.time() + cooldown

    def clear(self, key: str) -> None:
        """Forget any cooldown/strike history for ``key``."""
        self._state.pop(key, None)

    def in_cooldown(self, key: str) -> bool:
        """True if ``key`` was tripped recently and hasn't expired yet."""
        st = self._state.get(key)
        return bool(st and time.time() < st.until)

    def seconds_remaining(self, key: str) -> float:
        """Seconds until ``key`` clears on its own (0.0 if not tripped)."""
        st = self._state.get(key)
        if st is None:
            return 0.0
        return max(0.0, st.until - time.time())

    def reset_all(self) -> None:
        """Forget every key's history. Mainly useful for tests."""
        self._state.clear()

    def guard(self, key: str) -> "_GuardContext":
        """Context manager that raises :class:`InCooldownError` instead
        of letting the wrapped call run while ``key`` is tripped."""
        return _GuardContext(self, key)


@dataclass
class _GuardContext:
    breaker: CircuitBreaker
    key: str

    def __enter__(self) -> "CircuitBreaker":
        if self.breaker.in_cooldown(self.key):
            raise InCooldownError(self.key,
                                   self.breaker.seconds_remaining(self.key))
        return self.breaker

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False
