"""Optional pytest fixture for resetting CircuitBreaker state between tests.

Why this exists: a breaker instance that lives at module scope (the
common pattern -- one shared breaker per app) persists across a whole
pytest session. A test that simulates a real block (calls ``trip()``)
leaves a real multi-minute cooldown active, which then leaks into the
*next* test and short-circuits it regardless of that test's own mocks.
This bit a real production codebase hard enough to break 13 tests in a
chain before the root cause was found -- this fixture is that fix,
shipped as part of the library instead of hand-rolled per project.

Usage: add ``blockguard`` to your pytest plugins (most test setups pick
it up automatically once the package is installed, since it registers
via the ``pytest11`` entry point declared in ``pyproject.toml``), then
depend on breakers via a fixture of your own that also clears them, or
track instances explicitly:

    from blockguard.pytest_plugin import track

    breaker = CircuitBreaker()
    track(breaker)  # now reset_all() is called on it before/after each test
"""
from __future__ import annotations

from typing import Iterator

import pytest

from .breaker import CircuitBreaker

_tracked: list[CircuitBreaker] = []


def track(breaker: CircuitBreaker) -> CircuitBreaker:
    """Register ``breaker`` so the autouse fixture below resets it.

    Returns the same breaker, so this can wrap a module-level definition:
    ``breaker = track(CircuitBreaker())``.
    """
    _tracked.append(breaker)
    return breaker


@pytest.fixture(autouse=True)
def _reset_tracked_breakers() -> Iterator[None]:
    for b in _tracked:
        b.reset_all()
    yield
    for b in _tracked:
        b.reset_all()
