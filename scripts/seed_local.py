"""Load P4 seed data into DynamoDB Local (same as POST /reset).

Usage (repo root, DynamoDB Local running):
    .venv/bin/python scripts/seed_local.py
"""
import os
import sys

os.environ.setdefault("DYNAMODB_ENDPOINT", "http://localhost:8000")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_DEFAULT_REGION", os.environ["AWS_REGION"])
os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
for name in ("sources", "bulletins", "shelters", "zones", "messages",
             "rumors", "outbound", "system"):
    os.environ.setdefault(f"TABLE_{name.upper()}", f"truesignal-local-{name}")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from seed import seed  # noqa: E402

for table, n in seed.seed().items():
    print(f"  seeded {os.environ[table]}: {n}")
