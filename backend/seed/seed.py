"""P4 seed loader. Truncates every table and loads data/*.json.

Called by POST /reset (app.py) and scripts/seed_local.py. Bundled inside the
Lambda (CodeUri: backend/), so it only uses the backend's own db module.
Scenario scripts (scripts/rumors.json) and guided situations
(data/situations.json) are read on demand by chaos.py and /state.
"""
import json
import os
from decimal import Decimal

import db

_HERE = os.path.dirname(os.path.abspath(__file__))

# table env var -> data file (None = cleared only, never seeded)
TABLES = {
    "TABLE_SOURCES": "sources.json",
    "TABLE_ZONES": "zones.json",
    "TABLE_SHELTERS": "shelters.json",
    "TABLE_BULLETINS": "bulletins.json",
    "TABLE_MESSAGES": None,
    "TABLE_RUMORS": None,
    "TABLE_OUTBOUND": None,
    "TABLE_SYSTEM": None,
}


def load(name):
    """Read data/<name> with floats as Decimal (DynamoDB rejects float)."""
    with open(os.path.join(_HERE, "data", name)) as f:
        return json.load(f, parse_float=Decimal)


def scripts():
    """Named resident-message scripts: {id: {label, messages: [...]}}."""
    with open(os.path.join(_HERE, "scripts", "rumors.json")) as f:
        return json.load(f)


def situations():
    """Ordered guided situations: [{id, title, narration, steps}]."""
    with open(os.path.join(_HERE, "data", "situations.json")) as f:
        return json.load(f)


def seed(clear=True):
    """Reset the demo. Returns {table_env: rows_loaded}."""
    counts = {}
    for env, data_file in TABLES.items():
        tbl = db.table(env)
        if clear:
            with tbl.batch_writer() as batch:
                for item in db.scan(env):
                    batch.delete_item(Key={"id": item["id"]})
        rows = load(data_file) if data_file else []
        with tbl.batch_writer() as batch:
            for row in rows:
                batch.put_item(Item=row)
        counts[env] = len(rows)
    db.put("TABLE_SYSTEM", load("system.json"))
    counts["TABLE_SYSTEM"] = 1
    return counts
