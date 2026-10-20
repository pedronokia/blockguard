"""blockguard -- a circuit breaker for undocumented, server-imposed rate limits."""
from __future__ import annotations

from .breaker import CircuitBreaker, InCooldownError

__all__ = ["CircuitBreaker", "InCooldownError"]
__version__ = "0.1.0"
