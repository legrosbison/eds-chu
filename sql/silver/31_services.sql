INSERT INTO audit.quality_rejects
SELECT
    batch_id,
    'bronze.services',
    source_file,
    source_row_number,
    service_code,
    if(empty(trimBoth(service_code)), 'SERVICE_CODE_MISSING', 'SERVICE_LABEL_MISSING'),
    'Référentiel service incomplet',
    now64(3, 'UTC')
FROM bronze.services
WHERE batch_id = {batch_id:UUID}
  AND (empty(trimBoth(service_code)) OR empty(trimBoth(ifNull(service_label, ''))));

INSERT INTO silver.dim_service
(
    service_code,
    service_label,
    categorie,
    capacite_lits,
    pole,
    source_date,
    batch_id,
    processed_at
)
SELECT
    trimBoth(service_code),
    argMax(trimBoth(ifNull(service_label, '')), source_row_number),
    CAST(NULL, 'Nullable(String)'),
    CAST(NULL, 'Nullable(UInt16)'),
    CAST(NULL, 'Nullable(String)'),
    max(source_date),
    batch_id,
    now64(3, 'UTC')
FROM bronze.services
WHERE batch_id = {batch_id:UUID}
  AND NOT empty(trimBoth(service_code))
  AND NOT empty(trimBoth(ifNull(service_label, '')))
GROUP BY service_code, batch_id;
