INSERT INTO audit.quality_rejects
WITH exploded AS
(
    SELECT
        stay_id,
        tupleElement(diagnostic, 1) AS diagnosis_code,
        tupleElement(diagnostic, 2) AS diagnosis_type,
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
        stay_id NOT IN (SELECT stay_id FROM silver.fact_stay FINAL), 'DIAGNOSIS_UNKNOWN_OR_REJECTED_STAY',
        diagnosis_code NOT IN (SELECT diagnosis_code FROM silver.dim_diagnosis FINAL), 'DIAGNOSIS_UNKNOWN_CIM10',
        'DIAGNOSIS_UNKNOWN_ERROR'
    ),
    'Diagnostic rejeté pendant l’aplatissement Silver',
    now64(3, 'UTC')
FROM exploded
WHERE empty(trimBoth(stay_id))
   OR empty(trimBoth(diagnosis_code))
   OR lowerUTF8(trimBoth(diagnosis_type)) NOT IN ('principal', 'associe')
   OR stay_id NOT IN (SELECT stay_id FROM silver.fact_stay FINAL)
   OR diagnosis_code NOT IN (SELECT diagnosis_code FROM silver.dim_diagnosis FINAL);

INSERT INTO silver.fact_diagnosis
WITH exploded AS
(
    SELECT
        stay_id,
        tupleElement(diagnostic, 1) AS diagnosis_code,
        tupleElement(diagnostic, 2) AS diagnosis_type,
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
    s.patient_key,
    s.service_code,
    s.admission_date_key,
    e.source_date,
    e.source_file,
    e.source_row_number,
    e.batch_id,
    now64(3, 'UTC')
FROM exploded AS e
INNER JOIN (SELECT * FROM silver.fact_stay FINAL) AS s ON e.stay_id = s.stay_id
WHERE NOT empty(trimBoth(e.stay_id))
  AND NOT empty(trimBoth(e.diagnosis_code))
  AND lowerUTF8(trimBoth(e.diagnosis_type)) IN ('principal', 'associe')
  AND e.diagnosis_code IN (SELECT diagnosis_code FROM silver.dim_diagnosis FINAL);
