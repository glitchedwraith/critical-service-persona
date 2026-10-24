"""Lambda entry point and HTTP route dispatch.

Phase 0: skeleton only. Phases 2-5 fill in the handlers.
Route contract: plan.md §3.2.
"""
import json


def lambda_handler(event, context):
    route = event.get("routeKey", "")
    path_params = event.get("pathParameters") or {}
    body = _parse_body(event)

    # TODO(P1 phase 2): GET /state
    # TODO(P1 phase 3): POST /sms/inbound
    # TODO(P1 phase 4): POST /rumors/{id}/verify, /outbound/{id}/edit, /outbound/{id}/approve
    # TODO(P1 phase 5): POST /chaos/{action}
    # TODO(P1 phase 2): POST /reset
    return _ok({
        "ok": True,
        "route": route,
        "path_params": path_params,
        "body": body,
        "note": "backend skeleton - handlers land in later phases"
    })


def _parse_body(event):
    raw = event.get("body")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _ok(payload, status=200):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(payload),
    }
