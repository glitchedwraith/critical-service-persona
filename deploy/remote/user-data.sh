#!/bin/bash
# EC2 user-data (runs once as root on first boot, Amazon Linux 2023).
# Installs the runtime only; deploy/ship.sh copies the app, systemd units and
# nginx config on every deploy. No credentials here: user-data is readable
# from the instance metadata service.
set -euxo pipefail

dnf install -y docker nginx python3.11 python3.11-pip rsync
systemctl enable --now docker
docker pull amazon/dynamodb-local

# Unprivileged service account for the API; code and static files are owned
# by ec2-user so ship.sh can rsync without sudo.
id truesignal >/dev/null 2>&1 || useradd --system --no-create-home --shell /sbin/nologin truesignal
install -d -o ec2-user -g ec2-user /opt/truesignal /usr/share/nginx/truesignal
install -d -m 700 -o root -g root /etc/truesignal

echo "truesignal bootstrap done" > /var/log/truesignal-bootstrap.done
