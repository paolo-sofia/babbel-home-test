import datetime
import json
import re
from copy import deepcopy
from typing import Self
from unittest import mock

import pytest
import pytz

from src.babbel_home_assignement.lambda_function import JSONType, lambda_handler

current_timestamp: float = datetime.datetime.now(tz=pytz.timezone("Europe/Berlin")).timestamp()


class MockRedis:
    def __init__(self: Self, cache: dict[str, str] | None = None):
        self.cache = cache or {}

    def set(self: Self, key: str, value: str, *args, **kwargs) -> None:
        if self.cache:
            self.cache[key] = value

    def keys(self: Self, pattern: str = ".*") -> list[str]:
        return [key for key in self.cache if re.match(".*", key)]

    def expire(self: Self, key: str, time: int) -> None:
        pass


def get_test_sql_query() -> str:
    return """
SELECT
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
"""


def get_duplicate_events(event: JSONType, redis_cache: dict[str, str]) -> int:
    uuids = [x.get("event_uuid", "") for x in event.get("data", [])]
    return len(set(uuids).intersection(list(redis_cache.keys())))


@pytest.mark.parametrize(
    "event",
    [
        {
            "data": [
                {
                    "event_uuid": "key_2",
                    "event_name": "account:created",
                    "created_at": current_timestamp,
                    "payload": {},
                },
                {
                    "event_uuid": "event_uuid",
                    "event_name": "lesson:started",
                    "created_at": current_timestamp,
                    "payload": {"c": "cc"},
                },
                {
                    "event_uuid": "event_uuid",
                    "event_name": "payment:order:completed",
                    "created_at": current_timestamp,
                    "payload": {"q": "qq", "v": "vv"},
                },
                {
                    "event_uuid": "event_uuid",
                    "event_name": "account:created",
                    "created_at": current_timestamp,
                    "payload": {"gjh": 543, "324": 324},
                },
                {
                    "event_uuid": "event_uuid",
                    "event_name": "lesson:started",
                    "created_at": current_timestamp,
                    "payload": {"asfsad": "ehgr", "afae": "arfwefw"},
                },
            ]
        },
        {
            "data": [
                {
                    "event_uuid": "key_1",
                    "event_name": "account:created",
                    "created_at": current_timestamp,
                    "payload": {},
                }
            ]
        },
    ],
)
@mock.patch("src.babbel_home_assignement.lambda_function.get_sql_query")
@mock.patch("redis.StrictRedis")
def test_lambda_handler(mock_redis: mock.MagicMock, mock_get_sql_query: mock.MagicMock, event: dict):
    mock_get_sql_query.side_effect = get_test_sql_query

    redis_cache = {"key_1": "key_1", "key_2": "key_2"}
    mock_redis_object = MockRedis(deepcopy(redis_cache))
    mock_redis_method = mock.MagicMock()
    mock_redis_method.expire = mock.Mock(side_effect=mock_redis_object.expire)
    mock_redis_method.set = mock.Mock(side_effect=mock_redis_object.set)
    mock_redis_method.keys = mock.Mock(side_effect=mock_redis_object.keys)
    mock_redis.return_value = mock_redis_method

    response: JSONType = lambda_handler(event, context=None)
    body: JSONType = json.loads(response["body"])

    print(body)
    assert response.get("statusCode") == 200
    assert body.get("num_events_processed") == len(event.get("data"))
    assert body.get("num_duplicate_events") == get_duplicate_events(event, redis_cache)


@pytest.mark.parametrize("event", [{"data": []}])
@mock.patch("src.babbel_home_assignement.lambda_function.get_sql_query")
@mock.patch("redis.StrictRedis")
def test_lambda_handler_empty_data(mock_redis: mock.MagicMock, mock_get_sql_query: mock.MagicMock, event: dict):
    mock_get_sql_query.side_effect = get_test_sql_query

    redis_cache = {"key_1": "key_1", "key_2": "key_2"}
    mock_redis_object = MockRedis(deepcopy(redis_cache))
    mock_redis_method = mock.MagicMock()
    mock_redis_method.expire = mock.Mock(side_effect=mock_redis_object.expire)
    mock_redis_method.set = mock.Mock(side_effect=mock_redis_object.set)
    mock_redis_method.keys = mock.Mock(side_effect=mock_redis_object.keys)
    mock_redis.return_value = mock_redis_method

    response: JSONType = lambda_handler(event, context=None)
    body: JSONType = json.loads(response["body"])

    print(body)
    assert response.get("statusCode") == 400
    assert body.get("num_events_processed") == 0
    assert body.get("num_duplicate_events") == 0
