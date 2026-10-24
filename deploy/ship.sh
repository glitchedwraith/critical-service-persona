#!/usr/bin/env bash
# Build the frontend locally and deploy the app to the instance.
#
#   deploy/ship.sh     re-run after every change; safe to repeat
#
# Builds frontend/dist with VITE_API_BASE_URL=/api (nginx serves both on one
# origin), rsyncs backend/, scripts/ and deploy/remote/ to /opt/truesignal and
# the build to /usr/share/nginx/truesignal, then runs deploy/remote/install.sh.
# Redeploying restarts the API, which reseeds the shared demo; visitors'
# private sessions survive.
set -euo pipefail
cd "$(dirname "$0")/.."

die() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
step() { printf '\n\033[36m▸ %s\033[0m\n' "$*"; }

[ -f deploy/.instance ] || die "No deploy/.instance. Run deploy/provision.sh first."
source deploy/.instance
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)
REMOTE="ec2-user@$HOST"

step "Frontend build"
# Only the public CARTO tile key goes into the bundle; nothing else from .env.
CARTO_KEY="$(sed -n 's/^VITE_CARTO_API_KEY=//p' .env 2>/dev/null || true)"
(cd frontend && npm ci --no-audit --no-fund --loglevel=error \
  && npm test --silent >/dev/null \
  && VITE_API_BASE_URL=/api VITE_CARTO_API_KEY="$CARTO_KEY" npx vite build --logLevel warn)
echo "  frontend/dist built"

step "Upload"
RSYNC=(rsync -az --delete -e "ssh ${SSH_OPTS[*]}" --exclude __pycache__ --exclude '*.pyc')
"${RSYNC[@]}" backend scripts "$REMOTE:/opt/truesignal/"
"${RSYNC[@]}" deploy/remote "$REMOTE:/opt/truesignal/deploy/"
"${RSYNC[@]}" frontend/dist/ "$REMOTE:/usr/share/nginx/truesignal/"
echo "  ok"

step "Install + restart"
ssh "${SSH_OPTS[@]}" "$REMOTE" 'sudo bash /opt/truesignal/deploy/remote/install.sh'

step "Public check"
curl -fs "http://$HOST/api/state" | python3 -c 'import json,sys; s=json.load(sys.stdin)["system"]; print("  /api/state ok · ai:", s["ai"]["status"], "· session:", s["session"])' \
  || die "http://$HOST/api/state is not answering"
printf '\n\033[1mDeployed:\033[0m http://%s\n' "$HOST"
