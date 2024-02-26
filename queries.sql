COPY
(SELECT
    event_uuid,
    event_name,
    split_part(event_name, ':', 1) as event_type,
    split_part(event_name, ':', 2) as event_subtype,
    created_at,
    to_timestamp(created_at) as created_datetime,
    strftime(created_datetime, '%Y-%m-%d') as date,
    payload
FROM events
WHERE event_uuid NOT IN {}
)
TO 'data/s3' (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (date, event_type), FILENAME_PATTERN "{{uuid}}", OVERWRITE_OR_IGNORE true);
