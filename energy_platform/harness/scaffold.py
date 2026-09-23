"""``energyctl new-target``: exactly the ADR-027 surface, nothing more (03 Phase 3).

The scaffold is deliberately **not** a target: its manifest carries ``REPLACE_ME`` placeholders,
it has no fixture and its golden has no checked values, so ``make lint`` (05 C-13…C-16) and
pytest collection (ADR-020) refuse it until the author records a fixture and checks the values.
With a registered ``dataset_id`` the contract and the mapping skeleton are filled from the
registry — units, fixed dimensions, resolutions — because those are the platform's to decide.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from energy_platform.contracts.manifest import Modality, target_secret_name
from energy_platform.contracts.registry import DatasetContract, dataset

TARGET_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
PLACEHOLDER = "REPLACE_ME"
PLACEHOLDER_HOST = "replace-me.example"


class ScaffoldError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Scaffold:
    target: Path
    files: tuple[Path, ...]
    admission_required: bool


_FETCH_BLOCKS: dict[Modality, str] = {
    "soap-xml": """fetch:
  soap_xml:
    url: https://{host}/REPLACE_ME/service
    soap_action: https://{host}/REPLACE_ME/Action
    soap_version: "1.1"
    body_template: |
      <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
        <soapenv:Body>
          <REPLACE_ME>
            <StartDate>{{start_date}}</StartDate>
            <EndDate>{{end_date}}</EndDate>
          </REPLACE_ME>
        </soapenv:Body>
      </soapenv:Envelope>
    params:
      start_date: "{{delivery_day:%Y-%m-%d}}"
      end_date: "{{delivery_day:%Y-%m-%d}}"
""",
    "dated-file": """fetch:
  dated_file:
    file_format: {file_format}
    discovery:                      # optional (ADR-005): read the link from a page, then download
      url: https://{host}/REPLACE_ME/page
      link_regex: 'REPLACE_ME_\\d{{4}}\\.{file_format}'
    url_template: "https://{host}/REPLACE_ME/{{delivery_day:%Y-%m-%d}}.{file_format}"
""",
    "html-table": """fetch:
  html_table:
    url: https://{host}/REPLACE_ME/page
    table_selector: "table.REPLACE_ME"
""",
    "rest-json": """fetch:
  rest_json:
    url_template: "https://{host}/REPLACE_ME/api"
    query:
      date: "{{delivery_day:%Y-%m-%d}}"
    headers: {{}}
    # auth: {{secretRef: {{name: {secret_name}, key: REPLACE_ME}}, location: query, param: token}}
""",
    "rest-xml": """fetch:
  rest_xml:
    url_template: "https://{host}/REPLACE_ME/api"
    query:
      date: "{{delivery_day:%Y-%m-%d}}"
    headers: {{}}
""",
}

_CONTRACT_DEFAULTS: dict[Modality, tuple[str, str]] = {
    "soap-xml": ("soap", "soap"),
    "dated-file": ("xlsx", "xlsx"),
    "html-table": ("html", "html-table"),
    "rest-json": ("rest", "json"),
    "rest-xml": ("rest", "xml"),
}


def _mapping_block(contract: DatasetContract | None, metrics: tuple[str, ...]) -> str:
    dims: list[str] = []
    if contract is not None:
        for d in contract.manifest_dimensions():
            fixed = contract.fixed_dimensions.get(d)
            allowed = contract.allowed_dimension_values.get(d)
            value = (
                fixed
                if fixed is not None
                else (f"{PLACEHOLDER}   # one of {list(allowed)}" if allowed else PLACEHOLDER)
            )
            dims.append(f"    {d}: {value}")
    if not dims:
        dims.append(f"    {PLACEHOLDER}: {PLACEHOLDER}   # identity dimensions of the dataset")
    resolution = (
        f"{{constant: {contract.resolutions[0]}}}"
        if contract is not None and contract.resolutions
        else "{constant: PT15M}         # or {source: <field>} when the document says"
    )
    version = (
        f"{{constant: {PLACEHOLDER}}}   # bound to the `version` identity dimension"
        if contract is not None and contract.version_in_identity
        else "null                        # the source publishes no revision marker"
    )
    lines = [
        "mapping:",
        "  dimensions:",
        *dims,
        "  time:",
        "    kind: period_index          # or `timestamp` with `timestamp` + `interval_label`",
        "    timezone: Europe/Prague",
        f"    date: {{source: {PLACEHOLDER}}}          # or {{context: delivery_day}}",
        f"    index: {{source: {PLACEHOLDER}}}",
        f"    resolution: {resolution}",
        f"  source_version: {version}",
        "  source_published_at: null     # never derived from fetch time (01 §6.1)",
        "  metrics:",
    ]
    for m in metrics:
        spec = contract.metric(m) if contract is not None else None
        unit = spec.unit if spec is not None else PLACEHOLDER
        # the unit is quoted: a dimensionless registry unit is the string "1", which YAML would
        # otherwise read as an integer and the manifest model refuse (Phase 4 finding, E1)
        lines.append(
            f'    {m}: {{source: {PLACEHOLDER}, unit: "{unit}", sign: as_published, '
            "decimal_separator: dot}"
        )
    return "\n".join(lines) + "\n"


def render_manifest(
    target_id: str, modality: Modality, dataset_id: str | None, host: str
) -> tuple[str, bool]:
    """The manifest skeleton and whether the dataset is unregistered (Route B ahead)."""
    contract = dataset(dataset_id) if dataset_id else None
    did = dataset_id or f"{PLACEHOLDER}.dataset"
    transport, decode = _CONTRACT_DEFAULTS[modality]
    metrics = tuple(contract.metrics) if contract is not None else (PLACEHOLDER,)
    fetch = _FETCH_BLOCKS[modality].format(
        host=host, file_format="xlsx", secret_name=target_secret_name(target_id)
    )
    head = f"""# {target_id} — scaffolded by `energyctl new-target`; every REPLACE_ME must go before
