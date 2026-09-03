INSERT INTO audit.quality_rejects
WITH exploded AS
(
    SELECT
        stay_id,
        diagnostic.code_cim10 AS diagnosis_code,
        diagnostic.diagnosis_type AS diagnosis_type,
        source_file,
        source_row_number,
        batch_id
    FROM bronze.diagnostics
    ARRAY JOIN diagnostics AS diagnostic
    WHERE batch_id = {batch_id:UUID}
)
SELECT
    batch_id,
    'bronze.diagnostics',
    source_file,
    source_row_number,
    concat(stay_id, ':', diagnosis_code),
    multiIf(
        empty(trimBoth(stay_id)), 'DIAGNOSIS_STAY_ID_MISSING',
        empty(trimBoth(diagnosis_code)), 'DIAGNOSIS_CODE_MISSING',
        lowerUTF8(trimBoth(diagnosis_type)) NOT IN ('principal', 'associe'), 'DIAGNOSIS_TYPE_INVALID',
        stay_id NOT IN (SELECT stay_id FROM bronze.stays), 'DIAGNOSIS_UNKNOWN_STAY',
        diagnosis_code NOT IN (SELECT diagnosis_code FROM silver.dim_diagnosis FINAL), 'DIAGNOSIS_UNKNOWN_CIM10',
        'DIAGNOSIS_UNKNOWN_ERROR'
    ),
    'Diagnostic rejeté pendant l’aplatissement Silver',
    now64(3, 'UTC')
FROM exploded
WHERE empty(trimBoth(stay_id))
   OR empty(trimBoth(diagnosis_code))
   OR lowerUTF8(trimBoth(diagnosis_type)) NOT IN ('principal', 'associe')
   OR stay_id NOT IN (SELECT stay_id FROM bronze.stays)
   OR diagnosis_code NOT IN (SELECT diagnosis_code FROM silver.dim_diagnosis FINAL);

INSERT INTO silver.fact_diagnosis
WITH exploded AS
(
    SELECT
        stay_id,
        diagnostic.code_cim10 AS diagnosis_code,
        diagnostic.diagnosis_type AS diagnosis_type,
        source_date,
        source_file,
        source_row_number,
        batch_id
    FROM bronze.diagnostics
    ARRAY JOIN diagnostics AS diagnostic
    WHERE batch_id = {batch_id:UUID}
)
SELECT DISTINCT
    trimBoth(e.stay_id),
    trimBoth(e.diagnosis_code),
    lowerUTF8(trimBoth(e.diagnosis_type)),
    CAST(s.patient_key, 'FixedString(64)'),
    trimBoth(s.service_code),
    toDate(assumeNotNull(s.admission_ts)),
    e.source_date,
    e.source_file,
    e.source_row_number,
    e.batch_id,
    now64(3, 'UTC')
FROM exploded AS e
INNER JOIN
(
    -- Un diagnostic reste exploitable même si la durée de son séjour est
    -- incohérente. Bronze sert donc uniquement à récupérer son contexte.
    SELECT
        stay_id,
        argMax(patient_key, tuple(source_date, ingested_at)) AS patient_key,
        argMax(service_code, tuple(source_date, ingested_at)) AS service_code,
        argMax(admission_ts, tuple(source_date, ingested_at)) AS admission_ts
    FROM
    (
        SELECT
            trimBoth(stay_id) AS stay_id,
            patient_key,
            service_code,
            admission_ts,
            source_date,
            ingested_at
        FROM bronze.stays
        WHERE NOT empty(trimBoth(stay_id))
    )
    GROUP BY stay_id
) AS s ON trimBoth(e.stay_id) = s.stay_id
WHERE NOT empty(trimBoth(e.stay_id))
  AND NOT empty(trimBoth(e.diagnosis_code))
  AND lowerUTF8(trimBoth(e.diagnosis_type)) IN ('principal', 'associe')
  AND e.diagnosis_code IN (SELECT diagnosis_code FROM silver.dim_diagnosis FINAL)
  AND length(s.patient_key) = 64
  AND s.patient_key IN (SELECT patient_key FROM silver.dim_patient FINAL)
  AND s.service_code IN (SELECT service_code FROM silver.dim_service FINAL)
  AND s.admission_ts IS NOT NULL;
