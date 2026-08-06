"""Lightweight HTTP health server + self-ping to keep Render free tier alive.

Render spins down free services after 15 min of inactivity. This module:
  1. Starts a tiny HTTP server on PORT (default 8080) so Render's health
     check passes and the service type is recognised as a web service.
  2. Exposes ping_self() which the scheduler calls every 10 minutes to
     prevent the container from going to sleep.
"""
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

log = logging.getLogger(__name__)

_self_url: str = ""


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Atlas is alive")

    def log_message(self, *args):
        pass  # suppress per-request log noise


def start_health_server(port: int = 8080) -> None:
    """Start the health server in a daemon thread (non-blocking)."""
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info("Health server running on :%d", port)


def set_self_url(url: str) -> None:
    """Set the URL this instance pings to keep itself awake."""
    global _self_url
    _self_url = url.rstrip("/")
    log.info("Keep-alive self-ping target: %s", _self_url)


def ping_self() -> None:
    """Called by the scheduler every 10 minutes. No-op if RENDER_URL not set."""
    if not _self_url:
        return
    try:
        httpx.get(_self_url, timeout=10)
        log.debug("keep-alive ping OK → %s", _self_url)
    except Exception as exc:
        log.debug("keep-alive ping failed (non-critical): %s", exc)
