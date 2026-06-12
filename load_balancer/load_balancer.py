"""Redirect load balancer for the StarHarbour Payments API.

Distributes incoming requests across multiple backend instances using:
  - Round Robin scheduling (thread-safe)
  - Health checks before every redirect
  - HTTP 302 redirects (the client talks to the backend directly afterwards)

Backends are loaded from instances.json at startup.
"""

import functools
import json
import threading
from pathlib import Path

import requests
from flask import Flask, Response, redirect, request

app = Flask(__name__)

# Flush immediately so log lines appear in real time even when stdout is
# piped/redirected (Python block-buffers stdout when it is not a terminal).
print = functools.partial(print, flush=True)

# Health check settings: any response below 500 counts as healthy, because a
# 4xx still proves the instance is up and able to process requests.
HEALTH_CHECK_PATH = "/api/v1/payments?storeId=health-check"
HEALTH_CHECK_TIMEOUT_SECONDS = 2.0

LOAD_BALANCER_PORT = 8000


def load_instances() -> list[str]:
    """Load the backend instance URLs from instances.json.

    The path is resolved relative to this file so the load balancer can be
    started from any working directory.
    """
    config_path = Path(__file__).parent / "instances.json"
    with config_path.open() as config_file:
        config = json.load(config_file)
    return config["instances"]


INSTANCES: list[str] = load_instances()

# Round Robin state. Flask handles requests on multiple threads, so the index
# must be protected by a lock.
_index_lock = threading.Lock()
_current_index = 0


def next_instance() -> str:
    """Return the next instance in Round Robin order (thread-safe)."""
    global _current_index
    with _index_lock:
        instance = INSTANCES[_current_index]
        _current_index = (_current_index + 1) % len(INSTANCES)
    return instance


def is_healthy(instance: str) -> bool:
    """Check whether a backend instance is healthy.

    Healthy:   any 2xx or 4xx response.
    Unhealthy: any 5xx response, connection error, or timeout.
    """
    try:
        response = requests.get(
            instance + HEALTH_CHECK_PATH,
            timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
        )
        return response.status_code < 500
    except requests.RequestException:
        return False


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def balance(path: str) -> Response:
    """Redirect any incoming request to the next healthy backend instance.

    Tries each instance at most once (in Round Robin order). If none are
    healthy, responds with 503 Service Unavailable.
    """
    for _ in range(len(INSTANCES)):
        instance = next_instance()
        print(f"Selected instance: {instance}")

        if not is_healthy(instance):
            print(f"Health check failed, skipping instance: {instance}")
            continue

        print("Health check passed")
        target = build_target_url(instance)
        print(f"Redirecting to: {target}")
        return redirect(target, code=302)

    print("No healthy instances available, returning 503")
    return Response("Service Unavailable: no healthy instances", status=503)


def build_target_url(instance: str) -> str:
    """Build the redirect target, preserving the original path and query."""
    target = instance + request.path
    query_string = request.query_string.decode()
    if query_string:
        target += "?" + query_string
    return target


if __name__ == "__main__":
    print(f"Load balancer starting on http://localhost:{LOAD_BALANCER_PORT}")
    print(f"Backend instances: {INSTANCES}")
    app.run(host="localhost", port=LOAD_BALANCER_PORT)
