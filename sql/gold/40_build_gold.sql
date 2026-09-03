-- Gold est petit et entièrement dérivé de Silver : on le reconstruit à chaque
-- exécution. TRUNCATE évite les doublons et garde le mécanisme facile à rejouer.
TRUNCATE TABLE gold.kpi_dms_service;

INSERT INTO gold.kpi_dms_service
SELECT
    f.service_code,
    d.service_label,
    count() AS stay_count,
    round(avg(toFloat64(f.length_of_stay_hours) / 24), 2),
    round(avg(toFloat64(f.length_of_stay_hours)), 1),
    now64(3, 'UTC')
FROM (SELECT * FROM silver.fact_stay FINAL) AS f
INNER JOIN (SELECT * FROM silver.dim_service FINAL) AS d USING (service_code)
WHERE f.discharge_ts IS NOT NULL
GROUP BY f.service_code, d.service_label;

TRUNCATE TABLE gold.kpi_readmission_30d;

INSERT INTO gold.kpi_readmission_30d
WITH ordered_stays AS
(
    SELECT
        patient_key,
        admission_ts,
        discharge_ts,
        leadInFrame(toNullable(admission_ts), 1, NULL) OVER
        (
            PARTITION BY patient_key
            ORDER BY admission_ts
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS next_admission_ts
    FROM silver.fact_stay FINAL
)
SELECT
    countIf(
        discharge_ts IS NOT NULL
        AND next_admission_ts IS NOT NULL
        AND next_admission_ts >= discharge_ts
        AND dateDiff('day', discharge_ts, next_admission_ts) <= 30
    ) AS readmission_30d_count,
    (SELECT count() FROM silver.fact_stay FINAL) AS stay_count,
    round(100 * readmission_30d_count / stay_count, 2),
    now64(3, 'UTC')
FROM ordered_stays;

TRUNCATE TABLE gold.kpi_emergency_daily;

INSERT INTO gold.kpi_emergency_daily
SELECT
    admission_date_key,
    count() AS passage_count,
    countIf(discharge_ts IS NULL) AS ongoing_stay_count,
    round(avg(toFloat64(length_of_stay_hours)), 1),
    now64(3, 'UTC')
FROM silver.fact_stay FINAL
WHERE service_code = 'URGENCES'
GROUP BY admission_date_key;

TRUNCATE TABLE gold.kpi_monitoring_alert_daily;

INSERT INTO gold.kpi_monitoring_alert_daily
SELECT
    measurement_date_key,
    count() AS measurement_count,
    countIf(
        spo2 < 92
        OR heart_rate < 50 OR heart_rate > 100
        OR temp_c > 38.5
    ) AS alert_count,
    round(100 * alert_count / measurement_count, 1),
    now64(3, 'UTC')
FROM silver.fact_monitoring FINAL
GROUP BY measurement_date_key;

TRUNCATE TABLE gold.kpi_pathology_prevalence;

INSERT INTO gold.kpi_pathology_prevalence
SELECT
    diagnosis_code,
    diagnosis_label,
    patient_count,
    if(patient_count < 5, NULL, patient_count),
    now64(3, 'UTC')
FROM
(
    SELECT
        f.diagnosis_code,
        d.diagnosis_label,
        uniqExact(f.patient_key) AS patient_count
    FROM (SELECT * FROM silver.fact_diagnosis FINAL) AS f
    INNER JOIN (SELECT * FROM silver.dim_diagnosis FINAL) AS d USING (diagnosis_code)
    GROUP BY f.diagnosis_code, d.diagnosis_label
);

TRUNCATE TABLE gold.kpi_cohort_demographics;

INSERT INTO gold.kpi_cohort_demographics
WITH
    (SELECT max(source_date) FROM silver.dim_patient FINAL) AS reference_date,
    cohorts AS
    (
        SELECT
            f.diagnosis_code,
            concat(
                toString(intDiv(toYear(reference_date) - p.birth_year, 10) * 10),
                '-',
                toString(intDiv(toYear(reference_date) - p.birth_year, 10) * 10 + 9)
            ) AS age_band,
            p.sex,
            uniqExact(f.patient_key) AS patient_count
        FROM (SELECT * FROM silver.fact_diagnosis FINAL) AS f
        INNER JOIN (SELECT * FROM silver.dim_patient FINAL) AS p USING (patient_key)
        WHERE f.diagnosis_type = 'principal'
        GROUP BY f.diagnosis_code, age_band, p.sex
    )
SELECT
    diagnosis_code,
    age_band,
    sex,
    patient_count,
    if(patient_count < 5, NULL, patient_count),
    now64(3, 'UTC')
FROM cohorts;
