#!/usr/bin/env bash
# Create the TrueSignal demo instance on EC2 (us-east-1, default VPC).
#
#   deploy/provision.sh     then: deploy/ship.sh && deploy/push-creds.sh
#
# Creates, all tagged Project=truesignal:
#   key pair  truesignal-demo   (private key -> deploy/truesignal-demo.pem)
#   security group truesignal-demo: 22 + 80 open to 0.0.0.0/0 (SSH is key-only)
#   t3.small Amazon Linux 2023, 16 GB gp3, IMDSv2 only, user-data bootstrap
#   Elastic IP, so the public URL survives stop/start
# Writes deploy/.instance (read by ship.sh, push-creds.sh, destroy.sh).
# Credentials: the current shell's AWS_* vars, else the repo's .env.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME=truesignal-demo
TYPE="${INSTANCE_TYPE:-t3.small}"
export AWS_DEFAULT_REGION=us-east-1 AWS_REGION=us-east-1 AWS_PAGER=""
KEY=deploy/$NAME.pem
TAGS="{Key=Name,Value=$NAME},{Key=Project,Value=truesignal}"

die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
step() { printf '\n\033[36m▸ %s\033[0m\n' "$*"; }

if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -f .env ]; then set -a; source .env; set +a; fi
aws sts get-caller-identity >/dev/null 2>&1 || die "AWS credentials missing or expired."

if [ -f deploy/.instance ]; then
  source deploy/.instance
  state=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null || echo gone)
  [ "$state" = "terminated" ] || [ "$state" = "gone" ] \
    || die "Already provisioned: $INSTANCE_ID ($state) at http://$HOST — run deploy/destroy.sh first."
fi

step "AMI"
AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)
echo "  $AMI (Amazon Linux 2023)"

step "Key pair"
if aws ec2 describe-key-pairs --key-names "$NAME" >/dev/null 2>&1; then
  [ -f "$KEY" ] || die "Key pair $NAME exists in AWS but $KEY is missing. Delete it (aws ec2 delete-key-pair --key-name $NAME) or restore the file."
  echo "  reusing $NAME"
else
  (umask 077; aws ec2 create-key-pair --key-name "$NAME" --key-type ed25519 \
    --tag-specifications "ResourceType=key-pair,Tags=[$TAGS]" \
    --query KeyMaterial --output text > "$KEY")
  echo "  created $NAME -> $KEY"
fi

step "Security group"
VPC=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
SG_ID=$(aws ec2 describe-security-groups --filters Name=group-name,Values="$NAME" Name=vpc-id,Values="$VPC" \
  --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG_ID" = "None" ]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$NAME" --vpc-id "$VPC" \
    --description "TrueSignal public demo: HTTP + SSH" \
    --tag-specifications "ResourceType=security-group,Tags=[$TAGS]" --query GroupId --output text)
  for port in 22 80; do
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port $port --cidr 0.0.0.0/0 >/dev/null
  done
  echo "  created $SG_ID (22, 80 from anywhere)"
else
  echo "  reusing $SG_ID"
fi

step "Instance"
INSTANCE_ID=$(aws ec2 run-instances --image-id "$AMI" --instance-type "$TYPE" \
  --key-name "$NAME" --security-group-ids "$SG_ID" \
  --user-data file://deploy/remote/user-data.sh \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=16,VolumeType=gp3,DeleteOnTermination=true}' \
  --tag-specifications "ResourceType=instance,Tags=[$TAGS]" "ResourceType=volume,Tags=[$TAGS]" \
  --query 'Instances[0].InstanceId' --output text)
echo "  $INSTANCE_ID ($TYPE) launching…"
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

step "Elastic IP"
ALLOC_ID=$(aws ec2 allocate-address --domain vpc \
  --tag-specifications "ResourceType=elastic-ip,Tags=[$TAGS]" --query AllocationId --output text)
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" >/dev/null
sleep 3  # the public DNS name follows the new address
HOST=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)
echo "  $HOST"

cat > deploy/.instance <<EOF
# Written by deploy/provision.sh — read by ship.sh, push-creds.sh, destroy.sh
HOST=$HOST
KEY=$KEY
INSTANCE_ID=$INSTANCE_ID
SG_ID=$SG_ID
ALLOC_ID=$ALLOC_ID
KEY_NAME=$NAME
EOF

step "Waiting for SSH and the user-data bootstrap (a few minutes)"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 "ec2-user@$HOST")
for _ in $(seq 1 60); do "${SSH[@]}" true 2>/dev/null && break; sleep 5; done
"${SSH[@]}" 'sudo cloud-init status --wait >/dev/null; test -f /var/log/truesignal-bootstrap.done' \
  || die "Bootstrap failed: ssh in and check /var/log/cloud-init-output.log"

printf '\n\033[1mProvisioned.\033[0m http://%s\nNext: deploy/ship.sh && deploy/push-creds.sh\n' "$HOST"
