"""End-to-end proof: a toy server that blocks after N requests, and a
client that stops hammering it once the breaker trips.

Run directly: ``python examples/flaky_server_demo.py``
No extra dependencies beyond the Python standard library.
"""
from __future__ import annotations

import http.server
import json
import threading
import time
import urllib.error
import urllib.request

from blockguard import CircuitBreaker, InCooldownError

ALLOWED_REQUESTS = 3


class FlakyHandler(http.server.BaseHTTPRequestHandler):
    count = 0
    lock = threading.Lock()

    def do_GET(self) -> None:
        with FlakyHandler.lock:
            FlakyHandler.count += 1
            n = FlakyHandler.count
        if n > ALLOWED_REQUESTS:
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b"rate limited")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "request_number": n}).encode())

    def log_message(self, *args) -> None:  # noqa: D401 -- silence per-request logging
        pass


def call_flaky_server(port: int) -> int:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main() -> None:
    server = http.server.HTTPServer(("127.0.0.1", 0), FlakyHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    breaker = CircuitBreaker(base_cooldown_s=2.0, max_cooldown_s=10.0)
    real_calls = 0
    skipped_calls = 0

    for i in range(1, 9):
        if breaker.in_cooldown("flaky"):
            skipped_calls += 1
            print(f"attempt {i}: SKIPPED (breaker open, "
                  f"{breaker.seconds_remaining('flaky'):.1f}s left) -- "
                  "no real request sent")
            continue
        status = call_flaky_server(port)
        real_calls += 1
        if status == 429:
            breaker.trip("flaky")
            print(f"attempt {i}: got 429, tripping breaker")
        else:
            breaker.clear("flaky")
            print(f"attempt {i}: got {status}, ok")
        time.sleep(0.3)

    print(f"\n{real_calls} real requests reached the server, "
          f"{skipped_calls} were skipped by the breaker once it tripped.")
    server.shutdown()


if __name__ == "__main__":
    main()
