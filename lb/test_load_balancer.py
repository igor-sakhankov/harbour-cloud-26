"""Tests for the redirect load balancer.

Run with:  python3 -m unittest discover -s lb -v
       or:  python3 lb/test_load_balancer.py

Stdlib only — no install step.
"""

from __future__ import annotations

import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from load_balancer import (
    BackendPool,
    Config,
    HealthChecker,
    LoadBalancer,
    RandomStrategy,
    RoundRobinStrategy,
    build,
    build_strategy,
)


class ConfigTests(unittest.TestCase):
    def test_from_dict_strips_trailing_slashes(self):
        cfg = Config.from_dict({"backends": ["http://a:8081/", "http://b:8082"]})
        self.assertEqual(cfg.backends, ["http://a:8081", "http://b:8082"])

    def test_unknown_keys_ignored(self):
        cfg = Config.from_dict({"backends": [], "nonsense": 123, "port": 9000})
        self.assertEqual(cfg.port, 9000)
        self.assertFalse(hasattr(cfg, "nonsense"))


class BackendPoolTests(unittest.TestCase):
    def test_healthy_filters_unhealthy(self):
        pool = BackendPool(["http://a", "http://b", "http://c"])
        pool.set_health("http://b", False)
        healthy = [b.url for b in pool.healthy()]
        self.assertEqual(healthy, ["http://a", "http://c"])

    def test_replace_preserves_health_for_surviving_urls(self):
        pool = BackendPool(["http://a", "http://b"])
        pool.set_health("http://a", False)
        pool.replace(["http://a", "http://c"])
        states = {b.url: b.healthy for b in pool.all()}
        self.assertFalse(states["http://a"])  # preserved
        self.assertTrue(states["http://c"])  # new -> healthy by default
        self.assertNotIn("http://b", states)  # removed


class RoundRobinTests(unittest.TestCase):
    def test_cycles_evenly(self):
        pool = BackendPool(["http://a", "http://b", "http://c"])
        lb = LoadBalancer(pool, RoundRobinStrategy())
        picks = [lb.next_backend().url for _ in range(6)]
        self.assertEqual(
            picks,
            ["http://a", "http://b", "http://c", "http://a", "http://b", "http://c"],
        )

    def test_skips_unhealthy_backend(self):
        pool = BackendPool(["http://a", "http://b", "http://c"])
        pool.set_health("http://b", False)
        lb = LoadBalancer(pool, RoundRobinStrategy())
        picks = {lb.next_backend().url for _ in range(10)}
        self.assertEqual(picks, {"http://a", "http://c"})

    def test_returns_none_when_all_unhealthy(self):
        pool = BackendPool(["http://a", "http://b"])
        for url in ("http://a", "http://b"):
            pool.set_health(url, False)
        lb = LoadBalancer(pool, RoundRobinStrategy())
        self.assertIsNone(lb.next_backend())


class RandomStrategyTests(unittest.TestCase):
    def test_only_returns_candidates(self):
        import random

        pool = BackendPool(["http://a", "http://b", "http://c"])
        pool.set_health("http://c", False)
        lb = LoadBalancer(pool, RandomStrategy(rng=random.Random(42)))
        picks = {lb.next_backend().url for _ in range(50)}
        self.assertTrue(picks.issubset({"http://a", "http://b"}))


class RedirectTargetTests(unittest.TestCase):
    def test_preserves_path_and_query(self):
        pool = BackendPool(["http://localhost:8081"])
        lb = LoadBalancer(pool, RoundRobinStrategy())
        target = lb.redirect_target("/api/v1/payments?storeId=store-london-01")
        self.assertEqual(
            target, "http://localhost:8081/api/v1/payments?storeId=store-london-01"
        )

    def test_none_when_no_healthy_backend(self):
        pool = BackendPool(["http://a"])
        pool.set_health("http://a", False)
        lb = LoadBalancer(pool, RoundRobinStrategy())
        self.assertIsNone(lb.redirect_target("/anything"))


