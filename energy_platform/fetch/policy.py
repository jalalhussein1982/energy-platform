"""Egress policy: layer 2 of ADR-026, applied to every request and every redirect hop.

The checks are pure functions over a URL, a manifest's ``allowed_hosts`` and the platform host
registry, plus the addresses a name resolved to and the peer a connection ended up on. They
never open a socket themselves; the :class:`~energy_platform.fetch.client.Fetcher` calls them.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from energy_platform.contracts.hosts import HostEntry
from energy_platform.contracts.hosts import host as registered_host

# ADR-026 §1 ranges (and their IPv6 counterparts): never a fetch destination.
_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)

METADATA_ADDRESSES = frozenset({"169.254.169.254", "fd00:ec2::254", "100.100.100.200"})


class EgressError(Exception):
    """A request was refused before or after contact. ``code`` is stable for tests and logs."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class Destination:
    scheme: str
    host: str
    port: int
    entry: HostEntry


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def check_url(url: str, allowed_hosts: tuple[str, ...], allow_insecure: bool) -> Destination:
    """ADR-026 §2 bullets 1, 2 and 5 for one URL (a first request or a redirect hop)."""
    parts = urlsplit(url)
    hostname = (parts.hostname or "").lower()
    if not hostname:
        raise EgressError("host_not_allowed", f"{url!r} has no host")
    if _is_ip_literal(hostname):
        raise EgressError("ip_literal", f"{url!r}: IP literals are never a destination")
    if parts.scheme not in {"https", "http"}:
        raise EgressError("insecure_scheme", f"{url!r}: scheme must be https")
    if hostname not in allowed_hosts:
        raise EgressError(
            "host_not_allowed", f"{hostname!r} is not in the manifest allowed_hosts {allowed_hosts}"
        )
    entry = registered_host(hostname)
    if entry is None:
        raise EgressError(
            "host_not_registered",
            f"{hostname!r} is not in the platform host registry (ADR-022 Route B)",
        )
    if parts.scheme == "http":
        if not allow_insecure:
            raise EgressError(
                "insecure_scheme", f"{url!r}: http needs allow_insecure on the manifest"
            )
        if not entry.allow_insecure:
            raise EgressError(
                "insecure_host_not_registered",
                f"{hostname!r}: the host registry does not allow http (ADR-026 §2)",
            )
    port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
    if port not in entry.ports:
        raise EgressError(
            "port_not_allowed", f"{hostname!r}: port {port} is not in the registry {entry.ports}"
        )
    return Destination(parts.scheme, hostname, port, entry)


def check_addresses(host: str, addresses: tuple[str, ...]) -> tuple[str, ...]:
    """Reject a name that resolves to any private, loopback, link-local, CGNAT or metadata range."""
    if not addresses:
        raise EgressError("unresolvable", f"{host!r} did not resolve")
    for text in addresses:
        try:
            addr = ipaddress.ip_address(text)
        except ValueError as exc:
            raise EgressError("unresolvable", f"{host!r} resolved to {text!r}") from exc
        candidate = addr.ipv4_mapped if isinstance(addr, ipaddress.IPv6Address) else None
        for a in (addr, candidate):
            if a is None:
                continue
            if str(a) in METADATA_ADDRESSES or any(a in net for net in _BLOCKED_NETWORKS):
                raise EgressError(
                    "private_address", f"{host!r} resolved to {text}, a non-public address"
                )
    return addresses


def check_peer(host: str, peer: str | None, resolved: tuple[str, ...]) -> None:
    """The connected peer must be one of the addresses this layer resolved (ADR-026 §2)."""
    if peer is None:
        raise EgressError("peer_unknown", f"{host!r}: the transport reported no peer address")
    try:
        peer_addr = ipaddress.ip_address(peer)
    except ValueError as exc:
        raise EgressError("peer_mismatch", f"{host!r}: unparseable peer {peer!r}") from exc
    for text in resolved:
        if ipaddress.ip_address(text) == peer_addr:
            return
    raise EgressError("peer_mismatch", f"{host!r}: connected to {peer}, resolved {resolved}")


def check_proxy_environment(environ: dict[str, str] | None = None) -> tuple[str, ...]:
    """Proxy variables are honoured (A-7); a proxy on a metadata address is refused at start-up."""
    env = os.environ if environ is None else environ
    found: list[str] = []
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        value = env.get(key)
        if not value:
            continue
        proxy_host = (urlsplit(value).hostname or "").lower()
        if proxy_host in METADATA_ADDRESSES:
            raise EgressError("private_address", f"{key} points at a metadata address")
        found.append(value)
    return tuple(found)
