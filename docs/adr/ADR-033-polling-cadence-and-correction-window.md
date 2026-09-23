# ADR-033 — Polling cadence, politeness and the correction window (D-5)

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-20 |
| Resolves | D-5 (`02-architecture-decisions.md` §4.2), implementing its recorded default; closes the `04-contracts.md` §5 "delivery-day offset" question |
| Supersedes | — |
| Amended | 2026-09-23, amendment 1 (below): §4 gains `month_start[k]` / `month_end[k]`; every template field is checked (bare names only) |

## Context

`01-data-scope.md` §5 fixes per-target poll intervals (T1/T2: every 15 minutes during the
delivery day and hourly for D-1..D-3; T3: every 15 minutes; E1: hourly from 12:00 CET on D-1) and
a correction window (3 days for T1/T2, 1 day for T3/E1, all marked assumption). `02` §4.2 D-5
records the default: per-target intervals, jitter, capped backoff, conditional requests, and a
one-week observation campaign before any latency figure is quoted. A-12 (V-9) showed the network
does not rate-limit, so politeness is the platform's to enforce.

Phase 2 built the request side: `energy_platform.fetch.RetryPolicy` (4 attempts, capped
exponential backoff 0.5 s → 8 s with ±25 % jitter, on connection errors and 5xx only),
`Conditional` (`If-None-Match` / `If-Modified-Since`, a 304 is a stale fetch and never new data),
`RateLimiter` (token bucket for REST modalities), and `history.max_age` for the backfill bound
(ADR-024 §5, ADR-031). What is missing is the **correction re-poll**: "hourly for D-1..D-3" cannot
be expressed today because every run is for its own delivery day
(`runtime.context.delivery_day_for(scheduled_for)`) and Bronze is idempotent per
`(target_id, scheduled_for)`.

## Decision

1. **Cadence values** are 01 §5's, written in the manifest as `cadence.cron` in `cadence.timezone`
   (unchanged). T1, T2, T3: `*/15 * * * *`; E1: `0 12-23 * * *` (hourly from 12:00 on D-1, the
   delivery day being `scheduled_for + 1 day`, see 3).
2. **Politeness** is the fetch layer as built and is not configurable per target: bounded retries
   with jittered, capped backoff on connection errors and 5xx only (never on 4xx, never on a
   parse failure); conditional requests whenever the previous capture carried an `ETag` or
   `Last-Modified`; at most one in-flight request per target (one CronJob pod, `concurrencyPolicy:
   Forbid`, Phase 5); a REST `rate_limit` where the manifest declares one. Start-time jitter for
   the CronJob (±10 % of the interval, D-5) is a chart value, not a manifest field.
3. **Correction window.** The manifest gains an optional block

   ```yaml
   cadence:
     cron: "*/15 * * * *"
     timezone: Europe/Prague
     correction:
       cron: "7 * * * *"      # the re-poll schedule
       days: 3                # delivery days D-1 … D-3 are re-captured on each firing
   ```

   Semantics: a correction firing **re-captures the last run of each of the previous `days`
   delivery days** with `force=True`, appending a new attempt to that run. Bronze marks the
   attempt `content_changed`; only a changed payload reaches `process` (a stale fetch is a
   successful poll, 01 §5). The run identity stays `(target_id, scheduled_for)`; no new identity
   axis, no manifest "delivery-day offset" field, no change to `delivery_day_for`.
   A target without `correction` has no re-poll; `history.max_age` still bounds backfill.
4. **Delivery day of a run** stays the source's civil date of `scheduled_for`; no manifest
   offset field is introduced. A source that publishes day D's results on D-1 (E1, the day-ahead
   auction) asks for D through a third render name, `next_delivery_day` (the run's delivery day
   plus one calendar day in the source timezone), e.g. `start_date: "{next_delivery_day:%Y-%m-%d}"`.
   The run is still the D-1 run; the observations carry the document's own `Date`, so Silver,
   completeness and goldens see D. Only `delivery_day`, `next_delivery_day` and `scheduled_for`
   exist as placeholders; anything else stays a `RenderError`.
5. **No latency figure is quoted** before the one-week campaign; the campaign procedure is in
   `docs/06-source-verification.md` §6 and uses only `energyctl capture --live` and the capture
   log's `content_changed` transitions.

