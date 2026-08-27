"""Wires the dashboard's HTTP server: a background-thread ThreadingHTTPServer serving REST + SSE."""
from __future__ import annotations

from http.server import ThreadingHTTPServer

from app.dashboard.api import DEFAULT_HEARTBEAT_SECONDS, build_handler_class
from app.telemetry.broadcaster import EventBroadcaster
from app.telemetry.store import TraceStore


def build_dashboard_server(
    host: str,
    port: int,
    store: TraceStore,
    broadcaster: EventBroadcaster,
    max_list_limit: int,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
) -> ThreadingHTTPServer:
    handler_class = build_handler_class(store, broadcaster, max_list_limit, heartbeat_seconds)
    server = ThreadingHTTPServer((host, port), handler_class)
    server.daemon_threads = True
    return server
