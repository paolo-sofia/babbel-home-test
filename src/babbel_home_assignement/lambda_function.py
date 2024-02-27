import datetime
import json
import os
from typing import TypeAlias

import duckdb
import pandas as pd
import pytz
import redis

JSONType: TypeAlias = dict[str, "JSON"]


def initialize_redis_client() -> redis.StrictRedis:
    # Connect to Redis, S3 and duckdb
    return redis.StrictRedis(host=os.getenv("REDIS_HOST"), port=os.getenv("REDIS_PORT"), db=os.getenv("REDIS_DB"))


def initialize_duckdb_client() -> duckdb.DuckDBPyConnection:
    # database="" means to use memory instead of persisting to file
    duckdb_conn: duckdb.DuckDBPyConnection = duckdb.connect(database="")

    # initialize duckdb s3 config
    return duckdb_conn.execute(
        f"""
    CREATE SECRET secret1 (
        TYPE S3,
        KEY_ID '{os.getenv("S3_KEY")}',
        SECRET '{os.getenv("S3_SECRET")}',
        REGION 'eu-central-1'
    );
    """
    )


def get_sql_query() -> str:
    return """
COPY
(SELECT
    event_uuid,
    event_name,
    split_part(event_name, ':', 1) as event_type,
    split_part(event_name, ':', 2) as event_subtype,
    created_at,
    to_timestamp(created_at) as created_datetime,
    strftime(created_datetime, '%Y-%m-%d') as date,
    to_json(payload) as payload
FROM events
WHERE event_uuid NOT IN {cached_uuid_keys}
)
TO 's3://{bucket_name}' (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (date, event_type), FILENAME_PATTERN "{{uuid}}", OVERWRITE_OR_IGNORE true);
"""


def convert_list_to_sql_string(list_to_convert: list) -> str | None:
    """Convert a list of values to a string used in a sql query.

    Args:
        list_to_convert: The list of values to convert.

    Returns:
        The SQL string representation of the list.

    Raises:
        None.

    Examples:
        >>> convert_list_to_sql_string([1, 2, 3])
        "('1','2','3')"
    """
    try:
        list_to_convert: list[str] = [str(x) for x in list_to_convert]
    except Exception:
        print("Error converting list to a list of strings")
        return None
    return f"""('{"','".join(list_to_convert)}')"""


def lambda_handler(event: JSONType, context) -> JSONType:
    """Main lambda function. It executes the sql query and save the results to s3 bucket.

    Args:
        event: The event data to preprocess and store.
        context: The context object.

    Returns:
        A json response containing the status code and the exposed metrics.

    Raises:
        None.
    """
    duckdb_conn: duckdb.DuckDBPyConnection = initialize_duckdb_client()
    redis_client: redis.StrictRedis = initialize_redis_client()

    # first convert the event json to a pandas dataframe
    event_data: pd.DataFrame = pd.DataFrame(event.get("data", {}))

    if event_data.empty:
        duckdb_conn.close()
        redis_client.close()
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "message": "No events were received",
                    "num_events_processed": 0,
                    "num_duplicate_events": 0,
                    "timestamp": datetime.datetime.now(tz=pytz.timezone("Europe/Berlin")).timestamp(),
                }
            ),
        }

    # explicitly cast payload to string to be parsed by duckdb engine to a json. It could fail otherwise
    event_data["payload"] = event_data["payload"].apply(lambda row: f"'{row}'")
    duckdb_conn = duckdb_conn.register("events", event_data)

    # load the already processed uuid from cache and use them to create the sql query to execute.
    redis_keys: list[str] = redis_client.keys(pattern="*")
    redis_keys_sql: str = convert_list_to_sql_string(redis_keys)

    sql_query = get_sql_query()

    try:
        # executes the sql query and save the results to s3
        duckdb_conn.execute(sql_query.format(cached_uuid_keys=redis_keys_sql, bucket_name=os.getenv("S3_BUCKET")))
    except Exception as e:
        duckdb_conn.close()
        redis_client.close()
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "message": e,
                    "num_events_processed": 0,
                    "num_duplicate_events": 0,
                    "timestamp": datetime.datetime.now(tz=pytz.timezone("Europe/Berlin")).timestamp(),
                }
            ),
        }

    # put the event_uuid in cache
    for event_uuid in event_data["event_uuid"]:
        # Store event_uuid in Redis to mark as processed and set expiration time to 7 days
        redis_client.set(event_uuid, value=event_uuid)
        redis_client.expire(event_uuid, time=60 * 60 * 24 * 7)

    # compute metrics to be exposed.
    num_duplicate_events: int = event_data.query("event_uuid in (@redis_keys)").shape[0]
    num_events_processed: int = event_data.shape[0]
    current_timestamp: float = datetime.datetime.now(tz=pytz.timezone("Europe/Berlin")).timestamp()

    duckdb_conn.close()
    redis_client.close()

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "num_events_processed": num_events_processed,
                "num_duplicate_events": num_duplicate_events,
                "timestamp": current_timestamp,
            }
        ),
    }
