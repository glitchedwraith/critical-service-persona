"""Bootstrap DynamoDB Local for backend development.

Creates the 7 tables matching template.yaml and seeds the system singleton so
clock.now() works immediately. Idempotent — safe to re-run.

Usage:
    # 1. Start DynamoDB Local
    docker network create truesignal-net 2>/dev/null || true
    docker run -d --name dynamodb-local --network truesignal-net \\
        -p 8000:8000 amazon/dynamodb-local

    # 2. From repo root
    python scripts/create_local_tables.py

Env overrides:
    DYNAMODB_ENDPOINT    default http://localhost:8000
    AWS_REGION           default us-east-1
    TABLE_PREFIX         default truesignal-local-
"""
import os
import sys
import boto3
from botocore.exceptions import ClientError

ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "http://localhost:8000")
REGION = os.environ.get("AWS_REGION", "us-east-1")
PREFIX = os.environ.get("TABLE_PREFIX", "truesignal-local-")

TABLES = [
    "sources",
    "bulletins",
    "shelters",
    "messages",
    "rumors",
    "outbound",
    "system",
]


def _client():
    return boto3.client(
        "dynamodb",
        endpoint_url=ENDPOINT,
        region_name=REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    )


def _resource():
    return boto3.resource(
        "dynamodb",
        endpoint_url=ENDPOINT,
        region_name=REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    )


def create_table(name):
    full = f"{PREFIX}{name}"
    try:
        _client().create_table(
            TableName=full,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        )
        print(f"  created {full}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"  exists  {full}")
        else:
            raise


def seed_system_singleton():
    tbl = _resource().Table(f"{PREFIX}system")
    tbl.put_item(Item={
        "id": "singleton",
        "sim_clock": "04:30",
        "city_site_online": True,
        "approver": "Dana",
        "cache_as_of": "04:10",
        "trace": [],
    })
    print(f"  seeded  {PREFIX}system/singleton (sim_clock=04:30)")


def main():
    print(f"Target: {ENDPOINT} (region={REGION}, prefix={PREFIX!r})")
    try:
        _client().list_tables()
    except Exception as e:
        print(f"ERROR: cannot reach DynamoDB at {ENDPOINT}: {e}", file=sys.stderr)
        print("Is DynamoDB Local running? Start it with:", file=sys.stderr)
        print("  docker run -d --name dynamodb-local -p 8000:8000 amazon/dynamodb-local",
              file=sys.stderr)
        sys.exit(1)
    for name in TABLES:
        create_table(name)
    seed_system_singleton()
    print("Done.")


if __name__ == "__main__":
    main()
