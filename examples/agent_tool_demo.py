"""A tool an AI agent can call, guarded so the agent can't hammer a
rate-limited API.

Agents retry: when a tool call fails, the model tends to call the same tool
again, several times in a row and faster than a person would. If the API
behind the tool is already rate-limiting you, every retry can extend the
block. Here the tool checks the breaker first and answers the model with
plain text instead of sending a request it knows will be refused.

Run directly: ``python examples/agent_tool_demo.py``
No LLM, API key or network needed: a fake agent loop stands in for the
model, and the toy server from flaky_server_demo.py stands in for the API.
"""
from __future__ import annotations

import http.server
import threading

from blockguard import CircuitBreaker
from flaky_server_demo import FlakyHandler, call_flaky_server


def main() -> None:
    server = http.server.HTTPServer(("127.0.0.1", 0), FlakyHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    breaker = CircuitBreaker(base_cooldown_s=30.0, max_cooldown_s=600.0)
    real_requests = 0

    def get_price(item: str) -> str:
        """Tool exposed to the agent. Never raises; always returns text."""
        nonlocal real_requests
        if breaker.in_cooldown("prices_api"):
            wait = breaker.seconds_remaining("prices_api")
            return (f"ERROR: rate limited. Don't call get_price again for "
                    f"{wait:.0f}s; use cached data or tell the user.")
        real_requests += 1
        status = call_flaky_server(port)
        if status == 429:
            breaker.trip("prices_api")
            return "ERROR: the prices API returned 429. Don't retry yet."
        breaker.clear("prices_api")
        return f"OK: got the price for {item}"

    # Stand-in for the model: it asks for six prices and, like many agents,
    # retries a failed call up to three times without reading the error.
    tool_calls = 0
    for item in ["AK-47", "AWP", "M4A1-S", "Glock-18", "USP-S", "Desert Eagle"]:
        for attempt in range(1, 4):
            tool_calls += 1
            result = get_price(item)
            print(f"agent -> get_price({item!r}) try {attempt}: {result}")
            if result.startswith("OK"):
                break

    print(f"\nThe agent made {tool_calls} tool calls. {real_requests} reached "
          f"the API; {tool_calls - real_requests} were answered by the "
          "breaker without sending a request.")
    server.shutdown()


if __name__ == "__main__":
    main()
