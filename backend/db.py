"""DynamoDB helpers.

Honours DYNAMODB_ENDPOINT for local dev (DynamoDB Local). Table names are
resolved from env vars (TABLE_SOURCES, TABLE_BULLETINS, ...) set by SAM.
All tables use `id` (string) as the single hash key per plan.md §3.
"""
import os
import boto3
from boto3.dynamodb.conditions import Attr

_resource = None


def _dynamodb():
    global _resource
    if _resource is None:
        endpoint = os.environ.get("DYNAMODB_ENDPOINT")
        # DynamoDB Local ignores credentials; dummy ones keep the database
        # working even when the Bedrock credentials are missing or expired.
        kwargs = ({"endpoint_url": endpoint, "aws_access_key_id": "local",
                   "aws_secret_access_key": "local"}
                  if endpoint else {})
        _resource = boto3.resource("dynamodb", **kwargs)
    return _resource


def table(name_env):
    """Resolve a table handle from an env-var name (e.g. 'TABLE_SOURCES')."""
    return _dynamodb().Table(os.environ[name_env])


def get(name_env, item_id):
    """Return the item with `id = item_id`, or None."""
    resp = table(name_env).get_item(Key={"id": item_id})
    return resp.get("Item")


def put(name_env, item):
    """Insert or overwrite an item. `item` must include an `id` field."""
    table(name_env).put_item(Item=item)
    return item


def scan(name_env, filter_expr=None):
    """Scan a whole table. Hackathon-scale only (tens of items per table)."""
    kwargs = {}
    if filter_expr is not None:
        kwargs["FilterExpression"] = filter_expr
    items = []
    resp = table(name_env).scan(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        resp = table(name_env).scan(**kwargs)
        items.extend(resp.get("Items", []))
    return items


def update(name_env, item_id, updates):
    """SET each field in `updates` on the given item. Uses expression attribute
    names so reserved DynamoDB keywords (status, name, ...) don't blow up."""
    if not updates:
        return get(name_env, item_id)
    names = {}
    values = {}
    parts = []
    for i, (k, v) in enumerate(updates.items()):
        nk = f"#f{i}"
        vk = f":v{i}"
        names[nk] = k
        values[vk] = v
        parts.append(f"{nk} = {vk}")
    resp = table(name_env).update_item(
        Key={"id": item_id},
        UpdateExpression="SET " + ", ".join(parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def append(name_env, item_id, field, value, max_len=None):
    """Append `value` to a list-typed field. Creates the list if missing.
    If `max_len` is set, truncates to keep only the newest `max_len` entries
    (useful for the trace log on the system singleton)."""
    current = get(name_env, item_id) or {}
    lst = list(current.get(field) or [])
    lst.append(value)
    if max_len is not None and len(lst) > max_len:
        lst = lst[-max_len:]
    return update(name_env, item_id, {field: lst})


__all__ = ["table", "get", "put", "scan", "update", "append", "Attr"]