class HealthCheckerTests(unittest.TestCase):
    def test_check_once_updates_flags_from_probe(self):
        pool = BackendPool(["http://up", "http://down"])
        # Fake probe: only "http://up/..." is healthy.
        def fake_check(url: str, timeout: float) -> bool:
            return url.startswith("http://up")

        checker = HealthChecker(
            pool, health_path="/health", interval=0.01, timeout=1, check_fn=fake_check
        )
        checker.check_once()
        states = {b.url: b.healthy for b in pool.all()}
        self.assertTrue(states["http://up"])
        self.assertFalse(states["http://down"])

    def test_background_thread_detects_recovery(self):
        pool = BackendPool(["http://flaky"])
        state = {"healthy": False}

        def fake_check(url: str, timeout: float) -> bool:
            return state["healthy"]

        checker = HealthChecker(
            pool, health_path="/", interval=0.01, timeout=1, check_fn=fake_check
        )
        checker.start()
        try:
            self.assertEqual(pool.healthy(), [])  # checked synchronously on start
            state["healthy"] = True
            deadline = time.time() + 2.0
            while time.time() < deadline and not pool.healthy():
                time.sleep(0.01)
            self.assertEqual([b.url for b in pool.healthy()], ["http://flaky"])
        finally:
            checker.stop()


class StrategyFactoryTests(unittest.TestCase):
    def test_unknown_algorithm_raises(self):
        with self.assertRaises(ValueError):
            build_strategy("least-connections")


# ---------------------------------------------------------------------------
# End-to-end: run the real LB over real sockets and follow the 302.
# ---------------------------------------------------------------------------


class _StubBackendHandler(BaseHTTPRequestHandler):
    """Minimal backend that echoes which instance answered."""

    def do_GET(self):  # noqa: N802
        body = f"served by {self.server.server_address[1]} path={self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence test output
        pass


def _start_server(server: ThreadingHTTPServer) -> threading.Thread:
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return t


class EndToEndRedirectTests(unittest.TestCase):
    def setUp(self):
        # Two stub backends on ephemeral ports.
        self.backends = [
            ThreadingHTTPServer(("127.0.0.1", 0), _StubBackendHandler) for _ in range(2)
        ]
        self.backend_urls = []
        for b in self.backends:
            _start_server(b)
            self.backend_urls.append(f"http://127.0.0.1:{b.server_address[1]}")

        cfg = Config.from_dict(
            {
                "host": "127.0.0.1",
                "port": 0,
                "algorithm": "round_robin",
                "health_path": "/",
                "health_interval_seconds": 0.05,
                "health_timeout_seconds": 1,
                "backends": self.backend_urls,
            }
        )
        self.lb_server, self.checker = build(cfg)
        self.checker.start()
        _start_server(self.lb_server)
        self.lb_url = f"http://127.0.0.1:{self.lb_server.server_address[1]}"

    def tearDown(self):
        self.checker.stop()
        self.lb_server.shutdown()
        self.lb_server.server_close()
        for b in self.backends:
            b.shutdown()
            b.server_close()

    def test_returns_302_with_backend_location(self):
        req = urllib.request.Request(self.lb_url + "/api/v1/payments")
        # Don't auto-follow; inspect the redirect itself.
        opener = urllib.request.build_opener(_NoRedirect())
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(req)
        err = ctx.exception
        self.assertEqual(err.code, 302)
        location = err.headers["Location"]
        self.assertIn("/api/v1/payments", location)
        self.assertTrue(any(location.startswith(u) for u in self.backend_urls))

    def test_following_redirect_reaches_a_backend(self):
        # urllib follows 302 automatically; we should land on a stub backend.
        with urllib.request.urlopen(self.lb_url + "/hello") as resp:
            body = resp.read().decode()
        self.assertIn("served by", body)
        self.assertIn("path=/hello", body)

    def test_503_when_all_backends_down(self):
        for b in self.backends:
            b.shutdown()  # stop answering health checks
        # Wait for the health checker to mark them down.
        deadline = time.time() + 3.0
        opener = urllib.request.build_opener(_NoRedirect())
        while time.time() < deadline:
            try:
                opener.open(self.lb_url + "/x")
            except urllib.error.HTTPError as e:
                if e.code == 503:
                    break
            time.sleep(0.05)
        else:
            self.fail("LB never returned 503 after backends went down")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Disable automatic redirect following so we can assert on the 302."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


if __name__ == "__main__":
    import os
    import sys

    # Allow running this file directly from anywhere.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    unittest.main(verbosity=2)
