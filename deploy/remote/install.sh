#!/bin/bash
# Runs on the instance as root, invoked by deploy/ship.sh after each rsync.
# Idempotent: installs Python deps, systemd units and the nginx site, then
# restarts the API (which recreates and reseeds the shared tables).
set -euo pipefail
APP=/opt/truesignal
HERE="$APP/deploy/remote"

[ -f /var/log/truesignal-bootstrap.done ] || { echo "user-data bootstrap hasn't finished yet" >&2; exit 1; }

[ -x "$APP/.venv/bin/python" ] || python3.11 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -r "$APP/backend/requirements.txt"

install -m 644 "$HERE/dynamodb-local.service" "$HERE/truesignal-api.service" /etc/systemd/system/
install -m 644 "$HERE/nginx-truesignal.conf" /etc/nginx/conf.d/truesignal.conf
nginx -t

systemctl daemon-reload
systemctl enable --now dynamodb-local truesignal-api nginx
systemctl restart truesignal-api
systemctl reload nginx

for _ in $(seq 1 60); do
  curl -fs -o /dev/null http://127.0.0.1:3000/state && { echo "api: up"; exit 0; }
  sleep 1
done
echo "api did not come up; journalctl -u truesignal-api -n 50:" >&2
journalctl -u truesignal-api -n 50 --no-pager >&2
exit 1
