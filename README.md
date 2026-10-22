# blockguard

[![tests](https://github.com/pedronokia/blockguard/actions/workflows/tests.yml/badge.svg)](https://github.com/pedronokia/blockguard/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/blockguard)](https://pypi.org/project/blockguard/)

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
lasted hours. `blockguard` is the fix that came out of that, generalized.

## Install

```bash
pip install blockguard
```

## Usage

```python
from blockguard import CircuitBreaker

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
from blockguard import CircuitBreaker, InCooldownError

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

## Using it inside an AI agent's tools

Agents retry. When a tool call fails, the model tends to call the same tool
again, several times in a row and faster than a person would. If the API
behind the tool is already rate-limiting you, every retry can extend the
block. Check the breaker inside the tool and give the model a plain answer
instead of sending the request:

```python
from blockguard import CircuitBreaker

breaker = CircuitBreaker()

def get_price(item: str) -> str:
    """Tool exposed to the agent. Never raises; always returns text."""
    if breaker.in_cooldown("prices_api"):
        wait = breaker.seconds_remaining("prices_api")
        return f"Rate limited. Don't call get_price again for {wait:.0f}s."
    resp = call_prices_api(item)
    if resp.status_code == 429:
        breaker.trip("prices_api")
        return "The prices API returned 429. Don't retry yet."
    breaker.clear("prices_api")
    return resp.text
```

The message helps a model that reads it, and the check protects you from
one that doesn't: no request reaches the API until the cooldown ends, however
many times the agent calls the tool. Since the tool is a plain function that
returns text, it fits frameworks that expose Python functions as tools.

`examples/agent_tool_demo.py` runs this against a local toy server with a
fake agent loop that retries every failure three times. No LLM or API key is
needed. In that run, the agent makes 12 tool calls and 4 reach the API.

## Testing with blockguard in your own test suite

A breaker that lives at module/app scope persists across your whole test
session by default — a test that simulates a real block leaves a real
cooldown that leaks into the *next* test. `blockguard` ships a pytest
plugin that fixes this automatically once installed:

```python
from blockguard import CircuitBreaker
from blockguard.pytest_plugin import track

breaker = track(CircuitBreaker())  # now reset between every test, automatically
```

## Why not an existing circuit breaker library

General-purpose Python circuit breakers (`fabfuel/circuitbreaker`, for
example) trip on a failure *count* and reopen after a fixed recovery
timeout — built for "is this service healthy", not for a block that gets
*longer* the more you poke it. `blockguard` doubles the cooldown on each
repeated trip (capped), because that's the actual shape of the problem:
retrying during a block tends to extend it, so the backoff needs to grow
with it. It's also zero-dependency and keyed per endpoint out of the box,
rather than a general toolkit (like `kstlib`, which bundles a breaker with
a separate token-bucket limiter) you'd configure down to this shape.

## What this is *not* (yet)

v0.1 is deliberately small: an in-memory, single-process breaker, no
async API, no hosted dashboard, no Redis backend for multi-process
sharing. If you need any of that, open an issue — it'll ship if there's
real demand, not before.

## License

MIT
