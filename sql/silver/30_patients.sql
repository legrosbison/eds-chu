INSERT INTO audit.quality_rejects
SELECT
    batch_id,
    'bronze.patients',
    source_file,
    source_row_number,
    patient_key,
    multiIf(
        patient_key = '' OR length(patient_key) != 64, 'PATIENT_KEY_INVALID',
        birth_year IS NULL OR birth_year < 1900 OR birth_year > toYear(source_date), 'PATIENT_BIRTH_YEAR_INVALID',
        upperUTF8(trimBoth(ifNull(sex_raw, ''))) NOT IN ('M', 'F'), 'PATIENT_SEX_INVALID',
        empty(trimBoth(ifNull(region_code, ''))), 'PATIENT_REGION_MISSING',
        'PATIENT_UNKNOWN_ERROR'
    ),
    'Patient rejeté pendant la normalisation Silver',
    now64(3, 'UTC')
FROM bronze.patients
WHERE batch_id = {batch_id:UUID}
  AND (
      patient_key = '' OR length(patient_key) != 64
      OR birth_year IS NULL OR birth_year < 1900 OR birth_year > toYear(source_date)
      OR upperUTF8(trimBoth(ifNull(sex_raw, ''))) NOT IN ('M', 'F')
      OR empty(trimBoth(ifNull(region_code, '')))
  );

INSERT INTO silver.dim_patient
SELECT
    CAST(patient_key, 'FixedString(64)'),
    argMax(birth_year, source_row_number),
    argMax(upperUTF8(trimBoth(ifNull(sex_raw, ''))), source_row_number),
    argMax(trimBoth(ifNull(region_code, '')), source_row_number),
    max(source_date),
    batch_id,
    now64(3, 'UTC')
FROM bronze.patients
WHERE batch_id = {batch_id:UUID}
  AND patient_key != '' AND length(patient_key) = 64
  AND birth_year IS NOT NULL AND birth_year >= 1900 AND birth_year <= toYear(source_date)
  AND upperUTF8(trimBoth(ifNull(sex_raw, ''))) IN ('M', 'F')
  AND NOT empty(trimBoth(ifNull(region_code, '')))
GROUP BY patient_key, batch_id;
