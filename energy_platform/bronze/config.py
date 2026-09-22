"""Bronze from the environment (Phase 5 plan P5-D4): what a pod gets from the chart's `Secret`.

``ENERGY_PLATFORM_BRONZE`` selects the backend: ``dir`` (default; ``ENERGY_PLATFORM_BRONZE_DIR``,
falling back to ``.bronze``) or ``s3``. The S3 shape is one prefix per store:

``ENERGY_PLATFORM_S3_ENDPOINT``, ``…_S3_BUCKET``, ``…_S3_REGION`` (default ``us-east-1``),
``…_S3_ALLOWED_HOSTS`` (comma list; default = the endpoint host), ``…_S3_ALLOW_INSECURE``
(``true``/``false``), ``…_S3_RETENTION_MODE`` + ``…_S3_RETENTION_DAYS`` (optional, Object Lock
headers on every ``PUT``, ADR-032), credentials by secretRef name ``BRONZE`` (ADR-032:
``BRONZE_ACCESS_KEY_ID``, ``BRONZE_SECRET_ACCESS_KEY``, optional ``BRONZE_SESSION_TOKEN``).
The optional cold store (ADR-021 read path) uses the ``ENERGY_PLATFORM_S3_COLD_`` prefix and
secretRef ``BRONZE_COLD``; the replica the restore drill reads uses ``ENERGY_PLATFORM_S3_REPLICA_``
and ``BRONZE_REPLICA``. Nothing here reads a file; the chart maps its ``Secret`` to exactly these
names.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from energy_platform.bronze.bronze import Bronze
from energy_platform.bronze.capture_log import FileCaptureLog
from energy_platform.bronze.s3 import S3BlobStore, S3CaptureLog
from energy_platform.bronze.store import FileBlobStore
from energy_platform.fetch.objectstore import (
    Credentials,
    ObjectStore,
    ObjectStoreConfig,
    Retention,
    RetentionMode,
)

PREFIX = "ENERGY_PLATFORM_S3"
COLD_PREFIX = "ENERGY_PLATFORM_S3_COLD"
REPLICA_PREFIX = "ENERGY_PLATFORM_S3_REPLICA"
_TRUE = {"1", "true", "yes", "on"}


class BronzeConfigError(ValueError):
    """A required variable is missing or a value is not one of the accepted forms."""


def _flag(environ: Mapping[str, str], name: str) -> bool:
    return environ.get(name, "false").strip().lower() in _TRUE


def object_store_config(
    environ: Mapping[str, str], prefix: str = PREFIX, *, allow_delete: bool = False
) -> ObjectStoreConfig | None:
    """The ``ObjectStoreConfig`` under ``prefix``, or ``None`` when ``<prefix>_ENDPOINT`` is
    unset (an optional store that is simply not configured)."""
    endpoint = environ.get(f"{prefix}_ENDPOINT", "").strip()
    if not endpoint:
        return None
    bucket = environ.get(f"{prefix}_BUCKET", "").strip()
    if not bucket:
        raise BronzeConfigError(f"{prefix}_BUCKET is required with {prefix}_ENDPOINT")
    host = (urlsplit(endpoint).hostname or "").lower()
    hosts_raw = environ.get(f"{prefix}_ALLOWED_HOSTS", "").strip()
    allowed = tuple(h.strip().lower() for h in hosts_raw.split(",") if h.strip()) or (host,)
    retention: Retention | None = None
    mode = environ.get(f"{prefix}_RETENTION_MODE", "").strip().upper()
    days_raw = environ.get(f"{prefix}_RETENTION_DAYS", "").strip()
    if mode or days_raw:
        if mode not in {"COMPLIANCE", "GOVERNANCE"} or not days_raw.isdigit():
            raise BronzeConfigError(
                f"{prefix}_RETENTION_MODE must be COMPLIANCE|GOVERNANCE with "
                f"{prefix}_RETENTION_DAYS a positive integer"
            )
        retention_mode: RetentionMode = "COMPLIANCE" if mode == "COMPLIANCE" else "GOVERNANCE"
        retention = Retention(mode=retention_mode, days=int(days_raw))
    return ObjectStoreConfig(
        endpoint=endpoint,
        bucket=bucket,
        region=environ.get(f"{prefix}_REGION", "us-east-1").strip() or "us-east-1",
        allowed_hosts=allowed,
        allow_insecure=_flag(environ, f"{prefix}_ALLOW_INSECURE"),
        allow_delete=allow_delete,
        retention=retention,
    )


def object_store_from_env(
    environ: Mapping[str, str],
    prefix: str = PREFIX,
    credentials_ref: str = "BRONZE",
    *,
    allow_delete: bool = False,
    **client_kwargs: Any,
) -> ObjectStore:
    """One configured ``ObjectStore``; raises ``BronzeConfigError`` when the endpoint is unset.
    ``client_kwargs`` (``transport``, ``clock``, ``sleep``, ``rng``) are for tests."""
    config = object_store_config(environ, prefix, allow_delete=allow_delete)
    if config is None:
        raise BronzeConfigError(f"{prefix}_ENDPOINT is not set")
    return ObjectStore(
        config, Credentials.from_env(credentials_ref, dict(environ)), **client_kwargs
    )


def bronze_from_env(environ: Mapping[str, str], **client_kwargs: Any) -> Bronze:
    """The Bronze a verb runs against, chosen by ``ENERGY_PLATFORM_BRONZE``."""
    mode = environ.get("ENERGY_PLATFORM_BRONZE", "dir").strip().lower() or "dir"
    if mode == "dir":
        root = Path(environ.get("ENERGY_PLATFORM_BRONZE_DIR", "") or ".bronze")
        return Bronze(FileBlobStore(root), FileCaptureLog(root))
    if mode != "s3":
        raise BronzeConfigError(f"ENERGY_PLATFORM_BRONZE must be dir|s3, not {mode!r}")
    hot = object_store_from_env(environ, PREFIX, "BRONZE", **client_kwargs)
    cold_config = object_store_config(environ, COLD_PREFIX)
    cold: S3BlobStore | None = None
    if cold_config is not None:
        cold = S3BlobStore(
            object_store_from_env(environ, COLD_PREFIX, "BRONZE_COLD", **client_kwargs)
        )
    return Bronze(S3BlobStore(hot), S3CaptureLog(hot), cold=cold)


def replica_bronze_from_env(environ: Mapping[str, str], **client_kwargs: Any) -> Bronze:
    """The independent copy (store B) as a read-only Bronze for the restore drill (ADR-036 §5)."""
    store = object_store_from_env(environ, REPLICA_PREFIX, "BRONZE_REPLICA", **client_kwargs)
    return Bronze(S3BlobStore(store), S3CaptureLog(store))