## Rationale

Re-capturing a past run with `force` reuses three things that already exist and are tested:
Bronze's forced attempt, `content_changed`, and the fenced `process` of a changed capture. It
keeps "which delivery day is this document for" derivable from the run alone (ADR-024 §1: a
capture never has to store it), so replay, gap detection and goldens are untouched. A new
identity axis would have changed the ledger schema, the Bronze key layout (ADR-002) and the
golden runner for a feature whose only purpose is to notice late corrections.

## Rejected

- A manifest `delivery_day_offset` (a per-target offset changes the meaning of every run of the
  target; the correction case needs several offsets at once).
- Run identity `(target_id, scheduled_for, delivery_day)` (ledger migration, Bronze key change,
  every consumer; disproportionate).
- Making the correction poll a second target (`ote_intraday_market_d1`): duplicated contract,
  two Silver writers for one observation identity.
- Configurable retry counts per target (a target author could weaken politeness; C-07).

## Consequences

- Phase 4: `Cadence.correction` in `energy_platform/contracts/manifest.py`, schema export,
  `04` §3.2 row; `next_delivery_day` in `energy_platform/fetch/render.py` (`04` §3.3); the four
  committed manifests declare their cadence per 01 §5. No runtime verb yet.
- Phase 5: `energyctl recapture --days N` (the runtime form of 3), a second CronJob per target
  rendered from `cadence.correction`, `concurrencyPolicy: Forbid`, start jitter as a value.
  The process verb must treat a forced attempt with `content_changed = true` as pending;
  verified by a crash-matrix row then.
- Known weakness: until Phase 5 the committed targets capture only their own day, so a
  correction published on D+1 is picked up only by a manual `energyctl capture --force`. Recorded
  in `docs/06` per target.

## Amendment 1 (2026-09-23) — month-offset placeholders, strict template fields

**Context.** OTE's imbalance settlement exists in three versions per delivery day: 0 (daily),
1 (monthly), 2 (final). Bounded reads on 2026-09-23 (`docs/06` §9.1) found version 1 already
published for 2026-08-31 (at most 23 days after the month ended) and version 2 published for
May 2026 but not for June (roughly 3–4 months after the month ended). Neither version can be
expressed today: §3's correction window is at most 31 days, and §4 allows only `delivery_day`,
`next_delivery_day` and `scheduled_for`, so no request can name an earlier month (`docs/09` F-4).

**Decision.**

1. §4 gains two indexed render names: **`month_start[k]`** and **`month_end[k]`**, the first
   and last civil day of the calendar month *k* months before the delivery day's month
   (0 ≤ *k* ≤ 12; the delivery day is still the source-timezone date of `scheduled_for`). A
   settlement target asks for "the previous month" with
   `start_date: "{month_start[1]:%Y-%m-%d}"`, `end_date: "{month_end[1]:%Y-%m-%d}"` on a
   monthly cron (the 1st), and keeps re-polling that one run for up to 31 days with §3's
   correction window. A day without a run is skipped by the correction, so this costs one
   request per day. The run identity, the ledger and Bronze are untouched. The observations
   carry each item's own `Date`, exactly as for `next_delivery_day`.
2. **Every template field is checked, statically and at render time**
   (`energy_platform/contracts/templates.py`, used by manifest validation and by
   `energy_platform/fetch/render.py`). A field must be a bare allowed name, or `month_start[k]` /
   `month_end[k]` with a literal *k* in 0…12. Attribute access, any other index, conversions
   (`!r`) and nested placeholders inside a format spec are refused, and a SOAP body may name only
   its own `params`. The reason is that `str.format` walks attributes and items. From a
   Python-level context object, `{month_start.__getitem__.__globals__[calendar].sys.modules[os].environ[…]}`
   renders a process environment variable (demonstrated while this amendment was written),
   which would send a platform credential to a registered host. The check closes that path for
   the older names as well. `05` C-62.

**Rejected.** A general date-arithmetic language in templates (a small interpreter to review
and gate for one use); a per-target delivery-day offset (rejected above, for the same reasons);
raising the correction window to about 130 days (130 requests per firing, and version 1 would
still not be a month document).

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-9 · CONFIRMED (egress reachable, no network rate limit;
politeness stays platform-enforced).
