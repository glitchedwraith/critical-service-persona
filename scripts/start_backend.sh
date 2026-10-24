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

"$VENV/bin/python" scripts/seed_local.py

# 5. Start the backend
echo ""
echo "Starting backend on http://localhost:${PORT:-3000} ..."
exec "$VENV/bin/python" scripts/run_local.py
