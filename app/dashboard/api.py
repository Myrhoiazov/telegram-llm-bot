"""HTTP request handling for the trace dashboard: static files, REST endpoints, and SSE."""
from __future__ import annotations

import json
import logging
import queue
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.telemetry.broadcaster import EventBroadcaster
from app.telemetry.store import TraceStore

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[2] / "dashboard"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}
DEFAULT_HEARTBEAT_SECONDS = 20.0


def build_handler_class(
    store: TraceStore, broadcaster: EventBroadcaster, max_list_limit: int, heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS
):
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        server_version = "AgentTraceDashboard/1.0"
        # Required for the SSE endpoint's Transfer-Encoding: chunked to be protocol-correct: chunked
        # framing is only defined for HTTP/1.1. Without this, the status line would declare
        # HTTP/1.0 while sending a chunked body — some clients (requests/urllib3, curl) tolerate
        # this by keying chunk-parsing off the header alone, but that's undocumented leniency, not
        # a guarantee. Harmless for the REST/static endpoints too, since they already send explicit
        # Content-Length and are valid under either declared HTTP version.
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args) -> None:
            logger.info("dashboard: " + format, *args)

        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            path = parts.path
            query = parse_qs(parts.query)

            if path in STATIC_FILES:
                self._serve_static(path)
            elif path == "/api/traces":
                self._list_traces(query)
            elif path == "/api/stats":
                self._send_json(store.get_stats())
            elif path == "/api/events/stream":
                self._stream_events()
            elif path.startswith("/api/traces/") and path.endswith("/events"):
                trace_id = path[len("/api/traces/"):-len("/events")]
                self._get_trace_events(trace_id)
            elif path.startswith("/api/traces/"):
                trace_id = path[len("/api/traces/"):]
                self._get_trace(trace_id)
            else:
                self._send_json({"error": "not found"}, status=404)

        def _serve_static(self, path: str) -> None:
            filename, content_type = STATIC_FILES[path]
            file_path = STATIC_DIR / filename
            try:
                body = file_path.read_bytes()
            except OSError:
                self._send_json({"error": "not found"}, status=404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _list_traces(self, query: dict) -> None:
            limit = _parse_int(query.get("limit", ["50"])[0], default=50)
            limit = max(1, min(limit, max_list_limit))
            status = query.get("status", [None])[0]
            chat_id_raw = query.get("chat_id", [None])[0]
            chat_id = _parse_int(chat_id_raw, default=None) if chat_id_raw is not None else None
            traces = store.list_traces(limit=limit, status=status, chat_id=chat_id)
            self._send_json(traces)

        def _get_trace(self, trace_id: str) -> None:
            trace = store.get_trace(trace_id)
            if trace is None:
                self._send_json({"error": "trace not found"}, status=404)
                return
            self._send_json(trace)

        def _get_trace_events(self, trace_id: str) -> None:
            self._send_json(store.get_events(trace_id))

        def _stream_events(self) -> None:
            # Transfer-Encoding: chunked (rather than a Content-Length-less "read until close"
            # HTTP/1.0-style body) is not cosmetic here: without it, http.client's underlying
            # buffered socket reader treats each client-side read(amt) as greedy — it keeps
            # issuing raw socket reads until it accumulates the full requested amt (e.g.
            # requests.iter_lines()'s default 512-byte chunk_size) before returning anything.
            # Our SSE frames are tiny (22-76 bytes) and trickle in one heartbeat at a time, so a
            # greedy read can silently sit for many heartbeat intervals accumulating bytes before
            # the client ever sees the first event. Real chunked framing makes http.client read
            # exactly one server-declared chunk at a time via _read_chunked(), so each write is
            # visible to the client as soon as it is flushed, regardless of chunk_size.
            # Note: this stream is intentionally never terminated with a final 0\r\n\r\n chunk —
            # SSE has no defined end-of-stream marker. The connection just stays open until the
            # client disconnects or a write fails, at which point the except/finally below cleans
            # up the subscription.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            subscriber = broadcaster.subscribe()
            try:
                while True:
                    try:
                        event = subscriber.get(timeout=heartbeat_seconds)
                        chunk = f"event: agent_event\ndata: {json.dumps(event)}\n\n"
                    except queue.Empty:
                        chunk = "event: ping\ndata: {}\n\n"
                    self._write_chunk(chunk.encode("utf-8"))
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                broadcaster.unsubscribe(subscriber)

        def _write_chunk(self, payload: bytes) -> None:
            self.wfile.write(f"{len(payload):X}\r\n".encode("ascii"))
            self.wfile.write(payload)
            self.wfile.write(b"\r\n")
            self.wfile.flush()

        def _send_json(self, data, status: int = 200) -> None:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return DashboardRequestHandler


def _parse_int(value, default):
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
