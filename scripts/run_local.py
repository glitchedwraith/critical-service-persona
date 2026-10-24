"""Local dev server for the TrueSignal backend.

Bypasses `sam local start-api` (which chokes on Docker Desktop's non-standard
socket path on macOS). Instead, we run the exact Lambda handler in-process
and translate HTTP requests into the API Gateway v2 event shape the handler
expects. DynamoDB Local via Docker, Bedrock calls hit real AWS.

Usage:
    source .env                # exports AWS creds + bearer token
    /tmp/truesignal-venv/bin/python scripts/run_local.py
    # listens on http://localhost:3000, same URLs as the deployed API

Required env vars (loaded from .env + a few defaults below):
    AWS_ACCESS_KEY_ID / _SECRET_ACCESS_KEY / _SESSION_TOKEN
    BEDROCK_MODEL_ID (default us.anthropic.claude-haiku-4-5-20251001-v1:0)
    DYNAMODB_ENDPOINT (default http://localhost:8000)
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

# Defaults for local dev
os.environ.setdefault("DYNAMODB_ENDPOINT", "http://localhost:8000")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
for name, default in [
    ("TABLE_SOURCES", "truesignal-local-sources"),
    ("TABLE_BULLETINS", "truesignal-local-bulletins"),
    ("TABLE_SHELTERS", "truesignal-local-shelters"),
    ("TABLE_MESSAGES", "truesignal-local-messages"),
    ("TABLE_RUMORS", "truesignal-local-rumors"),
    ("TABLE_OUTBOUND", "truesignal-local-outbound"),
    ("TABLE_SYSTEM", "truesignal-local-system"),
]:
    os.environ.setdefault(name, default)

# Make backend/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import app  # noqa: E402

# API Gateway v2 "routeKey" templates we need to match. Order matters:
# templated routes must come before any catch-alls.
ROUTES = [
    ("GET", r"^/state$", "GET /state", None),
    ("POST", r"^/sms/inbound$", "POST /sms/inbound", None),
    ("POST", r"^/rumors/(?P<id>[^/]+)/verify$", "POST /rumors/{id}/verify", ["id"]),
    ("POST", r"^/outbound/(?P<id>[^/]+)/edit$", "POST /outbound/{id}/edit", ["id"]),
    ("POST", r"^/outbound/(?P<id>[^/]+)/approve$", "POST /outbound/{id}/approve", ["id"]),
    ("POST", r"^/chaos/(?P<action>[^/]+)$", "POST /chaos/{action}", ["action"]),
    ("POST", r"^/reset$", "POST /reset", None),
]


def _match(method, path):
    for verb, pattern, routeKey, params in ROUTES:
        if verb != method:
            continue
        m = re.match(pattern, path)
        if m:
            return routeKey, m.groupdict() if params else None
    return None, None


class Handler(BaseHTTPRequestHandler):
    def _dispatch(self, method):
        routeKey, path_params = _match(method, self.path)
        if routeKey is None:
            self._send(404, {"error": f"no route for {method} {self.path}"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else None
        event = {"routeKey": routeKey, "body": body, "pathParameters": path_params}
        resp = app.lambda_handler(event, None)
        self._send_raw(resp.get("statusCode", 200), resp.get("body") or "", resp.get("headers") or {})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_OPTIONS(self):
        self._send_raw(204, "", {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        })

    def _send(self, status, obj):
        self._send_raw(status, json.dumps(obj), {"Content-Type": "application/json"})

    def _send_raw(self, status, body, headers):
        self.send_response(status)
        headers.setdefault("Access-Control-Allow-Origin", "*")
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body.encode("utf-8") if isinstance(body, str) else body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else '?'}\n")


def main():
    port = int(os.environ.get("PORT", "3000"))
    print(f"TrueSignal local backend on http://localhost:{port}", flush=True)
    print(f"  model: {os.environ['BEDROCK_MODEL_ID']}", flush=True)
    print(f"  dynamodb: {os.environ['DYNAMODB_ENDPOINT']}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
