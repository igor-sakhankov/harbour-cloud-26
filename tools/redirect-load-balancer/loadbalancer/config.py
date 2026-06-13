"""Settings for the load balancer, loaded from a JSON file with an env override
for the backend list. This is the seam where a real service registry could be
plugged in later instead of a static list."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

DEFAULT_HEALTH_PATH = "/api/v1/payments?storeId=__lb_health__"


@dataclass(frozen=True)
class Settings:
    backends: list
    listen_host: str = "0.0.0.0"
    listen_port: int = 8080
    health_path: str = DEFAULT_HEALTH_PATH
    health_interval: float = 1.0
    health_timeout: float = 2.0
    fail_threshold: int = 2
    rise_threshold: int = 2
    redirect_status: int = 302


def load_settings(path=None, env=None):
    """Build Settings from an optional config.json. The LB_BACKENDS env var (a
    comma-separated list) overrides the file's backend list when present."""
    env = os.environ if env is None else env
    data = {}
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

    backends = _split(env.get("LB_BACKENDS")) or list(data.get("backends", []))
    backends = [b.rstrip("/") for b in backends]

    return Settings(
        backends=backends,
        listen_host=data.get("listen_host", "0.0.0.0"),
        listen_port=int(data.get("listen_port", 8080)),
        health_path=data.get("health_path", DEFAULT_HEALTH_PATH),
        health_interval=float(data.get("health_interval", 1.0)),
        health_timeout=float(data.get("health_timeout", 2.0)),
        fail_threshold=int(data.get("fail_threshold", 2)),
        rise_threshold=int(data.get("rise_threshold", 2)),
        redirect_status=int(data.get("redirect_status", 302)),
    )


def _split(value):
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]
