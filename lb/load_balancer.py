"""Redirect (HTTP 302) load balancer for the StarHarbour Payments service.

Instead of proxying traffic, this load balancer answers every incoming request
with an HTTP 302 redirect that points the client at one of the healthy backend
instances. The client then talks to the instance directly. This keeps the LB
stateless and cheap — it never carries request/response bodies — at the cost of
one extra round trip and exposing backend addresses to clients.

Design decisions (see lb/README.md for the full write-up):

* Service discovery — backends are read from a JSON config file (or the
  ``LB_BACKENDS`` env var). Static config is enough for the course; the
  ``BackendPool`` is the single seam where a real registry (Consul, Eureka,
  Kubernetes Endpoints) would plug in.
* Health checking — a background thread polls each backend's health path on a
  fixed interval and flips a per-backend ``healthy`` flag. Only healthy
  backends are handed out. The check function is injectable so it can be
  unit-tested without real sockets.
* Algorithm — round-robin over the *currently healthy* set by default, with a
  random strategy available. Both are O(1)-ish and stateless per request.

The module depends only on the Python standard library so the tests run with no
install step.
"""

from __future__ import annotations

import json
import os
import random
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Iterable, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Runtime configuration for the load balancer."""

    host: str = "0.0.0.0"
    port: int = 8080
    backends: list[str] = field(default_factory=list)
    algorithm: str = "round_robin"  # "round_robin" | "random"
    health_path: str = "/"
    health_interval_seconds: float = 5.0
    health_timeout_seconds: float = 2.0

    @staticmethod
    def from_file(path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return Config.from_dict(data)

    @staticmethod
    def from_dict(data: dict) -> "Config":
        cfg = Config()
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        # Allow LB_BACKENDS="http://a:8081,http://b:8082" to override the file.
        env_backends = os.environ.get("LB_BACKENDS")
        if env_backends:
            cfg.backends = [b.strip() for b in env_backends.split(",") if b.strip()]
        cfg.backends = [b.rstrip("/") for b in cfg.backends]
        return cfg


# ---------------------------------------------------------------------------
# Backend pool
# ---------------------------------------------------------------------------


@dataclass
class Backend:
    """A single app instance the load balancer can redirect to."""

    url: str
    healthy: bool = True

    def health_url(self, health_path: str) -> str:
        return self.url + health_path


class BackendPool:
    """Thread-safe registry of backends and their health.

    This is the discovery seam: ``replace`` lets an external source (registry,
    DNS, k8s) swap the backend set at runtime without touching the rest of the
    load balancer.
    """

    def __init__(self, urls: Iterable[str]):
        self._lock = threading.Lock()
        self._backends: list[Backend] = [Backend(url=u) for u in urls]

    def all(self) -> list[Backend]:
        with self._lock:
            return list(self._backends)

    def healthy(self) -> list[Backend]:
        with self._lock:
            return [b for b in self._backends if b.healthy]

    def set_health(self, url: str, healthy: bool) -> None:
        with self._lock:
            for b in self._backends:
                if b.url == url:
                    b.healthy = healthy

    def replace(self, urls: Iterable[str]) -> None:
        """Swap the backend set, preserving health state for URLs that stay."""
        with self._lock:
            previous = {b.url: b.healthy for b in self._backends}
            self._backends = [
                Backend(url=u, healthy=previous.get(u, True)) for u in urls
            ]


# ---------------------------------------------------------------------------
# Balancing strategies
# ---------------------------------------------------------------------------


class BalancingStrategy:
    """Selects one backend from a list of candidates (all assumed healthy)."""

    def choose(self, candidates: list[Backend]) -> Optional[Backend]:
        raise NotImplementedError


class RoundRobinStrategy(BalancingStrategy):
    """Cycle through candidates in order, evenly spreading load.

    The counter is global rather than per-backend so the distribution stays
    even even as the healthy set shrinks and grows.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counter = 0

    def choose(self, candidates: list[Backend]) -> Optional[Backend]:
        if not candidates:
            return None
        with self._lock:
            index = self._counter % len(candidates)
            self._counter += 1
        return candidates[index]


class RandomStrategy(BalancingStrategy):
    """Pick a uniformly random candidate. Stateless; good enough at scale."""

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng or random.Random()

    def choose(self, candidates: list[Backend]) -> Optional[Backend]:
        if not candidates:
            return None
        return self._rng.choice(candidates)


def build_strategy(name: str) -> BalancingStrategy:
    if name == "round_robin":
        return RoundRobinStrategy()
    if name == "random":
        return RandomStrategy()
    raise ValueError(f"Unknown balancing algorithm: {name!r}")


