CREATE DATABASE IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.kpi_dms_service
(
    service_code String,
    service_label String,
    stay_count UInt64,
    average_length_of_stay_days Float64,
    average_length_of_stay_hours Float64,
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY service_code;

CREATE TABLE IF NOT EXISTS gold.kpi_readmission_30d
(
    readmission_30d_count UInt64,
    stay_count UInt64,
    readmission_30d_rate_pct Float64,
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY tuple();

CREATE TABLE IF NOT EXISTS gold.kpi_emergency_daily
(
    date_key Date,
    passage_count UInt64,
    ongoing_stay_count UInt64,
    average_length_hours Float64,
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY date_key;

CREATE TABLE IF NOT EXISTS gold.kpi_monitoring_alert_daily
(
    date_key Date,
    measurement_count UInt64,
    alert_count UInt64,
    alert_rate_pct Float64,
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY date_key;

CREATE TABLE IF NOT EXISTS gold.kpi_pathology_prevalence
(
    diagnosis_code String,
    diagnosis_label String,
    patient_count UInt64,
    publishable_patient_count Nullable(UInt64),
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY diagnosis_code;

CREATE TABLE IF NOT EXISTS gold.kpi_cohort_demographics
(
    diagnosis_code String,
    age_band LowCardinality(String),
    sex LowCardinality(String),
    patient_count UInt64,
    publishable_patient_count Nullable(UInt64),
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (diagnosis_code, age_band, sex);

CREATE TABLE IF NOT EXISTS gold.kpi_activity_dms_category
(
    categorie String,
    stay_count UInt64,
    closed_stay_count UInt64,
    average_length_of_stay_days Float64,
    average_length_of_stay_hours Float64,
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY categorie;

CREATE TABLE IF NOT EXISTS gold.kpi_acts_service
(
    service_code String,
    service_label String,
    act_count UInt64,
    stay_with_act_count UInt64,
    average_acts_per_stay Float64,
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY service_code;

CREATE TABLE IF NOT EXISTS gold.kpi_acts_type
(
    code_ccam String,
    act_label String,
    act_count UInt64,
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY code_ccam;

CREATE TABLE IF NOT EXISTS gold.kpi_act_density_bed
(
    service_code String,
    service_label String,
    act_count UInt64,
    capacite_lits Nullable(UInt16),
    acts_per_bed Nullable(Float64),
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY service_code;

CREATE TABLE IF NOT EXISTS gold.kpi_billed_amount_service
(
    service_code String,
    service_label String,
    act_count UInt64,
    billed_amount_euros Decimal(18, 2),
    computed_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY service_code;
