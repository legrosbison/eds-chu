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
        empty(s.stay_id), 'MONITORING_UNKNOWN_OR_REJECTED_STAY',
        b.ts < s.admission_ts, 'MONITORING_BEFORE_ADMISSION',
        s.discharge_ts IS NOT NULL AND b.ts > s.discharge_ts, 'MONITORING_AFTER_DISCHARGE',
        'MONITORING_UNKNOWN_ERROR'
    ),
    'Relevé rejeté par une règle de qualité Silver',
    now64(3, 'UTC')
FROM bronze.monitoring AS b
LEFT JOIN (SELECT * FROM silver.fact_stay FINAL) AS s ON b.stay_id = s.stay_id
WHERE b.batch_id = {batch_id:UUID}
  AND (
      empty(trimBoth(b.stay_id))
      OR b.ts IS NULL
      OR b.heart_rate IS NULL OR b.heart_rate < 20 OR b.heart_rate > 250
      OR b.spo2 IS NULL OR b.spo2 < 50 OR b.spo2 > 100
      OR b.temp_c IS NULL OR b.temp_c < 30 OR b.temp_c > 45
      OR empty(s.stay_id)
      OR b.ts < s.admission_ts
      OR (s.discharge_ts IS NOT NULL AND b.ts > s.discharge_ts)
  );

INSERT INTO silver.fact_monitoring
SELECT DISTINCT
    b.stay_id,
    assumeNotNull(b.ts),
    s.patient_key,
    s.service_code,
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
INNER JOIN (SELECT * FROM silver.fact_stay FINAL) AS s ON b.stay_id = s.stay_id
WHERE b.batch_id = {batch_id:UUID}
  AND b.ts IS NOT NULL
  AND b.heart_rate IS NOT NULL AND b.heart_rate BETWEEN 20 AND 250
  AND b.spo2 IS NOT NULL AND b.spo2 BETWEEN 50 AND 100
  AND b.temp_c IS NOT NULL AND b.temp_c BETWEEN 30 AND 45
  AND b.ts >= s.admission_ts
  AND (s.discharge_ts IS NULL OR b.ts <= s.discharge_ts);

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
