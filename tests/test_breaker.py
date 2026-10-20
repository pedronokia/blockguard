"""Tests for CircuitBreaker -- ported from the proven Steam-market breaker's
own test suite (same cases, generalized away from a specific domain)."""
from __future__ import annotations

import time

import pytest

from blockguard import CircuitBreaker, InCooldownError


def make_breaker(base=0.05, cap=0.2):
    # Tiny real durations (seconds, not minutes) so the suite stays fast
    # without ever mocking time.time() -- the real clock is simple enough
    # here that faking it would just add a second way to get it wrong.
    return CircuitBreaker(base_cooldown_s=base, max_cooldown_s=cap)


def test_no_history_means_not_in_cooldown():
    b = make_breaker()
    assert b.in_cooldown("x") is False
    assert b.seconds_remaining("x") == 0.0


def test_one_strike_trips_cooldown():
    b = make_breaker()
    b.trip("x")
    assert b.in_cooldown("x") is True
    assert b.seconds_remaining("x") > 0.0


def test_escalation_doubles_each_strike():
    b = make_breaker(base=1.0, cap=1000.0)
    b.trip("x")
    first = b.seconds_remaining("x")
    b.trip("x")
    second = b.seconds_remaining("x")
    assert second > first


def test_escalation_caps_at_max():
    b = make_breaker(base=1.0, cap=10.0)
    for _ in range(20):
        b.trip("x")
    assert b.seconds_remaining("x") <= 10.0 + 0.01


def test_clear_resets_cooldown():
    b = make_breaker()
    b.trip("x")
    b.clear("x")
    assert b.in_cooldown("x") is False


def test_keys_are_independent():
    b = make_breaker()
    b.trip("inventory")
    assert b.in_cooldown("inventory") is True
    assert b.in_cooldown("resolve") is False


def test_cooldown_expires_on_its_own():
    b = make_breaker(base=0.05, cap=0.05)
    b.trip("x")
    assert b.in_cooldown("x") is True
    time.sleep(0.08)
    assert b.in_cooldown("x") is False


def test_reset_all_clears_every_key():
    b = make_breaker()
    b.trip("a")
    b.trip("b")
    b.reset_all()
    assert b.in_cooldown("a") is False
    assert b.in_cooldown("b") is False


def test_guard_raises_when_tripped():
    b = make_breaker()
    b.trip("x")
    with pytest.raises(InCooldownError):
        with b.guard("x"):
            pytest.fail("should never reach the body")


def test_guard_passes_through_when_clear():
    b = make_breaker()
    ran = False
    with b.guard("x"):
        ran = True
    assert ran is True


def test_invalid_base_cooldown_rejected():
    with pytest.raises(ValueError):
        CircuitBreaker(base_cooldown_s=0)


def test_max_below_base_rejected():
    with pytest.raises(ValueError):
        CircuitBreaker(base_cooldown_s=10, max_cooldown_s=5)
