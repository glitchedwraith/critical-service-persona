#!/usr/bin/env bash
# TrueSignal — install everything and run the whole project locally.
#
#   ./start.sh            install deps, start DynamoDB Local, seed, run backend + frontend
#   ./start.sh --install  install deps only
#
# Prerequisites it can't install for you: Docker (running). On macOS with
# Homebrew, missing Python 3 / Node.js are installed automatically.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { printf '\n\033[36m▸ %s\033[0m\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 1. configuration --------------------------------------------------------
step "Configuration"
if [ ! -f .env ]; then
  cp .env.example .env
  die "Created .env from .env.example — add your AWS credentials, then re-run ./start.sh"
fi
set -a; source .env; set +a
BACKEND_PORT="${BACKEND_PORT:-3000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
export AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-$AWS_REGION}"
[ -n "${AWS_ACCESS_KEY_ID:-}" ] || echo "  ! AWS_ACCESS_KEY_ID is empty: Bedrock calls will fail and the pipeline falls back to heuristics."
echo "  backend :$BACKEND_PORT   frontend :$FRONTEND_PORT   region $AWS_REGION"

# ---- 2. system tools ---------------------------------------------------------
step "System tools"
need() {  # need <command> <brew formula> <install hint>
  command -v "$1" >/dev/null 2>&1 && return
  if command -v brew >/dev/null 2>&1 && [ -n "$2" ]; then
    echo "  installing $2 with Homebrew…"; brew install "$2"
  else
    die "$1 not found. $3"
  fi
}
need python3 python@3.12 "Install Python 3.10+ from https://www.python.org/downloads/"
need node node "Install Node.js 20+ from https://nodejs.org/"
need docker "" "Install Docker Desktop from https://www.docker.com/products/docker-desktop/"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10+ required (found $(python3 -V))"
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ] || die "Node.js 20+ required (found $(node -v))"
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker Desktop and re-run."
echo "  $(python3 -V) · node $(node -v) · docker $(docker version --format '{{.Server.Version}}')"

# ---- 3. project dependencies -------------------------------------------------
step "Python dependencies (.venv)"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r backend/requirements.txt
echo "  ok"

step "Frontend dependencies (npm)"
(cd frontend && npm ci --no-audit --no-fund --loglevel=error)
# Frontend env: point at the local backend and pass the optional CARTO key
# through (keeping one already in frontend/.env if the root .env has none).
CARTO_KEY="${VITE_CARTO_API_KEY:-}"
[ -n "$CARTO_KEY" ] || CARTO_KEY="$(sed -n 's/^VITE_CARTO_API_KEY=//p' frontend/.env 2>/dev/null || true)"
printf 'VITE_API_BASE_URL=http://127.0.0.1:%s\nVITE_CARTO_API_KEY=%s\n' "$BACKEND_PORT" "$CARTO_KEY" > frontend/.env
chmod 600 frontend/.env
echo "  ok"

step "DynamoDB Local (docker)"
docker pull -q amazon/dynamodb-local >/dev/null
echo "  ok"

[ "${1:-}" = "--install" ] && { bold "Dependencies installed."; exit 0; }

# ---- 4. database --------------------------------------------------------------
step "Database"
if docker ps --format '{{.Names}}' | grep -q '^dynamodb-local$'; then
  echo "  DynamoDB Local already running"
else
  docker rm -f dynamodb-local >/dev/null 2>&1 || true
  # -sharedDb: one database regardless of which AWS key id the client uses.
  docker run -d --name dynamodb-local -p 8000:8000 amazon/dynamodb-local \
    -jar DynamoDBLocal.jar -inMemory -sharedDb >/dev/null
  sleep 2
fi
.venv/bin/python scripts/create_local_tables.py >/dev/null
.venv/bin/python scripts/seed_local.py

# ---- 5. run -------------------------------------------------------------------
step "Starting TrueSignal"
pids=()
cleanup() { trap - INT TERM EXIT; kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true; echo; bold "Stopped. (DynamoDB Local keeps running: docker stop dynamodb-local)"; }
trap cleanup INT TERM EXIT

PORT="$BACKEND_PORT" .venv/bin/python scripts/run_local.py &
pids+=($!)
for _ in $(seq 1 40); do
  curl -fs "http://127.0.0.1:$BACKEND_PORT/state" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fs "http://127.0.0.1:$BACKEND_PORT/state" >/dev/null || die "Backend did not start on :$BACKEND_PORT"

(cd frontend && exec npx vite --port "$FRONTEND_PORT" --strictPort --host 127.0.0.1 --logLevel warn) &
pids+=($!)

echo
bold "TrueSignal is running"
echo "  App      http://127.0.0.1:$FRONTEND_PORT"
echo "  API      http://127.0.0.1:$BACKEND_PORT/state"
echo "  Ctrl-C to stop"
wait
