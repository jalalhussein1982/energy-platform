"""``energyctl record-fixture``: a Bronze object under ``targets/<id>/fixtures/<name>/``.

Two ways in (P3-D9): ``--live`` runs a real capture through the fetch layer into a scratch Bronze
and copies the blob and its entry; ``--from-file`` wraps a saved payload in an entry offline, for
the synthetic fixtures 01 §10 asks for until redistribution is confirmed. Either way the fixture
is exactly what a capture writes (ADR-020), so ``load_fixture`` verifies it.
"""

from __future__ import annotations

import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from energy_platform.bronze import (
    Bronze,
    CaptureEntry,
    FileBlobStore,
    FileCaptureLog,
    blob_key,
    capture_id,
    sha256_hex,
    write_fixture,
)
from energy_platform.contracts.manifest import Manifest
from energy_platform.fetch import EnvSecretResolver, Fetcher
from energy_platform.runtime import Runtime, capture
from energy_platform.store.unavailable import UnavailableStore

FIXTURE_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")

_DEFAULT_CONTENT_TYPES = {
    "soap": "text/xml; charset=utf-8",
    "xml": "application/xml",
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "html-table": "text/html; charset=utf-8",
}


class FixtureError(ValueError):
    pass


def fixture_dir(target: Path, name: str) -> Path:
    if not FIXTURE_NAME.match(name):
        raise FixtureError(f"fixture name must match {FIXTURE_NAME.pattern}: {name!r}")
    directory = target / "fixtures" / name
    if directory.exists():
        raise FixtureError(f"{directory} already exists; fixtures are immutable, pick a new name")
    return directory


def record_from_file(
    target: Path,
    manifest: Manifest,
    name: str,
    payload_path: Path,
    *,
    scheduled_for: datetime | None = None,
    content_type: str | None = None,
) -> CaptureEntry:
    """Offline: describe a saved payload as if the manifest's first URL had served it."""
    directory = fixture_dir(target, name)
    payload = payload_path.read_bytes()
    when = scheduled_for or datetime.now(UTC)
    sha = sha256_hex(payload)
    entry = CaptureEntry(
        capture_id=capture_id(manifest.target_id, when, 1),
        target_id=manifest.target_id,
        scheduled_for=when,
        attempt=1,
        fetched_at=when,
        source_url=manifest.fetch.urls()[0],
        http_status=200,
        content_type=content_type or _DEFAULT_CONTENT_TYPES[manifest.contract.decode],
        payload_sha256=sha,
        raw_ref=blob_key(sha),
        size=len(payload),
        content_changed=True,
        source_transport=manifest.contract.source_transport,
    )
    write_fixture(directory, entry, payload)
    return entry


def record_live(
    target: Path,
    manifest: Manifest,
    name: str,
    *,
    scheduled_for: datetime | None = None,
    fetcher: Fetcher | None = None,
) -> CaptureEntry:
    """Network, opt-in: one real capture through ``runtime.capture`` into a scratch Bronze."""
    directory = fixture_dir(target, name)
    when = scheduled_for or datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="energy-platform-fixture-") as tmp:
        bronze = Bronze(FileBlobStore(Path(tmp)), FileCaptureLog(Path(tmp)))
        rt = Runtime(
            manifest=manifest,
            bronze=bronze,
            store=UnavailableStore(),
            fetcher_factory=lambda m: (
                fetcher or Fetcher(allowed_hosts=m.allowed_hosts, allow_insecure=m.allow_insecure)
            ),
            secrets=EnvSecretResolver(),
        )
        report = capture(rt, when)
        if report.entry is None or report.outcome != "ok":
            raise FixtureError(f"capture failed: {report.outcome}: {report.error}")
        payload = bronze.read(report.entry.raw_ref).payload
        write_fixture(directory, report.entry, payload)
        return report.entry
