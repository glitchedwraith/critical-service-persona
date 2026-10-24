#!/usr/bin/env bash
# Tear down everything provision.sh created: instance, Elastic IP, security
# group, key pair, and the local deploy/.instance + private key.
#
#   deploy/destroy.sh          asks you to type the instance id
#   deploy/destroy.sh --yes    no prompt
set -euo pipefail
cd "$(dirname "$0")/.."
export AWS_DEFAULT_REGION=us-east-1 AWS_REGION=us-east-1 AWS_PAGER=""

die() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
[ -f deploy/.instance ] || die "No deploy/.instance — nothing to destroy."
source deploy/.instance
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -f .env ]; then set -a; source .env; set +a; fi
aws sts get-caller-identity >/dev/null 2>&1 || die "AWS credentials missing or expired."

echo "This deletes $INSTANCE_ID ($HOST), its Elastic IP, security group $SG_ID and key pair $KEY_NAME."
if [ "${1:-}" != "--yes" ]; then
  read -r -p "Type the instance id to confirm: " answer
  [ "$answer" = "$INSTANCE_ID" ] || die "Aborted."
fi

echo "▸ Elastic IP";      aws ec2 disassociate-address --association-id "$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" --query 'Addresses[0].AssociationId' --output text)" 2>/dev/null || true
                         aws ec2 release-address --allocation-id "$ALLOC_ID" || true
echo "▸ Instance";        aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" >/dev/null || true
                         aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID" || true
echo "▸ Security group";  aws ec2 delete-security-group --group-id "$SG_ID" || true
echo "▸ Key pair";        aws ec2 delete-key-pair --key-name "$KEY_NAME" || true
rm -f deploy/.instance "$KEY"
echo "Destroyed."
