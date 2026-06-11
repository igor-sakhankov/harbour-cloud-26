"""Demo client for the redirect load balancer.

It sends a series of Payments-API calls to the load balancer (default
http://localhost:8080) and, for each one, shows:

  1. the ``302`` the load balancer returns and the backend it points at, then
  2. the real API call against that backend and its response.

At the end it prints how the requests were spread across the instances, so you
can see the round-robin balancing in action.

Run the backends + LB first:
    ./lb/run_instances.sh

Then, in another terminal:
    python3 lb/demo_client.py
    python3 lb/demo_client.py --lb http://localhost:8080 --count 9

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from collections import Counter

# ANSI colors (skipped automatically when output isn't a TTY).
import sys

_TTY = sys.stdout.isatty()


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Stop urllib from auto-following redirects so we can see the 302."""

    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(NoRedirect())


def send(method: str, url: str, headers: dict | None = None, body: bytes | None = None):
    """Send one request, return (status, headers, body_text). Never raises on HTTP errors."""
    req = urllib.request.Request(url, method=method, data=body, headers=headers or {})
    try:
        with _opener.open(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8", "replace")


def call_through_lb(method: str, lb_base: str, path: str, headers=None, body=None):
    """Hit the LB, print the 302, follow it to the backend, print the result.

    Returns the backend origin (e.g. http://127.0.0.1:8082) that served it, or None.
    """
    lb_url = lb_base.rstrip("/") + path
    status, hdrs, _ = send(method, lb_url, headers=headers, body=body)

    print(f"  {c(method, '1;36')} {path}")
    if status == 302:
        location = hdrs.get("Location", "")
        print(f"    LB  -> {c('302 Found', '33')}  Location: {c(location, '32')}")
        # Follow the redirect by re-issuing the SAME method against the backend.
        b_status, _, b_body = send(method, location, headers=headers, body=body)
        origin = location.split("/api")[0] if "/api" in location else location
        snippet = b_body.strip().replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        color = "32" if 200 <= b_status < 300 else "31"
        print(f"    app -> {c(str(b_status), color)}  {snippet}")
        return origin
    elif status == 503:
        print(f"    LB  -> {c('503 No healthy backend', '31')}")
        return None
    else:
        print(f"    LB  -> {c(str(status), '31')} (unexpected)")
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Redirect LB demo client")
    parser.add_argument("--lb", default="http://localhost:8080", help="Load balancer base URL")
    parser.add_argument("--count", type=int, default=6, help="How many payments to POST")
    args = parser.parse_args(argv)

    json_headers = {"Content-Type": "application/json", "Store-Id": "store-london-01"}
    served_by = Counter()

    print(c(f"\nTalking to load balancer at {args.lb}\n", "1"))

    print(c("== POST payments (writes) ==", "1;35"))
    coffees = ["LATTE", "ESPRESSO", "CAPPUCCINO", "FLAT_WHITE", "MOCHA", "CORTADO"]
    for i in range(args.count):
        payload = {
            "coffeeType": coffees[i % len(coffees)],
            "price": round(2.5 + i * 0.25, 2),
            "currency": "EUR",
            "loyaltyCardId": f"card-{i:03d}",
        }
        origin = call_through_lb(
            "POST",
            args.lb,
            "/api/v1/payments",
            headers=json_headers,
            body=json.dumps(payload).encode(),
        )
        if origin:
            served_by[origin] += 1

    print(c("\n== GET payments for the store (reads) ==", "1;35"))
    for _ in range(3):
        origin = call_through_lb(
            "GET", args.lb, "/api/v1/payments?storeId=store-london-01"
        )
        if origin:
            served_by[origin] += 1

    print(c("\n== Distribution across instances ==", "1;35"))
    if served_by:
        for origin, n in sorted(served_by.items()):
            bar = "#" * n
            print(f"  {origin:<28} {n:>2}  {c(bar, '36')}")
    else:
        print(c("  No backend served any request — is the LB up with healthy backends?", "31"))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
