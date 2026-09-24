-- Repair of the 2026-09-23 incident (docs/07 §4.3, ADR-033 amendment 2).
--
-- T2's backfills and corrections stored 23 September's XLSX under 22 September. OTE has no
-- IM_15MIN_22_09_2026_EN.xlsx (404), so no capture can supersede the wrong versions: they stay
-- current for T2's own metrics until removed. Silver is derived — Bronze keeps the blobs under
-- Object Lock and the fetch log keeps every attempt — so deleting these Silver versions loses no
-- evidence. T1 (the system of record for price_vwap and volume_total) is not touched.
--
-- Run by the author only (a production database mutation, Level 3), from the checkout, with
-- the admin kubeconfig:
--
--   kubectl -n energy-platform exec -i statefulset/energy-platform-postgres -- \
--     sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
--     < deployment/own-cluster/repairs/2026-09-22-t2-wrong-day.sql
--
-- The transaction aborts unless the row set is exactly the 672 rows counted on 2026-09-23; a
-- different count means the situation changed and docs/07 §4.3 must be re-read first.
--
-- Do NOT `energyctl replay` the 22 September runs of ote_intraday_market_xlsx afterwards: a
-- replay re-processes each run's recorded capture, and those captures are the wrong blob.

BEGIN;

CREATE TEMP TABLE wrong_22 ON COMMIT DROP AS
  SELECT id
    FROM observations
   WHERE dataset_id = 'ote.idm_continuous'
     AND source_transport = 'xlsx'
     AND local_date = DATE '2026-09-22'
     AND payload_sha256 IN (SELECT payload_sha256
                              FROM observations
                             WHERE dataset_id = 'ote.idm_continuous'
                               AND source_transport = 'xlsx'
                             GROUP BY 1
                            HAVING count(DISTINCT local_date) > 1);

DO $$
DECLARE
  n integer;
BEGIN
  SELECT count(*) INTO n FROM wrong_22;
  IF n <> 672 THEN
    RAISE EXCEPTION 'expected 672 wrong rows for 2026-09-22, found % — nothing deleted', n;
  END IF;
END
$$;

DELETE FROM observations WHERE id IN (SELECT id FROM wrong_22);

SELECT count(*) AS deleted FROM wrong_22;

SELECT count(*) AS xlsx_rows_left_for_2026_09_22
  FROM observations
 WHERE dataset_id = 'ote.idm_continuous'
   AND source_transport = 'xlsx'
   AND local_date = DATE '2026-09-22';

COMMIT;
