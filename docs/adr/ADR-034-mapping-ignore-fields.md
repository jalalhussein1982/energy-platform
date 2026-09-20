# ADR-034 — `mapping.ignore_fields`: display-only source fields

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-20 |
| Resolves | `04-contracts.md` §5 open question "Display-only columns" (raised 2026-09-20, Phase 2, P2-D6) |
| Supersedes | — |

## Context

`01-data-scope.md` §9 says an unknown column quarantines the document; 01 §3 documents that
T2's `Time interval` column is display only and that the parser keys on `Period`. Phase 2 made
the unknown-field case a warning (`unknown_field`, P2-D6) because the manifest had no way to
name a column it deliberately does not read. Phase 4 builds the committed targets and finds the
same shape three times: T1 carries an optional `Emerg` element, T2 the `Time interval` label,
E1 a `PeriodInterval` label. A warning raised on every successful run of three of four targets
is noise, and noise is how a real unknown column (a changed header, a new unit) gets ignored.

## Decision

1. The `mapping` block gains an optional list:

   ```yaml
   mapping:
     ignore_fields: ["Time interval"]   # present in the document, deliberately not read
   ```

   Names are source-vocabulary field names exactly as the generic parser reports them
   (header text, element local name, `@attribute`).
2. **Validation:** a name in `ignore_fields` that is also referenced by the mapping (a time
   field, `source_version`, `source_published_at`, or a metric `source`) is a manifest error; a
   bare column number is refused like any `source` (05 C-04).
3. **Effect:** the mapping engine subtracts `ignore_fields` from a record's fields before
   computing `unknown_field`. Any other unmapped field still raises the warning; nothing else
   changes — an ignored field never reaches Silver, never affects identity or values.
4. `ignore_fields` is part of `mapping_block()` and therefore of `derivation_id` (ADR-023 §1).
   It changes no output value; the derivation changes because the mapping text changed, which
   is the rule as written.
5. Schema: additive optional field; `schema_version` stays `1`; `schemas/manifest.v1.json` is
   regenerated.

## Rationale

The alternative — leaving the warning on every run — makes `unknown_field` unactionable, and
the stronger alternative — quarantining unknown columns as 01 §9 reads literally — would
quarantine every T2 file ever published. Naming the ignored columns keeps the strict rule for
everything the author did not foresee while documenting, in the manifest, what was foreseen.

## Rejected

- Silently dropping known display columns in the generic parser (platform code would carry
  per-source knowledge; ADR-005 puts source syntax in the manifest).
- A `warn: false` switch on `unknown_field` (turns off the guard instead of scoping it).
- Mapping display columns to a throw-away metric (invents a metric; C-24).

## Consequences

- Phase 4: `MappingBlock.ignore_fields` with its validator; engine change; `04` §3.6; the T1, T2
  and E1 manifests use it; the T2 `extra_column` fixture proves an *unlisted* column still warns.
- `docs/05-constraint-matrix.md` is unchanged: the existing C-24/C-25 rows cover the "hide a
  metric by ignoring it" attempt because `contract.metrics` must still equal the registry set.

## Verification refs

none — design decision.
