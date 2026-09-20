"""The only outbound HTTP path of the platform (A-7, ADR-026 §2, ADR-027 §3).

Everything a capture needs from the network goes through :class:`Fetcher`: host and scheme
enforcement against the manifest **and** the host registry, name resolution with private-range
rejection, hand-followed redirects, capped jittered backoff, conditional requests and rate
limiting. :mod:`energy_platform.fetch.objectstore` is the object-store client (S3, SigV4) of
the Bronze backend (ADR-032); it lives here so the rule stays literal.
:func:`fetch_for_manifest` turns a manifest's declarative ``fetch`` block into the
request(s) for one run. No other package may import ``httpx`` (ruff TID251).
"""

from energy_platform.fetch.client import (
    Conditional,
    Fetcher,
    FetchFailed,
    FetchRequest,
    FetchResult,
    RateLimiter,
    RetryPolicy,
)
from energy_platform.fetch.objectstore import (
    Credentials,
    ObjectInfo,
    ObjectStore,
    ObjectStoreConfig,
    ObjectStoreError,
    Retention,
    check_endpoint,
    sign_v4,
)
from energy_platform.fetch.offline import FixtureTransport, mock_transport
from energy_platform.fetch.plan import fetch_for_manifest
from energy_platform.fetch.policy import EgressError, check_proxy_environment, check_url
from energy_platform.fetch.render import FetchContext, RenderError, render
from energy_platform.fetch.secrets import EnvSecretResolver, SecretResolver

__all__ = [
    "Conditional",
    "Credentials",
    "EgressError",
    "EnvSecretResolver",
    "FetchContext",
    "FetchFailed",
    "FetchRequest",
    "FetchResult",
    "Fetcher",
    "FixtureTransport",
    "ObjectInfo",
    "ObjectStore",
    "ObjectStoreConfig",
    "ObjectStoreError",
    "RateLimiter",
    "RenderError",
    "Retention",
    "RetryPolicy",
    "SecretResolver",
    "check_endpoint",
    "check_proxy_environment",
    "check_url",
    "fetch_for_manifest",
    "mock_transport",
    "render",
    "sign_v4",
]
