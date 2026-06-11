import argparse
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Config

DEFAULT_CONFIG = "config.json"
DEFAULT_PORT   = 8000
HEALTH_TIMEOUT = 2   


def load_config(path: str) -> list:
    with open(path) as f:
        data = json.load(f)
    servers = data.get("servers", [])
    if not servers:
        raise ValueError("config.json must have at least one server in 'servers' list")
    return servers


# Health check 

def is_healthy(server_url: str) -> bool:
    url = f"{server_url}/api/v1/payments?storeId=health-check"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
            return resp.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500          
    except Exception:
        return False                

# Round-robin selector 

class RoundRobinBalancer:
    def __init__(self, servers: list):
        self.servers = servers
        self._index  = 0
        self._lock   = threading.Lock()

    def next_healthy(self) -> str | None:
        with self._lock:
            total = len(self.servers)
            for _ in range(total):
                url = self.servers[self._index % total]
                self._index += 1
                if is_healthy(url):
                    return url
        return None   

# HTTP handler 

class LoadBalancerHandler(BaseHTTPRequestHandler):

    balancer: RoundRobinBalancer   

    def do_GET(self):
        self._redirect()

    def do_POST(self):
        self._redirect()

    def do_PUT(self):
        self._redirect()

    def do_DELETE(self):
        self._redirect()

    def _redirect(self):
        target = self.balancer.next_healthy()

        if target is None:
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"503 Service Unavailable: all backends are down")
            print(f"  [503] {self.command} {self.path} — no healthy backends")
            return

        redirect_url = f"{target}{self.path}"

        self.send_response(302)
        self.send_header("Location", redirect_url)
        self.send_header("Content-Length", "0")
        self.end_headers()
        print(f"  [302] {self.command} {self.path}  →  {redirect_url}")

    def log_message(self, format, *args):
        pass  


# Main

def main():
    parser = argparse.ArgumentParser(description="StarHarbour redirect load balancer")
    parser.add_argument("--port",   type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--config", default=DEFAULT_CONFIG,         help="Path to config.json")
    args = parser.parse_args()

    servers = load_config(args.config)
    print(f"\n🔀  StarHarbour Load Balancer")
    print(f"    Listening : http://localhost:{args.port}")
    print(f"    Algorithm : round-robin with health checks")
    print(f"    Backends  :")
    for s in servers:
        status = "✅ healthy" if is_healthy(s) else "❌ unreachable"
        print(f"      {s}  ({status})")
    print()

    LoadBalancerHandler.balancer = RoundRobinBalancer(servers)

    server = HTTPServer(("", args.port), LoadBalancerHandler)
    print(f"    Ready — press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n    Stopped.")


if __name__ == "__main__":
    main()
