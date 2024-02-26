import pathlib
from typing import TypeAlias

import boto3
import pandas as pd
import redis
import duckdb

JSONType: TypeAlias = dict[str, "JSON"]

# Connect to Redis
redis_client = redis.StrictRedis(host="redis-host", port=6379, db=0)

# Connect to S3
s3_client = boto3.client("s3")

global duckdb_conn

duckdb_conn: duckdb.DuckDBPyConnection = duckdb.connect(database="duckdb.db")


def convert_list_to_sql_string(list_to_convert: list) -> str | None:
    try:
        list_to_convert: list[str] = [str(x) for x in list_to_convert]
    except Exception:
        print("Error converting list to a list of strings")
        return
    return f"""('{"','".join(list_to_convert)}')"""


def load_sql_queries_from_file() -> list[str]:
    with pathlib.Path("queries.sql").open("r") as file:
        file_content = file.read()

    return [query.strip() for query in file_content.split(";")]


def cache_events_uuid(events: list[str]) -> None:
    for event_uuid in events:
        # Store event_uuid in Redis to mark as processed
        redis_client.set(event_uuid, value=event_uuid)
        redis_client.expire(event_uuid, time=60 * 60 * 24 * 7)  # Set expiration time to 7 days


def preprocess_and_store(event: JSONType, context):
    # Iterate over batch of events
    global duckdb_conn

    event: pd.DataFrame = pd.DataFrame(event)
    duckdb_conn = duckdb_conn.register("events", event)

    redis_keys: list[str] = redis_client.keys(pattern="*")
    sql_queries = load_sql_queries_from_file()
    redis_keys_sql: str = convert_list_to_sql_string(redis_keys)

    duckdb_conn.execute(sql_queries[0].format(redis_keys_sql))

    num_duplicate_events: int = event.query("event_uuid in (@redis_keys)").shape[0]

    cache_events_uuid(event["event_uuid"])
