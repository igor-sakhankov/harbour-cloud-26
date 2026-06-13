"""Entry point: load settings, build the pool, start health checks, and serve."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace

from .config import load_settings
from .health import HealthChecker, http_probe
from .registry import BackendPool
from .server import make_server


def make_probe(settings):
    def probe(url):
        return http_probe(url, settings.health_path, settings.health_timeout)
    return probe


def main(argv=None):
    parser = argparse.ArgumentParser(prog="loadbalancer")
    parser.add_argument("--config", default="config.json", help="path to config.json")
    parser.add_argument("--host", help="listen host (overrides config)")
    parser.add_argument("--port", type=int, help="listen port (overrides config)")
    parser.add_argument("--backends", help="comma-separated backend URLs (overrides config/env)")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if args.backends:
        env["LB_BACKENDS"] = args.backends

    settings = load_settings(args.config, env)
    if args.host:
        settings = replace(settings, listen_host=args.host)
    if args.port:
        settings = replace(settings, listen_port=args.port)

    if not settings.backends:
        print("no backends configured (set them in config.json or --backends)", file=sys.stderr)
        return 2

    pool = BackendPool(settings.backends, settings.fail_threshold, settings.rise_threshold)
    checker = HealthChecker(pool, make_probe(settings), settings.health_interval).start()
    server = make_server(pool, settings.listen_host, settings.listen_port, settings.redirect_status)

    print(f"load balancer on {settings.listen_host}:{settings.listen_port} "
          f"-> {settings.backends} (HTTP {settings.redirect_status})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        checker.stop()
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
