CREATE DATABASE IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.dim_patient
(
    patient_key FixedString(64),
    birth_year UInt16,
    sex LowCardinality(String),
    region_code String,
    source_date Date,
    batch_id UUID,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(source_date)
ORDER BY patient_key;

CREATE TABLE IF NOT EXISTS silver.dim_service
(
    service_code String,
    service_label String,
    categorie Nullable(String),
    capacite_lits Nullable(UInt16),
    pole Nullable(String),
    source_date Date,
    batch_id UUID,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(source_date)
ORDER BY service_code;

-- Migration non destructive pour une base créée avant le dépôt du 2026-08-29.
ALTER TABLE silver.dim_service
    ADD COLUMN IF NOT EXISTS categorie Nullable(String) AFTER service_label;

ALTER TABLE silver.dim_service
    ADD COLUMN IF NOT EXISTS capacite_lits Nullable(UInt16) AFTER categorie;

ALTER TABLE silver.dim_service
    ADD COLUMN IF NOT EXISTS pole Nullable(String) AFTER capacite_lits;

CREATE TABLE IF NOT EXISTS silver.dim_diagnosis
(
    diagnosis_code String,
    diagnosis_label String,
    source_date Date,
    batch_id UUID,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(source_date)
ORDER BY diagnosis_code;

CREATE TABLE IF NOT EXISTS silver.dim_ccam
(
    code_ccam String,
    libelle String,
    tarif_euros Decimal(10, 2),
    source_date Date,
    batch_id UUID,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(source_date)
ORDER BY code_ccam;

CREATE TABLE IF NOT EXISTS silver.dim_date
(
    date_key Date,
    day UInt8,
    week UInt8,
    month UInt8,
    year UInt16,
    batch_id UUID,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(processed_at)
ORDER BY date_key;

CREATE TABLE IF NOT EXISTS silver.fact_stay
(
    stay_id String,
    patient_key FixedString(64),
    service_code String,
    admission_date_key Date,
    discharge_date_key Nullable(Date),
    admission_ts DateTime64(3, 'UTC'),
    discharge_ts Nullable(DateTime64(3, 'UTC')),
    admission_mode LowCardinality(String),
    discharge_mode LowCardinality(Nullable(String)),
    length_of_stay_hours Nullable(Int32),
    is_ongoing Bool,
    source_date Date,
    source_file String,
    source_row_number UInt64,
    batch_id UUID,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(processed_at)
ORDER BY stay_id;

CREATE TABLE IF NOT EXISTS silver.fact_diagnosis
(
    stay_id String,
    diagnosis_code String,
    diagnosis_type LowCardinality(String),
    patient_key FixedString(64),
    service_code String,
    admission_date_key Date,
    source_date Date,
    source_file String,
    source_row_number UInt64,
    batch_id UUID,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(processed_at)
ORDER BY (stay_id, diagnosis_code, diagnosis_type);

CREATE TABLE IF NOT EXISTS silver.fact_monitoring
(
    stay_id String,
    ts DateTime64(6, 'UTC'),
    patient_key FixedString(64),
    service_code String,
    measurement_date_key Date,
    heart_rate Int16,
    spo2 Int16,
    temp_c Decimal(4, 1),
    source_date Date,
    source_file String,
    source_row_number UInt64,
    batch_id UUID,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(processed_at)
PARTITION BY toYYYYMM(measurement_date_key)
ORDER BY (measurement_date_key, stay_id, ts);

CREATE TABLE IF NOT EXISTS silver.fact_acte
(
    stay_id String,
    service_code String,
    code_ccam String,
    act_date_key Date,
    acte_ts DateTime64(3, 'UTC'),
    source_date Date,
    source_file String,
    source_row_number UInt64,
    batch_id UUID,
    processed_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(processed_at)
PARTITION BY toYYYYMM(act_date_key)
ORDER BY (act_date_key, service_code, stay_id, code_ccam, acte_ts);
