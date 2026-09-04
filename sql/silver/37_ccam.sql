INSERT INTO audit.quality_rejects
SELECT
    batch_id,
    'bronze.ccam',
    source_file,
    source_row_number,
    code_ccam,
    multiIf(
        empty(trimBoth(code_ccam)), 'CCAM_CODE_MISSING',
        empty(trimBoth(ifNull(libelle, ''))), 'CCAM_LABEL_MISSING',
        tarif_euros IS NULL OR tarif_euros < 0, 'CCAM_TARIFF_INVALID',
        code_ccam IN
        (
            SELECT code_ccam
            FROM bronze.ccam
            WHERE batch_id = {batch_id:UUID}
            GROUP BY code_ccam
            HAVING count() > 1
        ), 'CCAM_DUPLICATE_CODE',
        'CCAM_UNKNOWN_ERROR'
    ),
    'Code CCAM rejeté par une règle de qualité Silver',
    now64(3, 'UTC')
FROM bronze.ccam
WHERE batch_id = {batch_id:UUID}
  AND
  (
      empty(trimBoth(code_ccam))
      OR empty(trimBoth(ifNull(libelle, '')))
      OR tarif_euros IS NULL OR tarif_euros < 0
      OR code_ccam IN
      (
          SELECT code_ccam
          FROM bronze.ccam
          WHERE batch_id = {batch_id:UUID}
          GROUP BY code_ccam
          HAVING count() > 1
      )
  );

INSERT INTO silver.dim_ccam
SELECT
    trimBoth(code_ccam),
    argMax(trimBoth(ifNull(libelle, '')), source_row_number),
    CAST(argMax(assumeNotNull(tarif_euros), source_row_number), 'Decimal(10, 2)'),
    max(source_date),
    batch_id,
    now64(3, 'UTC')
FROM bronze.ccam
WHERE batch_id = {batch_id:UUID}
  AND NOT empty(trimBoth(code_ccam))
  AND NOT empty(trimBoth(ifNull(libelle, '')))
  AND tarif_euros IS NOT NULL
  AND tarif_euros >= 0
  AND code_ccam NOT IN
  (
      SELECT code_ccam
      FROM bronze.ccam
      WHERE batch_id = {batch_id:UUID}
      GROUP BY code_ccam
      HAVING count() > 1
  )
GROUP BY code_ccam, batch_id;
