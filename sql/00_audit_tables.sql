CREATE DATABASE IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.ingestion_files
(
    batch_id UUID,
    source_file String,
    source_checksum FixedString(64),
    lake_file String,
    source_date Date,
    target_table LowCardinality(String),
    status LowCardinality(String),
    row_count UInt64,
    error_message String,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (source_file, source_checksum, target_table, processed_at);

CREATE TABLE IF NOT EXISTS audit.silver_batches
(
    batch_id UUID,
    source_table LowCardinality(String),
    target_table LowCardinality(String),
    status LowCardinality(String),
    accepted_rows UInt64,
    rejected_rows UInt64,
    error_message String,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (batch_id, target_table, processed_at);

CREATE TABLE IF NOT EXISTS audit.quality_rejects
(
    batch_id UUID,
    source_table LowCardinality(String),
    source_file String,
    source_row_number UInt64,
    record_key String,
    rule_code LowCardinality(String),
    rule_detail String,
    rejected_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (source_table, rule_code, batch_id, source_row_number);

-- Journal append-only d'une exécution complète. Une exécution écrit d'abord
-- RUNNING, puis SUCCESS ou FAILED avec le même run_id.
CREATE TABLE IF NOT EXISTS audit.pipeline_runs
(
    run_id UUID,
    step LowCardinality(String),
    status LowCardinality(String),
    message String,
    recorded_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (run_id, recorded_at);