# ---------------------------------------------------------------------------
# Health checker
# ---------------------------------------------------------------------------


def http_health_check(url: str, timeout: float) -> bool:
    """Return True if a GET to ``url`` returns a 2xx/3xx status within timeout."""
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 400
    except urllib.error.HTTPError as exc:
        # The instance answered, just not with a happy status. A 4xx still
        # proves the process is up and serving, so treat <500 as healthy.
        return exc.code < 500
    except Exception:
        return False


class HealthChecker:
    """Background thread that periodically refreshes backend health.

    The actual probe is injected (``check_fn``) so tests can drive health
    transitions deterministically without opening sockets.
    """

    def __init__(
        self,
        pool: BackendPool,
        health_path: str,
        interval: float,
        timeout: float,
        check_fn: Optional[Callable[[str, float], bool]] = None,
    ) -> None:
        self._pool = pool
        self._health_path = health_path
        self._interval = interval
        self._timeout = timeout
        self._check_fn = check_fn or http_health_check
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def check_once(self) -> None:
        """Probe every backend exactly once and update its health flag."""
        for backend in self._pool.all():
            ok = self._check_fn(backend.health_url(self._health_path), self._timeout)
            self._pool.set_health(backend.url, ok)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.check_once()
            self._stop.wait(self._interval)

    def start(self) -> None:
        # Probe synchronously once so the LB has fresh health before serving.
        self.check_once()
        self._thread = threading.Thread(
            target=self._run, name="health-checker", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self._interval + self._timeout)


# ---------------------------------------------------------------------------
# Load balancer core
# ---------------------------------------------------------------------------


class LoadBalancer:
    """Chooses a healthy backend per request using the configured strategy."""

    def __init__(self, pool: BackendPool, strategy: BalancingStrategy) -> None:
        self._pool = pool
        self._strategy = strategy

    def next_backend(self) -> Optional[Backend]:
        return self._strategy.choose(self._pool.healthy())

    def redirect_target(self, path: str) -> Optional[str]:
        """Full URL to redirect to, or None when no backend is healthy."""
        backend = self.next_backend()
        if backend is None:
            return None
        if not path.startswith("/"):
            path = "/" + path
        return backend.url + path


# ---------------------------------------------------------------------------
# HTTP front end
# ---------------------------------------------------------------------------


def make_handler(load_balancer: LoadBalancer):
    """Build a BaseHTTPRequestHandler bound to ``load_balancer``."""

    class RedirectHandler(BaseHTTPRequestHandler):
        server_version = "RedirectLB/1.0"
        protocol_version = "HTTP/1.1"

        def _handle(self) -> None:
            # The LB's own liveness probe — lets you health-check the LB itself.
            if self.path == "/__lb/health":
                self._write(200, b"OK\n", content_type="text/plain")
                return

            target = load_balancer.redirect_target(self.path)
            if target is None:
                self._write(
                    503,
                    b"No healthy backend available\n",
                    content_type="text/plain",
                )
                return

            body = f"Redirecting to {target}\n".encode("utf-8")
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            # Redirects must not be cached — the target changes every request.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _write(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # Redirect every method — GET, POST, PUT, DELETE all get a 302. A 302
        # makes the client replay POST as GET per old browsers, but curl/HTTP
        # clients with --post301/307 semantics aside, the course clients re-issue
        # the original method against the Location, which is what we want.
        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle
        do_DELETE = _handle
        do_PATCH = _handle
        do_HEAD = _handle

    return RedirectHandler


def build(config: Config) -> tuple[ThreadingHTTPServer, HealthChecker]:
    """Wire up pool, strategy, health checker, and HTTP server from config."""
    pool = BackendPool(config.backends)
    strategy = build_strategy(config.algorithm)
    load_balancer = LoadBalancer(pool, strategy)
    checker = HealthChecker(
        pool,
        health_path=config.health_path,
        interval=config.health_interval_seconds,
        timeout=config.health_timeout_seconds,
    )
    handler = make_handler(load_balancer)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    return server, checker


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Redirect (HTTP 302) load balancer")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "config.json"),
        help="Path to JSON config file",
    )
    args = parser.parse_args(argv)

    config = Config.from_file(args.config)
    if not config.backends:
        print("No backends configured. Set 'backends' in config or LB_BACKENDS.")
        return 1

    server, checker = build(config)
    checker.start()
    print(
        f"Redirect LB listening on http://{config.host}:{config.port} "
        f"-> {config.algorithm} over {len(config.backends)} backend(s)"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        checker.stop()
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