# this is a target (05 C-13). Fetch and normalise are declared here, never coded (ADR-005).
schema_version: 1
target_id: {target_id}
description: {PLACEHOLDER}
license: "{PLACEHOLDER}: the terms under which the data is reused (01 §10)"
terms_url: https://{host}/{PLACEHOLDER}/terms
allowed_hosts:
  - {host}
modality: {modality}
cadence:
  cron: "*/15 * * * *"
  timezone: Europe/Prague
history:
  max_age: P1Y                  # how far back the source still serves data (ADR-024 §5)
"""
    contract_block = f"""contract:
  dataset_id: {did}
  source_transport: {transport}
  decode: {decode}
  metrics: [{", ".join(metrics)}]
"""
    return head + fetch + contract_block + _mapping_block(contract, metrics), contract is None


README = """# {target_id}

Scaffolded by `energyctl new-target {target_id} --modality {modality}`. This directory is the
whole contribution (ADR-027): a manifest, optional `parser.py`, Bronze fixtures, goldens, tests.

Steps to make it a target:

1. Fill every `REPLACE_ME` in `manifest.yaml` from the source's documentation and terms page.
   `energyctl validate {target_id}` must say `OK`; `ADMISSION_REQUIRED` means the dataset, a
   metric or a host is not admitted — run `energyctl admission-request {target_id}` and open a PR
   with only that file (ADR-022 Route B). Do not invent a unit or edit a registry.
2. Record a fixture: `energyctl record-fixture {target_id} --name ordinary_day --live` (network is
   opt-in) or `--from-file <payload>` for a synthetic copy of the real shape (01 §10).
3. Write `tests/golden/ordinary_day.yaml`: values you checked by hand against the document, your
   name in `checked_by`. Add the 01 §7/§9 cases (DST days, negative price, NULL, changed header →
   `expect.quarantine`).
4. `energyctl run-target-tests {target_id}`; then `make check`.
5. Open a PR that touches only `targets/{target_id}/` (`energyctl pr-bundle {target_id}`).

What is *not* here: fetch code, unit or timezone conversion, retries, secrets. Those are the
platform's (`energy_platform/`), driven by the manifest.
"""

GOLDEN = """# Expected canonical rows for fixtures/{fixture}/, values checked by a human (ADR-020).
fixture: {fixture}
checked_by: REPLACE_ME            # who checked the values, against what, when
expect:
  # row_count: 192
  rows:
    - delivery_start_utc: 2026-01-01T00:00:00+01:00
      resolution: PT15M
      metric: REPLACE_ME
      value: "REPLACE_ME"          # quoted decimal, or null
  # quality_events: [partition_status]
"""

TEST = '''"""Golden files load and point at existing fixtures; the platform runs the values."""

from pathlib import Path

from energy_platform.contracts.golden import load_golden

HERE = Path(__file__).parent


def test_goldens_reference_existing_fixtures() -> None:
    goldens = sorted((HERE / "golden").glob("*.yaml"))
    assert goldens
    for path in goldens:
        golden = load_golden(path)
        assert (HERE.parent / "fixtures" / golden.fixture).is_dir(), golden.fixture
'''

PARSER = '''"""Custom parser: only when the generic parser cannot read this source's syntax.

It receives the document already decoded (04 §3.8) and emits records in the source's own
vocabulary. Units, timezones, intervals and signs are applied by the platform from the manifest.
"""

from decimal import Decimal

from energy_platform.contracts import SourceRecord, XmlDocument


class Parser:
    def parse(self, doc: XmlDocument) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        for item in doc.root.find_all("REPLACE_ME"):
            value = item.first("REPLACE_ME")
            fields = {"REPLACE_ME": Decimal(value.text) if value and value.text else None}
            records.append(SourceRecord(fields, locator=item.local_name))
        return records
'''


def scaffold_target(
    root: Path,
    target_id: str,
    modality: Modality,
    *,
    dataset_id: str | None = None,
    host: str = PLACEHOLDER_HOST,
    with_parser: bool = False,
) -> Scaffold:
    if not TARGET_ID.match(target_id):
        raise ScaffoldError(f"target id must match {TARGET_ID.pattern}: {target_id!r}")
    if modality not in _FETCH_BLOCKS:
        raise ScaffoldError(f"unknown modality {modality!r}; one of {sorted(_FETCH_BLOCKS)}")
    target = root / target_id
    if target.exists():
        raise ScaffoldError(f"{target} already exists")
    manifest, admission = render_manifest(target_id, modality, dataset_id, host)
    files: dict[Path, str] = {
        target / "__init__.py": "",
        target / "manifest.yaml": manifest,
        target / "README.md": README.format(target_id=target_id, modality=modality),
        target / "tests" / "__init__.py": "",
        target / "tests" / "test_golden.py": TEST,
        target / "tests" / "golden" / "ordinary_day.yaml": GOLDEN.format(fixture="ordinary_day"),
    }
    if with_parser:
        files[target / "parser.py"] = PARSER
    (target / "fixtures").mkdir(parents=True)
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Scaffold(target, tuple(sorted(files)), admission)
