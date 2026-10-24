#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

VENV="/tmp/truesignal-venv"

# 1. Load .env
if [ ! -f .env ]; then
  echo "ERROR: .env not found at repo root. See backend/README.md for required vars." >&2
  exit 1
fi
set -a && source .env && set +a

# 2. Python venv + boto3
if [ ! -d "$VENV" ]; then
  echo "Creating venv at $VENV ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q boto3
else
  echo "Venv already exists at $VENV"
fi

# 3. DynamoDB Local (shared-DB mode)
if docker ps --format '{{.Names}}' | grep -q '^dynamodb-local$'; then
  echo "DynamoDB Local already running"
else
  echo "Starting DynamoDB Local ..."
  docker network create truesignal-net 2>/dev/null || true
  docker rm -f dynamodb-local 2>/dev/null || true
  docker run -d --name dynamodb-local --network truesignal-net \
    -p 8000:8000 amazon/dynamodb-local \
    -jar DynamoDBLocal.jar -inMemory -sharedDb
  sleep 2
fi

# 4. Create tables + seed data
echo "Creating tables + seeding data ..."
"$VENV/bin/python" scripts/create_local_tables.py

"$VENV/bin/python" - <<'PY'
import boto3, os
os.environ.setdefault('AWS_ACCESS_KEY_ID','x')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY','x')
r = boto3.resource('dynamodb', endpoint_url='http://localhost:8000', region_name='us-east-1')
seeds = {
    'truesignal-local-sources': [
        {'id':'SRC-EOC','name':'City EOC','authority':1},
        {'id':'SRC-MGR-A','name':'Shelter A manager','authority':2},
        {'id':'SRC-MGR-D','name':'Shelter D manager','authority':2},
    ],
    'truesignal-local-shelters': [
        {'id':'SH-A','name':'Shelter A — Lincoln HS Gym','address':'123 Example Ave',
         'status':'open','capacity':300,'occupancy':240,
         'status_source_id':'SRC-EOC','status_updated_at':'04:10','status_expires_at':'05:10'},
        {'id':'SH-D','name':'Shelter D — Jefferson Rec Center','address':'456 Pine St',
         'status':'open','capacity':250,'occupancy':60,
         'status_source_id':'SRC-EOC','status_updated_at':'04:10','status_expires_at':'06:00'},
    ],
    'truesignal-local-bulletins': [
        {'id':'B-001','source_id':'SRC-EOC','title':'Shelters open',
         'body':'Shelters A (SH-A, 123 Example Ave) and D (SH-D, 456 Pine St) are open.',
         'published_at':'04:00','last_verified_at':'04:10','expires_at':'06:00','status':'active'},
    ],
}
for tbl, items in seeds.items():
    t = r.Table(tbl)
    for it in items: t.put_item(Item=it)
    print(f'  seeded {tbl}: {len(items)}')
PY

# 5. Start the backend
echo ""
echo "Starting backend on http://localhost:${PORT:-3000} ..."
exec "$VENV/bin/python" scripts/run_local.py
