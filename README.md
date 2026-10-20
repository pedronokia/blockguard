# rateguard

A circuit breaker for rate limits the *other* server imposes on you —
not a client-side throttle for your own call rate.

## The problem

Libraries like `ratelimit` or `django-ratelimit` cap how fast *you* call
out ("no more than 10 requests/second"). That's a different problem from
what this solves: a remote server — often one with an **undocumented,
time-varying, IP-scoped** rate limit (scraping targets, flaky
third-party APIs, anything without a published SLA) — has already told
you "no" with a 429 or a silent block, and now every retry you make
*while it's still blocking you* risks **extending** the block instead of
clearing it.

This happened for real, repeatedly, building a tool against the Steam
Community Market: a single user action could fire dozens of requests at
an already-flagged endpoint, turning a minutes-long block into one that
lasted hours. `rateguard` is the fix that came out of that, generalized.

## Install

```bash
pip install rateguard
```

## Usage

```python
from rateguard import CircuitBreaker

breaker = CircuitBreaker(base_cooldown_s=60.0, max_cooldown_s=1800.0)

if breaker.in_cooldown("some_api"):
    return cached_result  # don't even try -- we already know it'll fail

resp = call_flaky_api()
if resp.status_code == 429:
    breaker.trip("some_api")   # next cooldown doubles: 60s, 120s, 240s, ... capped
else:
    breaker.clear("some_api")  # back to a clean slate after a real success
```

Or with the context-manager shortcut, which raises instead of letting you
forget the check:

```python
from rateguard import CircuitBreaker, InCooldownError

breaker = CircuitBreaker()

try:
    with breaker.guard("some_api"):
        resp = call_flaky_api()
except InCooldownError as e:
    print(f"skipping call, {e.seconds_remaining:.0f}s left")
```

Keys ("families") are independent: tripping `"inventory"` never affects
`"search"`. Use one key per logical endpoint/rate-limit budget, not one
global key for your whole app.

## Testing with rateguard in your own test suite

A breaker that lives at module/app scope persists across your whole test
session by default — a test that simulates a real block leaves a real
cooldown that leaks into the *next* test. `rateguard` ships a pytest
plugin that fixes this automatically once installed:

```python
from rateguard import CircuitBreaker
from rateguard.pytest_plugin import track

breaker = track(CircuitBreaker())  # now reset between every test, automatically
```

## What this is *not* (yet)

v0.1 is deliberately small: an in-memory, single-process breaker, no
async API, no hosted dashboard, no Redis backend for multi-process
sharing. If you need any of that, open an issue — it'll ship if there's
real demand, not before.

## License

MIT
