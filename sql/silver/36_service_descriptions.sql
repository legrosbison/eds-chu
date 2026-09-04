INSERT INTO audit.quality_rejects
SELECT
    batch_id,
    'bronze.service_descriptions',
    source_file,
    source_row_number,
    service_code,
    multiIf(
        empty(trimBoth(service_code)), 'SERVICE_DESCRIPTION_CODE_MISSING',
        empty(trimBoth(ifNull(categorie, ''))), 'SERVICE_DESCRIPTION_CATEGORY_MISSING',
        capacite_lits IS NULL OR capacite_lits <= 0 OR capacite_lits > 65535, 'SERVICE_DESCRIPTION_CAPACITY_INVALID',
        empty(trimBoth(ifNull(pole, ''))), 'SERVICE_DESCRIPTION_POLE_MISSING',
        service_code NOT IN (SELECT service_code FROM silver.dim_service FINAL), 'SERVICE_DESCRIPTION_UNKNOWN_SERVICE',
        service_code IN
        (
            SELECT service_code
            FROM bronze.service_descriptions
            WHERE batch_id = {batch_id:UUID}
            GROUP BY service_code
            HAVING count() > 1
        ), 'SERVICE_DESCRIPTION_DUPLICATE_CODE',
        'SERVICE_DESCRIPTION_UNKNOWN_ERROR'
    ),
    'Description de service rejetée par une règle de qualité Silver',
    now64(3, 'UTC')
FROM bronze.service_descriptions
WHERE batch_id = {batch_id:UUID}
  AND
  (
      empty(trimBoth(service_code))
      OR empty(trimBoth(ifNull(categorie, '')))
      OR capacite_lits IS NULL OR capacite_lits <= 0 OR capacite_lits > 65535
      OR empty(trimBoth(ifNull(pole, '')))
      OR service_code NOT IN (SELECT service_code FROM silver.dim_service FINAL)
      OR service_code IN
      (
          SELECT service_code
          FROM bronze.service_descriptions
          WHERE batch_id = {batch_id:UUID}
          GROUP BY service_code
          HAVING count() > 1
      )
  );

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
WITH service_labels AS
(
    SELECT
        trimBoth(service_code) AS service_code,
        argMax(trimBoth(ifNull(service_label, '')), tuple(source_date, ingested_at)) AS latest_service_label
    FROM bronze.services
    WHERE NOT empty(trimBoth(service_code))
      AND NOT empty(trimBoth(ifNull(service_label, '')))
    GROUP BY service_code
)
SELECT
    trimBoth(b.service_code),
    s.latest_service_label,
    lowerUTF8(trimBoth(assumeNotNull(b.categorie))),
    toUInt16(assumeNotNull(b.capacite_lits)),
    trimBoth(assumeNotNull(b.pole)),
    b.source_date,
    b.batch_id,
    now64(3, 'UTC')
FROM bronze.service_descriptions AS b
INNER JOIN service_labels AS s ON trimBoth(b.service_code) = s.service_code
WHERE b.batch_id = {batch_id:UUID}
  AND NOT empty(trimBoth(b.service_code))
  AND NOT empty(trimBoth(ifNull(b.categorie, '')))
  AND b.capacite_lits IS NOT NULL
  AND b.capacite_lits BETWEEN 1 AND 65535
  AND NOT empty(trimBoth(ifNull(b.pole, '')))
  AND b.service_code NOT IN
  (
      SELECT service_code
      FROM bronze.service_descriptions
      WHERE batch_id = {batch_id:UUID}
      GROUP BY service_code
      HAVING count() > 1
  );
