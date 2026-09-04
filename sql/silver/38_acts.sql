INSERT INTO audit.quality_rejects
WITH stay_context AS
(
    SELECT
        stay_id,
        argMax(service_code, tuple(source_date, ingested_at)) AS service_code
    FROM
    (
        SELECT
            trimBoth(stay_id) AS stay_id,
            trimBoth(service_code) AS service_code,
            source_date,
            ingested_at
        FROM bronze.stays
        WHERE NOT empty(trimBoth(stay_id))
    )
    GROUP BY stay_id
)
SELECT
    b.batch_id,
    'bronze.acts',
    b.source_file,
    b.source_row_number,
    concat(b.stay_id, ':', b.code_ccam, ':', ifNull(toString(b.acte_ts), '<null>')),
    multiIf(
        empty(trimBoth(b.stay_id)), 'ACT_STAY_ID_MISSING',
        empty(trimBoth(b.code_ccam)), 'ACT_CCAM_CODE_MISSING',
        b.acte_ts IS NULL, 'ACT_TS_INVALID',
        empty(s.stay_id), 'ACT_UNKNOWN_STAY',
        b.code_ccam NOT IN (SELECT code_ccam FROM silver.dim_ccam FINAL), 'ACT_UNKNOWN_CCAM',
        s.service_code NOT IN (SELECT service_code FROM silver.dim_service FINAL), 'ACT_UNKNOWN_SERVICE',
        'ACT_UNKNOWN_ERROR'
    ),
    'Acte rejeté par une règle de qualité Silver',
    now64(3, 'UTC')
FROM bronze.acts AS b
LEFT JOIN stay_context AS s ON trimBoth(b.stay_id) = s.stay_id
WHERE b.batch_id = {batch_id:UUID}
  AND
  (
      empty(trimBoth(b.stay_id))
      OR empty(trimBoth(b.code_ccam))
      OR b.acte_ts IS NULL
      OR empty(s.stay_id)
      OR b.code_ccam NOT IN (SELECT code_ccam FROM silver.dim_ccam FINAL)
      OR s.service_code NOT IN (SELECT service_code FROM silver.dim_service FINAL)
  );

INSERT INTO silver.fact_acte
WITH stay_context AS
(
    -- Le service est récupéré depuis Bronze puis stocké dans fact_acte.
    -- Gold n'a ainsi jamais besoin de relier fact_acte à fact_stay.
    SELECT
        stay_id,
        argMax(service_code, tuple(source_date, ingested_at)) AS service_code
    FROM
    (
        SELECT
            trimBoth(stay_id) AS stay_id,
            trimBoth(service_code) AS service_code,
            source_date,
            ingested_at
        FROM bronze.stays
        WHERE NOT empty(trimBoth(stay_id))
    )
    GROUP BY stay_id
)
SELECT DISTINCT
    trimBoth(b.stay_id),
    s.service_code,
    trimBoth(b.code_ccam),
    toDate(assumeNotNull(b.acte_ts)),
    assumeNotNull(b.acte_ts),
    b.source_date,
    b.source_file,
    b.source_row_number,
    b.batch_id,
    now64(3, 'UTC')
FROM bronze.acts AS b
INNER JOIN stay_context AS s ON trimBoth(b.stay_id) = s.stay_id
WHERE b.batch_id = {batch_id:UUID}
  AND NOT empty(trimBoth(b.stay_id))
  AND NOT empty(trimBoth(b.code_ccam))
  AND b.acte_ts IS NOT NULL
  AND b.code_ccam IN (SELECT code_ccam FROM silver.dim_ccam FINAL)
  AND s.service_code IN (SELECT service_code FROM silver.dim_service FINAL);

INSERT INTO silver.dim_date
SELECT DISTINCT
    act_date_key,
    toDayOfMonth(act_date_key),
    toISOWeek(act_date_key),
    toMonth(act_date_key),
    toYear(act_date_key),
    {batch_id:UUID},
    now64(3, 'UTC')
FROM silver.fact_acte
WHERE batch_id = {batch_id:UUID};
