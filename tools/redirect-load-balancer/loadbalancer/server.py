"""The HTTP front. For every request it picks a healthy backend and answers with
a redirect (302 by default) whose Location points at that backend, keeping the
same path and query string. It never reads or forwards the body, so the balancer
stays stateless and cheap. If no backend is healthy it answers 503."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_handler(pool, redirect_status=302):
    class RedirectHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _redirect(self):
            backend = pool.next_healthy()
            if backend is None:
                body = b"no healthy backends"
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(redirect_status)
            self.send_header("Location", backend.url + self.path)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()

        do_GET = _redirect
        do_POST = _redirect
        do_PUT = _redirect
        do_PATCH = _redirect
        do_DELETE = _redirect
        do_HEAD = _redirect

    return RedirectHandler


def make_server(pool, host, port, redirect_status=302):
    return ThreadingHTTPServer((host, port), make_handler(pool, redirect_status))
