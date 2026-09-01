CREATE DATABASE IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.patients
(
    patient_key String,
    birth_year Nullable(UInt16),
    sex_raw Nullable(String),
    region_code Nullable(String),
    source_date Date,
    source_file String,
    source_row_number UInt64,
    batch_id UUID,
    ingested_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (source_date, batch_id, source_row_number);

CREATE TABLE IF NOT EXISTS bronze.stays
(
    stay_id String,
    patient_key String,
    service_code String,
    admission_ts Nullable(DateTime64(3, 'UTC')),
    discharge_ts Nullable(DateTime64(3, 'UTC')),
    admission_mode_raw Nullable(String),
    discharge_mode_raw Nullable(String),
    source_date Date,
    source_file String,
    source_row_number UInt64,
    batch_id UUID,
    ingested_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (source_date, batch_id, source_row_number);

CREATE TABLE IF NOT EXISTS bronze.diagnostics
(
    stay_id String,
    diagnostics Array(Tuple(code_cim10 String, diagnosis_type String)),
    source_date Date,
    source_file String,
    source_row_number UInt64,
    batch_id UUID,
    ingested_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (source_date, batch_id, source_row_number);

CREATE TABLE IF NOT EXISTS bronze.monitoring
(
    stay_id String,
    ts Nullable(DateTime64(6, 'UTC')),
    heart_rate Nullable(Int16),
    spo2 Nullable(Int16),
    temp_c Nullable(Decimal(4, 1)),
    source_date Date,
    source_file String,
    source_row_number UInt64,
    batch_id UUID,
    ingested_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(source_date)
ORDER BY (source_date, stay_id, batch_id, source_row_number);

CREATE TABLE IF NOT EXISTS bronze.services
(
    service_code String,
    service_label Nullable(String),
    source_date Date,
    source_file String,
    source_row_number UInt64,
    batch_id UUID,
    ingested_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (source_date, batch_id, source_row_number);

CREATE TABLE IF NOT EXISTS bronze.cim10
(
    code_cim10 String,
    diagnosis_label Nullable(String),
    source_date Date,
    source_file String,
    source_row_number UInt64,
    batch_id UUID,
    ingested_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (source_date, batch_id, source_row_number);
