#!/usr/bin/env bash
# Give a teammate their own SSH access (instead of sharing the .pem).
#
#   deploy/add-ssh-key.sh ~/teammate_ed25519.pub
#
# Then they connect with: ssh ec2-user@<host> (using their own private key).
# To revoke, delete their line from ~ec2-user/.ssh/authorized_keys.
set -euo pipefail
cd "$(dirname "$0")/.."
die() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

PUB="${1:-}"
[ -f "$PUB" ] || die "Usage: deploy/add-ssh-key.sh <public-key-file>"
grep -qE '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-[a-z0-9-]+) ' "$PUB" || die "$PUB doesn't look like an SSH public key."
[ -f deploy/.instance ] || die "No deploy/.instance. Run deploy/provision.sh first."
source deploy/.instance

ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "ec2-user@$HOST" \
  'key=$(cat); grep -qxF "$key" ~/.ssh/authorized_keys && echo "already present" || { echo "$key" >> ~/.ssh/authorized_keys; echo "added"; }' < "$PUB"
echo "Teammate connects with: ssh ec2-user@$HOST"
