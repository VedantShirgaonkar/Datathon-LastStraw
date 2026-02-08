-- ClickHouse events table used by pr_merge_agent
-- Matches columns shown in the screenshot:
-- event_id, timestamp, source, event_type, project_id, actor_id, entity_id, entity_type, metadata

CREATE TABLE IF NOT EXISTS events (
    event_id String,
    timestamp DateTime64(3, 'UTC'),
    source LowCardinality(String),
    event_type LowCardinality(String),
    project_id String,
    actor_id String,
    entity_id String,
    entity_type LowCardinality(String),
    metadata String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (project_id, timestamp, event_type, entity_id);
