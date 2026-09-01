INSERT INTO audit.quality_rejects
SELECT
    batch_id,
    'bronze.stays',
    source_file,
    source_row_number,
    stay_id,
    multiIf(
        empty(trimBoth(stay_id)), 'STAY_ID_MISSING',
        empty(patient_key) OR length(patient_key) != 64, 'STAY_PATIENT_KEY_INVALID',
        empty(trimBoth(service_code)), 'STAY_SERVICE_CODE_MISSING',
        admission_ts IS NULL, 'STAY_ADMISSION_TS_INVALID',
        discharge_ts IS NOT NULL AND discharge_ts < admission_ts, 'STAY_DISCHARGE_BEFORE_ADMISSION',
        lowerUTF8(trimBoth(ifNull(admission_mode_raw, ''))) NOT IN ('urgence', 'programme', 'mutation'), 'STAY_ADMISSION_MODE_INVALID',
        discharge_ts IS NOT NULL AND empty(trimBoth(ifNull(discharge_mode_raw, ''))), 'STAY_DISCHARGE_MODE_MISSING',
        discharge_ts IS NULL AND NOT empty(trimBoth(ifNull(discharge_mode_raw, ''))), 'STAY_ONGOING_WITH_DISCHARGE_MODE',
        patient_key NOT IN (SELECT patient_key FROM silver.dim_patient FINAL), 'STAY_UNKNOWN_PATIENT',
        service_code NOT IN (SELECT service_code FROM silver.dim_service FINAL), 'STAY_UNKNOWN_SERVICE',
        stay_id IN (
            SELECT stay_id FROM bronze.stays
            WHERE batch_id = {batch_id:UUID}
            GROUP BY stay_id HAVING count() > 1
        ), 'STAY_DUPLICATE_ID',
        'STAY_UNKNOWN_ERROR'
    ),
    'Séjour rejeté par une règle de cohérence Silver',
    now64(3, 'UTC')
FROM bronze.stays
WHERE batch_id = {batch_id:UUID}
  AND (
      empty(trimBoth(stay_id))
      OR empty(patient_key) OR length(patient_key) != 64
      OR empty(trimBoth(service_code))
      OR admission_ts IS NULL
      OR (discharge_ts IS NOT NULL AND discharge_ts < admission_ts)
      OR lowerUTF8(trimBoth(ifNull(admission_mode_raw, ''))) NOT IN ('urgence', 'programme', 'mutation')
      OR (discharge_ts IS NOT NULL AND empty(trimBoth(ifNull(discharge_mode_raw, ''))))
      OR (discharge_ts IS NULL AND NOT empty(trimBoth(ifNull(discharge_mode_raw, ''))))
      OR patient_key NOT IN (SELECT patient_key FROM silver.dim_patient FINAL)
      OR service_code NOT IN (SELECT service_code FROM silver.dim_service FINAL)
      OR stay_id IN (
          SELECT stay_id FROM bronze.stays
          WHERE batch_id = {batch_id:UUID}
          GROUP BY stay_id HAVING count() > 1
      )
  );

INSERT INTO silver.fact_stay
SELECT
    trimBoth(stay_id),
    CAST(patient_key, 'FixedString(64)'),
    trimBoth(service_code),
    toDate(admission_ts),
    if(discharge_ts IS NULL, NULL, toDate(discharge_ts)),
    assumeNotNull(admission_ts),
    discharge_ts,
    lowerUTF8(trimBoth(ifNull(admission_mode_raw, ''))),
    if(discharge_ts IS NULL, NULL, lowerUTF8(trimBoth(ifNull(discharge_mode_raw, '')))),
    if(discharge_ts IS NULL, NULL, dateDiff('hour', admission_ts, discharge_ts)),
    discharge_ts IS NULL,
    source_date,
    source_file,
    source_row_number,
    batch_id,
    now64(3, 'UTC')
FROM bronze.stays
WHERE batch_id = {batch_id:UUID}
  AND NOT empty(trimBoth(stay_id))
  AND NOT empty(patient_key) AND length(patient_key) = 64
  AND NOT empty(trimBoth(service_code))
  AND admission_ts IS NOT NULL
  AND (discharge_ts IS NULL OR discharge_ts >= admission_ts)
  AND lowerUTF8(trimBoth(ifNull(admission_mode_raw, ''))) IN ('urgence', 'programme', 'mutation')
  AND (
      (discharge_ts IS NULL AND empty(trimBoth(ifNull(discharge_mode_raw, ''))))
      OR (discharge_ts IS NOT NULL AND NOT empty(trimBoth(ifNull(discharge_mode_raw, ''))))
  )
  AND patient_key IN (SELECT patient_key FROM silver.dim_patient FINAL)
  AND service_code IN (SELECT service_code FROM silver.dim_service FINAL)
  AND stay_id NOT IN (
      SELECT stay_id FROM bronze.stays
      WHERE batch_id = {batch_id:UUID}
      GROUP BY stay_id HAVING count() > 1
  );

INSERT INTO silver.dim_date
SELECT DISTINCT
    date_key,
    toDayOfMonth(date_key),
    toISOWeek(date_key),
    toMonth(date_key),
    toYear(date_key),
    {batch_id:UUID},
    now64(3, 'UTC')
FROM
(
    SELECT admission_date_key AS date_key
    FROM silver.fact_stay WHERE batch_id = {batch_id:UUID}
    UNION ALL
    SELECT assumeNotNull(discharge_date_key) AS date_key
    FROM silver.fact_stay
    WHERE batch_id = {batch_id:UUID} AND discharge_date_key IS NOT NULL
);
