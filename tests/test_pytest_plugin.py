"""Dogfoods blockguard.pytest_plugin: a breaker tracked via ``track()`` must
come back clean in the NEXT test, even though a previous test tripped it.
Order matters here -- these two tests rely on running in file order,
which pytest does by default within a single file."""
from __future__ import annotations

from blockguard import CircuitBreaker
from blockguard.pytest_plugin import track

shared = track(CircuitBreaker(base_cooldown_s=60.0))


def test_a_trips_the_shared_breaker():
    assert shared.in_cooldown("x") is False
    shared.trip("x")
    assert shared.in_cooldown("x") is True


def test_b_sees_a_clean_breaker():
    # If the autouse fixture in pytest_plugin.py didn't reset `shared`
    # between tests, this would see the cooldown test_a_ left behind.
    assert shared.in_cooldown("x") is False
