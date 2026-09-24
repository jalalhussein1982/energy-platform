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
-- The transaction aborts unless the row set is exactly 6 048 rows = 9 versions × 672. The 672
-- of docs/07 §4.3 was the CURRENT VIEW (the newest wrong version); the base table holds all
-- nine wrong versions of 22 September — 23 September's file at nine points of that day, fetched
-- 13:37–18:10 UTC on 2026-09-23, all before the fix (revision 7, 18:15 UTC). Deleting only the
-- current one would promote the next wrong one, so all nine go. Two more guards: every payload
-- must also appear under another day (it is another day's file), and every row must have been
-- fetched before the fix. A different count means the situation changed: re-profile first.
--
-- EXECUTED 2026-09-24 ~01:44 UTC by the maintainer agent with the author's manual approval:
-- DELETE 6048, 0 xlsx rows left for 2026-09-22, COMMIT. Kept as the record; a second run aborts
-- on the guard (0 rows).
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
  n_all integer;
  n_late integer;
BEGIN
  SELECT count(*) INTO n FROM wrong_22;
  IF n <> 6048 THEN
    RAISE EXCEPTION 'expected 6048 wrong rows for 2026-09-22 (9 versions x 672), found % — nothing deleted', n;
  END IF;
  -- every xlsx row of 22 September must be in the set: the day has no file of its own
  SELECT count(*) INTO n_all FROM observations
   WHERE dataset_id = 'ote.idm_continuous' AND source_transport = 'xlsx' AND local_date = DATE '2026-09-22';
  IF n_all <> n THEN
    RAISE EXCEPTION '% xlsx rows under 2026-09-22 but only % share a payload with another day — nothing deleted', n_all, n;
  END IF;
  -- every row must predate the fix (ADR-033 amendment 2, revision 7, 2026-09-23 18:15 UTC)
  SELECT count(*) INTO n_late FROM observations o JOIN wrong_22 w ON w.id = o.id
   WHERE o.fetched_at >= TIMESTAMPTZ '2026-09-23 18:15:00+00';
  IF n_late <> 0 THEN
    RAISE EXCEPTION '% rows were fetched after the fix — re-profile before deleting', n_late;
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
