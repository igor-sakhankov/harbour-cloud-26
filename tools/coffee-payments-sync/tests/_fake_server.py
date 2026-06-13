"""In-process fake of the StarHarbour payments API for tests.

Mimics the real contract:
- POST /api/v1/payments with Store-Id + optional Idempotency-Key headers.
- 201 on first sight of (storeId, idempotencyKey); 200 replay afterwards.
- 400 ProblemDetail when the JSON body fails a basic check.

Fault injection: `fail_times` makes the next N requests fail before any succeed,
either by HTTP 500 or by sleeping past the client timeout.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeCentral:
    def __init__(self, fail_times=0, fail_mode="500", fail_delay=2.0):
        self.payments = {}          # (storeId, idemKey) -> paymentId
        self.requests_seen = 0      # every POST attempt that reached us
        self.created_count = 0
        self._remaining_failures = fail_times
        self._fail_mode = fail_mode  # "500" or "timeout"
        self._fail_delay = fail_delay
        self._counter = 0
        self._lock = threading.Lock()
        self._server = None
        self._thread = None

    @property
    def base_url(self):
        host, port = self._server.server_address
        return f"http://127.0.0.1:{port}"

    def start(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                # A client that timed out may have closed the socket while we
                # were sleeping (timeout fault injection); writing to it then
                # raises. That is expected in tests, so swallow it quietly.
                try:
                    outer._handle(self)
                except (BrokenPipeError, ConnectionError):
                    pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    def _handle(self, h):
        with self._lock:
            self.requests_seen += 1
            inject = self._remaining_failures > 0
            if inject:
                self._remaining_failures -= 1

        # Always drain the request body first so responding (even with an error)
        # never leaves an unread body that would reset the connection.
        length = int(h.headers.get("Content-Length", 0))
        body = h.rfile.read(length) if length else b"{}"

        if inject:
            if self._fail_mode == "timeout":
                time.sleep(self._fail_delay)
                # fall through and answer; the client should have timed out
            else:
                payload = b'{"detail":"injected failure"}'
                h.send_response(500)
                h.send_header("Content-Type", "application/json")
                h.send_header("Content-Length", str(len(payload)))
                h.end_headers()
                h.wfile.write(payload)
                return

        try:
            payload = json.loads(body)
        except ValueError:
            payload = {}

        store_id = h.headers.get("Store-Id")
        idem = h.headers.get("Idempotency-Key")

        if not payload.get("coffeeType") or not payload.get("price"):
            h.send_response(400)
            h.send_header("Content-Type", "application/problem+json")
            h.end_headers()
            h.wfile.write(b'{"detail":"price must be greater than zero"}')
            return

        key = (store_id, idem)
        with self._lock:
            if key in self.payments:
                payment_id, status = self.payments[key], 200
            else:
                self._counter += 1
                payment_id = f"pay-{self._counter}"
                self.payments[key] = payment_id
                self.created_count += 1
                status = 201
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        h.end_headers()
        h.wfile.write(json.dumps({"paymentId": payment_id, "storeId": store_id}).encode())
