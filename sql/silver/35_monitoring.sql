INSERT INTO audit.quality_rejects
SELECT
    b.batch_id,
    'bronze.monitoring',
    b.source_file,
    b.source_row_number,
    concat(b.stay_id, ':', ifNull(toString(b.ts), '<null>')),
    multiIf(
        empty(trimBoth(b.stay_id)), 'MONITORING_STAY_ID_MISSING',
        b.ts IS NULL, 'MONITORING_TS_INVALID',
        b.heart_rate IS NULL, 'MONITORING_HEART_RATE_MISSING',
        b.heart_rate < 20 OR b.heart_rate > 250, 'MONITORING_HEART_RATE_OUT_OF_RANGE',
        b.spo2 IS NULL, 'MONITORING_SPO2_MISSING',
        b.spo2 < 50 OR b.spo2 > 100, 'MONITORING_SPO2_OUT_OF_RANGE',
        b.temp_c IS NULL, 'MONITORING_TEMP_MISSING',
        b.temp_c < 30 OR b.temp_c > 45, 'MONITORING_TEMP_OUT_OF_RANGE',
        b.stay_id NOT IN (SELECT stay_id FROM bronze.stays), 'MONITORING_UNKNOWN_STAY',
        'MONITORING_UNKNOWN_ERROR'
    ),
    'Relevé rejeté par une règle de qualité Silver',
    now64(3, 'UTC')
FROM bronze.monitoring AS b
WHERE b.batch_id = {batch_id:UUID}
  AND (
      empty(trimBoth(b.stay_id))
      OR b.ts IS NULL
      OR b.heart_rate IS NULL OR b.heart_rate < 20 OR b.heart_rate > 250
      OR b.spo2 IS NULL OR b.spo2 < 50 OR b.spo2 > 100
      OR b.temp_c IS NULL OR b.temp_c < 30 OR b.temp_c > 45
      OR b.stay_id NOT IN (SELECT stay_id FROM bronze.stays)
  );

INSERT INTO silver.fact_monitoring
SELECT DISTINCT
    b.stay_id,
    assumeNotNull(b.ts),
    CAST(s.patient_key, 'FixedString(64)'),
    trimBoth(s.service_code),
    toDate(assumeNotNull(b.ts)),
    assumeNotNull(b.heart_rate),
    assumeNotNull(b.spo2),
    assumeNotNull(b.temp_c),
    b.source_date,
    b.source_file,
    b.source_row_number,
    b.batch_id,
    now64(3, 'UTC')
FROM bronze.monitoring AS b
INNER JOIN
(
    -- Les bornes du séjour sont contrôlées pour fact_stay, mais elles ne
    -- suppriment pas en cascade une mesure capteur valide.
    SELECT
        stay_id,
        argMax(patient_key, tuple(source_date, ingested_at)) AS patient_key,
        argMax(service_code, tuple(source_date, ingested_at)) AS service_code
    FROM
    (
        SELECT
            trimBoth(stay_id) AS stay_id,
            patient_key,
            service_code,
            source_date,
            ingested_at
        FROM bronze.stays
        WHERE NOT empty(trimBoth(stay_id))
    )
    GROUP BY stay_id
) AS s ON trimBoth(b.stay_id) = s.stay_id
WHERE b.batch_id = {batch_id:UUID}
  AND b.ts IS NOT NULL
  AND b.heart_rate IS NOT NULL AND b.heart_rate BETWEEN 20 AND 250
  AND b.spo2 IS NOT NULL AND b.spo2 BETWEEN 50 AND 100
  AND b.temp_c IS NOT NULL AND b.temp_c BETWEEN 30 AND 45
  AND length(s.patient_key) = 64
  AND s.patient_key IN (SELECT patient_key FROM silver.dim_patient FINAL)
  AND s.service_code IN (SELECT service_code FROM silver.dim_service FINAL);

INSERT INTO silver.dim_date
SELECT DISTINCT
    measurement_date_key,
    toDayOfMonth(measurement_date_key),
    toISOWeek(measurement_date_key),
    toMonth(measurement_date_key),
    toYear(measurement_date_key),
    {batch_id:UUID},
    now64(3, 'UTC')
FROM silver.fact_monitoring
WHERE batch_id = {batch_id:UUID};
