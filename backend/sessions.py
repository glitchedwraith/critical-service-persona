"""Per-visitor demo sessions for the public EC2 demo.

Each browser sends X-Session-Id; its first request creates a private set of
tables in DynamoDB Local (`<table>-s-<id>`) and seeds them, so one visitor's
clicks and resets never touch anyone else's demo. Idle sessions are dropped
after IDLE_SEC. Past MAX_SESSIONS, new visitors share the unsuffixed tables.

On by default only against DynamoDB Local (DYNAMODB_ENDPOINT set): creating
real DynamoDB tables per visitor would be slow and billable. SESSIONS=0/1
overrides.
"""
import os
import re
import threading
import time

import ai_status
import db

ENABLED = os.environ.get(
    "SESSIONS", "1" if os.environ.get("DYNAMODB_ENDPOINT") else "0") == "1"
MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", "20"))
IDLE_SEC = int(os.environ.get("SESSION_IDLE_SEC", "1800"))
SWEEP_EVERY_SEC = 60

_ID = re.compile(r"^[a-z0-9]{8,32}$")
_lock = threading.Lock()
_last_seen = {}   # sid -> epoch seconds of the last request
_ready = {}       # sid -> threading.Event, set once its tables are seeded
_adopted = False


def _tables():
    from seed import seed as seed_mod  # lazy; same table list the seeder uses
    return list(seed_mod.TABLES)


def _client():
    return db._dynamodb().meta.client


def _adopt_existing():
    """After an API restart, pick up session tables DynamoDB Local still holds."""
    global _adopted
    _adopted = True
    marker = db.table_name("TABLE_SYSTEM", session="")
    prefix = f"{marker}-s-"
    names, kwargs = [], {}
    while True:
        resp = _client().list_tables(**kwargs)
        names += resp.get("TableNames", [])
        if "LastEvaluatedTableName" not in resp:
            break
        kwargs = {"ExclusiveStartTableName": resp["LastEvaluatedTableName"]}
    now = time.time()
    for name in names:
        if name.startswith(prefix):
            sid = name[len(prefix):]
            _last_seen[sid] = now
            _ready.setdefault(sid, threading.Event()).set()


def _create(sid):
    for env in _tables():
        try:
            _client().create_table(
                TableName=db.table_name(env, session=sid),
                BillingMode="PAY_PER_REQUEST",
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            )
        except _client().exceptions.ResourceInUseException:
            pass
    from seed import seed as seed_mod
    with db.session_scope(sid):
        seed_mod.seed(clear=True)


def _drop(sid):
    for env in _tables():
        try:
            _client().delete_table(TableName=db.table_name(env, session=sid))
        except _client().exceptions.ResourceNotFoundException:
            pass


def ensure(raw_sid):
    """Return the session id to scope this request to, or None for shared.
    Creates and seeds the session's tables on first sight."""
    if not ENABLED or not raw_sid or not _ID.match(raw_sid):
        return None
    with _lock:
        if not _adopted:
            _adopt_existing()
        if raw_sid in _last_seen:
            _last_seen[raw_sid] = time.time()
            ready, creator = _ready[raw_sid], False
        elif len(_last_seen) >= MAX_SESSIONS:
            return None
        else:
            _last_seen[raw_sid] = time.time()
            ready = _ready[raw_sid] = threading.Event()
            creator = True
    if creator:
        try:
            _create(raw_sid)
        except Exception:
            with _lock:
                _last_seen.pop(raw_sid, None)
                _ready.pop(raw_sid, None)
            ready.set()
            raise
        ready.set()
    elif not ready.wait(timeout=30):
        raise RuntimeError("demo session is still being prepared, try again")
    if raw_sid not in _last_seen:
        raise RuntimeError("demo session could not be created")
    return raw_sid


def mode(sid):
    """For GET /state: private | shared (cap reached / no id) | off."""
    if not ENABLED:
        return "off"
    return "private" if sid else "shared"


def sweep(now=None):
    """Drop sessions idle for longer than IDLE_SEC. Returns the dropped ids."""
    now = now or time.time()
    dropped = []
    with _lock:
        for sid, seen in list(_last_seen.items()):
            if now - seen > IDLE_SEC:
                _drop(sid)
                _last_seen.pop(sid, None)
                _ready.pop(sid, None)
                ai_status._last_ms.pop(sid, None)
                dropped.append(sid)
    return dropped


def start_sweeper():
    """Background idle-session cleanup for long-running servers (run_local.py)."""
    if not ENABLED:
        return

    def loop():
        while True:
            time.sleep(SWEEP_EVERY_SEC)
            try:
                sweep()
            except Exception as e:  # noqa: BLE001 — keep sweeping
                print(f"session sweep failed: {e}", flush=True)

    threading.Thread(target=loop, name="session-sweeper", daemon=True).start()
