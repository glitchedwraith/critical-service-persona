"""Bedrock credential health, surfaced in GET /state as system.ai.

Workshop credentials are temporary. When they expire the pipeline silently
falls back to heuristics; this module makes that visible so the UI can say
"AI offline — credentials expired" instead of just giving plainer answers.

Two signals:
  * an STS GetCallerIdentity probe, cached for PROBE_TTL_SEC
  * the outcome of the most recent real Bedrock call (record())
"""
import os
import threading
import time

import db

PROBE_TTL_SEC = 60

# Error codes that mean "the credentials themselves are bad", not a model hiccup.
_CRED_ERRORS = {
    "ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId",
    "UnrecognizedClientException", "InvalidSignatureException",
    "AccessDeniedException", "NoCredentialsError",
}

_probe = {"at": 0.0, "status": None, "detail": None}
_last_call = {"ok": None, "status": None, "detail": None, "at": None}
_inflight = {}   # thread id -> {"step", "started", "session"}; read by GET /state mid-call
_last_ms = {}    # demo session -> latency of its most recent Bedrock call

# Bedrock tool name -> what the UI says while it waits.
STEP_LABELS = {
    "record_extraction": "understand",   # Step 1 · extract + cluster
    "record_verification": "verify",     # Step 2 · verify + draft
}


def _classify(exc):
    code = getattr(exc, "response", {}).get("Error", {}).get("Code") or type(exc).__name__
    if code in ("AccessDeniedException",):
        return "denied", code
    if code in _CRED_ERRORS:
        return "expired", code
    return "error", code


def begin(tool_name):
    """Mark a Bedrock call as in flight so polling clients can show "thinking"."""
    _inflight[threading.get_ident()] = {
        "step": STEP_LABELS.get(tool_name, tool_name), "started": time.time(),
        "session": db.current_session()}


def record(ok, exc=None):
    """Called by the pipeline after every Bedrock call (ends the in-flight mark)."""
    call = _inflight.pop(threading.get_ident(), {})
    status, detail = ("ok", None) if ok else _classify(exc)
    _last_call.update(ok=ok, status=status, detail=detail, at=time.time())
    if ok and call:
        _last_ms[call["session"]] = int((time.time() - call["started"]) * 1000)


def _run_probe():
    if not os.environ.get("AWS_ACCESS_KEY_ID") and not os.environ.get("AWS_PROFILE"):
        return "missing", "no AWS credentials configured"
    try:
        import boto3
        from botocore.config import Config
        boto3.client(
            "sts", region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 1}),
        ).get_caller_identity()
        return "ok", None
    except Exception as e:  # noqa: BLE001 — any failure is a status, not a crash
        return _classify(e)


def status():
    """Return {"status": ok|expired|denied|missing|error, "detail", "checked_at",
    "thinking": [{"step", "elapsed_ms"}], "last_ms"}."""
    now = time.time()
    if now - _probe["at"] > PROBE_TTL_SEC:
        _probe["status"], _probe["detail"] = _run_probe()
        _probe["at"] = now
    result, detail = _probe["status"], _probe["detail"]
    # Credentials can be valid while Bedrock still refuses (model access revoked).
    if result == "ok" and _last_call["ok"] is False and _last_call["status"] != "error":
        result, detail = _last_call["status"], _last_call["detail"]
    # Credential health is global; thinking/latency belong to this visitor's session.
    sid = db.current_session()
    thinking = [{"step": c["step"], "elapsed_ms": int((now - c["started"]) * 1000)}
                for c in list(_inflight.values()) if c["session"] == sid]
    return {"status": result, "detail": detail, "checked_at": int(_probe["at"]),
            "thinking": thinking, "last_ms": _last_ms.get(sid)}
