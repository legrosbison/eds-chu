INSERT INTO audit.quality_rejects
SELECT
    batch_id,
    'bronze.cim10',
    source_file,
    source_row_number,
    code_cim10,
    if(empty(trimBoth(code_cim10)), 'CIM10_CODE_MISSING', 'CIM10_LABEL_MISSING'),
    'Référentiel CIM-10 incomplet',
    now64(3, 'UTC')
FROM bronze.cim10
WHERE batch_id = {batch_id:UUID}
  AND (empty(trimBoth(code_cim10)) OR empty(trimBoth(ifNull(diagnosis_label, ''))));

INSERT INTO silver.dim_diagnosis
SELECT
    trimBoth(code_cim10),
    argMax(trimBoth(ifNull(diagnosis_label, '')), source_row_number),
    max(source_date),
    batch_id,
    now64(3, 'UTC')
FROM bronze.cim10
WHERE batch_id = {batch_id:UUID}
  AND NOT empty(trimBoth(code_cim10))
  AND NOT empty(trimBoth(ifNull(diagnosis_label, '')))
GROUP BY code_cim10, batch_id;
