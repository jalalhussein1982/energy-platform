"""From a manifest's declarative ``fetch`` block to the request(s) of one run (ADR-005, 04 §3.3).

Per modality:

* ``soap_xml`` — POST the rendered body with the ``SOAPAction`` header (1.1) or the
  ``application/soap+xml`` action parameter (1.2);
* ``dated_file`` — optional discovery step (fetch the page, pick the first ``href`` matching
  ``link_regex``), else the rendered ``url_template``;
* ``html_table`` — GET;
* ``rest_json`` / ``rest_xml`` — GET with rendered query and headers; ``secretRef`` resolved and
  redacted from every stored URL; ``rate_limit`` honoured.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from energy_platform.contracts.intervals import parse_duration
from energy_platform.contracts.manifest import (
    Auth,
    DatedFileFetch,
    Manifest,
    RestJsonFetch,
    RestXmlFetch,
    SoapXmlFetch,
)
from energy_platform.fetch.client import (
    Conditional,
    Fetcher,
    FetchRequest,
    FetchResult,
    RateLimiter,
)
from energy_platform.fetch.render import FetchContext, render, render_with
from energy_platform.fetch.secrets import SecretResolver

_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def soap_request(block: SoapXmlFetch, ctx: FetchContext) -> FetchRequest:
    params = {name: render(expr, ctx) for name, expr in block.params.items()}
    body = render_with(block.body_template, params).encode("utf-8")
    if block.soap_version == "1.1":
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{block.soap_action}"',
        }
    else:
        headers = {
            "Content-Type": f'application/soap+xml; charset=utf-8; action="{block.soap_action}"'
        }
    return FetchRequest(url=block.url, method="POST", headers=headers, body=body)


def discover_link(page: str, base_url: str, link_regex: str) -> str | None:
    """First ``href`` whose value matches ``link_regex``, absolutised against the page URL."""
    pattern = re.compile(link_regex)
    for match in _HREF.finditer(page):
        href = match.group(1)
        if pattern.search(href):
            return str(urljoin(base_url, href))
    return None


def _rest_request(
    block: RestJsonFetch | RestXmlFetch,
    ctx: FetchContext,
    secrets: SecretResolver | None,
    conditional: Conditional | None,
) -> FetchRequest:
    url = render(block.url_template, ctx)
    query = {k: render(v, ctx) for k, v in block.query.items()}
    headers = {k: render(v, ctx) for k, v in block.headers.items()}
    redact: tuple[str, ...] = ()
    if block.auth is not None:
        value = _resolve(block.auth, secrets)
        if block.auth.location == "query":
            query[block.auth.param] = value
            redact = (block.auth.param,)
        else:
            headers[block.auth.param] = value
    if query:
        parts = urlsplit(url)
        existing = parts.query
        merged = f"{existing}&{urlencode(query)}" if existing else urlencode(query)
        url = urlunsplit(parts._replace(query=merged))
    return FetchRequest(url=url, headers=headers, conditional=conditional, redact_params=redact)


def _resolve(auth: Auth, secrets: SecretResolver | None) -> str:
    if secrets is None:
        raise LookupError("this fetch block needs a secretRef but no SecretResolver was given")
    return secrets.resolve(auth.secretRef)


def rate_limiter_for(block: RestJsonFetch | RestXmlFetch) -> RateLimiter | None:
    if block.rate_limit is None:
        return None
    per = parse_duration(block.rate_limit.per).total_seconds()
    return RateLimiter(block.rate_limit.requests, per)


def fetch_for_manifest(
    manifest: Manifest,
    ctx: FetchContext,
    fetcher: Fetcher,
    *,
    previous: Conditional | None = None,
    secrets: SecretResolver | None = None,
) -> FetchResult:
    """Execute the manifest's fetch block for one run and return the payload response."""
    block = manifest.fetch
    if block.soap_xml is not None:
        # SOAP responses are never cacheable by validators; no conditional headers.
        return fetcher.fetch(soap_request(block.soap_xml, ctx))
    if block.dated_file is not None:
        return _fetch_dated_file(block.dated_file, ctx, fetcher, previous)
    if block.html_table is not None:
        return fetcher.fetch(FetchRequest(url=block.html_table.url, conditional=previous))
    if block.rest_json is not None:
        return fetcher.fetch(_rest_request(block.rest_json, ctx, secrets, previous))
    if block.rest_xml is not None:
        return fetcher.fetch(_rest_request(block.rest_xml, ctx, secrets, previous))
    raise ValueError("fetch block has no modality key")  # unreachable: FetchBlock validates


def _fetch_dated_file(
    block: DatedFileFetch,
    ctx: FetchContext,
    fetcher: Fetcher,
    previous: Conditional | None,
) -> FetchResult:
    url: str | None = None
    if block.discovery is not None:
        page = fetcher.fetch(FetchRequest(url=block.discovery.url))
        url = discover_link(
            page.body.decode("utf-8", "replace"), page.url, block.discovery.link_regex
        )
    if url is None:
        url = render(block.url_template, ctx)
    return fetcher.fetch(FetchRequest(url=url, conditional=previous))


def request_headers_for_log(request: FetchRequest) -> Mapping[str, str]:
    """Headers safe to log: authorization-like values redacted."""
    return {
        k: ("<redacted>" if k.lower() in {"authorization", "x-api-key", "securitytoken"} else v)
        for k, v in request.headers.items()
    }
