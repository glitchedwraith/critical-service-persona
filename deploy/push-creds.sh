#!/usr/bin/env bash
# Push (or refresh) Bedrock credentials onto the TrueSignal EC2 instance over SSH.
#
#   deploy/push-creds.sh               host + key from deploy/.instance (written by provision.sh)
#   deploy/push-creds.sh <host> <key>  explicit host and SSH private key
#
# Credentials come from the current shell if AWS_ACCESS_KEY_ID is exported
# (e.g. pasted from the workshop portal), otherwise from the repo's .env.
# They travel over SSH stdin — never as command-line args, never echoed — and
# land in /etc/truesignal/aws.env (root, 0600), which truesignal-api.service
# reads via EnvironmentFile=. Re-run whenever the workshop credentials rotate.
set -euo pipefail
cd "$(dirname "$0")/.."

die() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ---- target ------------------------------------------------------------------
HOST="${1:-}"; KEY="${2:-}"
if [ -z "$HOST" ] && [ -f deploy/.instance ]; then
  # shellcheck disable=SC1091
  source deploy/.instance   # sets HOST and KEY
fi
[ -n "$HOST" ] || die "No host. Run deploy/provision.sh first, or pass <host> <key>."
[ -f "$KEY" ]  || die "SSH key not found: ${KEY:-<unset>}"

# ---- credentials ---------------------------------------------------------------
if [ -z "${AWS_ACCESS_KEY_ID:-}" ]; then
  [ -f .env ] || die "No AWS_ACCESS_KEY_ID in the environment and no .env file."
  set -a; source .env; set +a
fi
[ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ] \
  || die "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are empty."

# Fail fast on expired credentials instead of shipping dead ones.
aws sts get-caller-identity >/dev/null 2>&1 \
  || die "These credentials are rejected by AWS (expired?). Grab fresh ones from the workshop portal."

SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "ec2-user@$HOST")

# ---- push ----------------------------------------------------------------------
echo "▸ Writing /etc/truesignal/aws.env on $HOST"
{
  echo "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID"
  echo "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY"
  [ -n "${AWS_SESSION_TOKEN:-}" ] && echo "AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN"
  echo "AWS_REGION=us-east-1"
  echo "AWS_DEFAULT_REGION=us-east-1"
  [ -n "${BEDROCK_MODEL_ID:-}" ] && echo "BEDROCK_MODEL_ID=$BEDROCK_MODEL_ID"
} | "${SSH[@]}" 'sudo install -d -m 700 -o root -g root /etc/truesignal \
  && sudo tee /etc/truesignal/aws.env >/dev/null \
  && sudo chmod 600 /etc/truesignal/aws.env'

# ---- restart + verify ----------------------------------------------------------
echo "▸ Restarting truesignal-api"
"${SSH[@]}" 'sudo systemctl restart truesignal-api'

echo "▸ Verifying credentials on the instance"
arn=$("${SSH[@]}" "sudo bash -c 'set -a; . /etc/truesignal/aws.env; aws sts get-caller-identity --query Arn --output text'" 2>/dev/null) \
  || die "Instance could not authenticate with the pushed credentials."
echo "  ok: $(sed 's/[0-9]\{12\}/<acct>/' <<<"$arn")"

for _ in $(seq 1 20); do
  "${SSH[@]}" 'curl -fs http://127.0.0.1:3000/state >/dev/null' && { echo "  api: up"; exit 0; }
  sleep 1
done
die "API did not come back up — check: ssh … 'journalctl -u truesignal-api -n 50'"
