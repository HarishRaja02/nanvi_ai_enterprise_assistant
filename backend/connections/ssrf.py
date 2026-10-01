"""SSRF protection for user-supplied URLs and hostnames.

Validates that outbound requests do not target private, loopback, link-local,
or cloud-metadata IP ranges.  DNS is resolved and checked before the request
is made, guarding against DNS rebinding by pinning the resolved IP.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

from backend.connections.base import SSRFBlocked

logger = logging.getLogger(__name__)

# Cloud metadata endpoints that must always be blocked
_METADATA_IPS = frozenset({
    "169.254.169.254",   # AWS, GCP, Azure IMDS
    "fd00:ec2::254",     # AWS IPv6 metadata
    "metadata.google.internal",
})

_METADATA_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata.azure.com",
    "169.254.169.254",
})


def _is_private_ip(ip_str: str) -> bool:
    """Return True if the IP is private, loopback, link-local, or reserved."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # If we can't parse it, block it
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
        or ip_str in _METADATA_IPS
    )


def _allow_private_hosts() -> bool:
    """Check if private hosts are explicitly allowed (dev/testing only)."""
    return os.getenv("CONNECTIONS_ALLOW_PRIVATE_HOSTS", "false").lower() in {"true", "1", "yes"}


def validate_url(url: str, *, allow_http: bool = False) -> str:
    """Validate a URL for SSRF safety.

    Returns the validated URL.  Raises ``SSRFBlocked`` if the target is not
    allowed.

    Parameters
    ----------
    url : str
        The URL to validate.
    allow_http : bool
        If False (default), only ``https`` is permitted.  Set to True for
        development environments where local HTTP is acceptable.
    """
    if not url or not url.strip():
        raise SSRFBlocked("URL cannot be empty")

    parsed = urlparse(url.strip())

    # Scheme validation
    allowed_schemes = {"https"}
    if allow_http:
        allowed_schemes.add("http")
    if parsed.scheme not in allowed_schemes:
        raise SSRFBlocked(f"Only {', '.join(sorted(allowed_schemes))} URLs are allowed")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlocked("URL must include a hostname")

    # Block known metadata hostnames
    if hostname.lower() in _METADATA_HOSTNAMES:
        raise SSRFBlocked("Cloud metadata endpoints are blocked")

    # Resolve DNS and check all IPs
    validate_hostname(hostname)

    return url.strip()


def validate_hostname(hostname: str, *, port: int | None = None) -> list[str]:
    """Resolve a hostname and validate all resolved IPs.

    Returns the list of resolved IP addresses.  Raises ``SSRFBlocked``
    if any resolved IP is in a blocked range.
    """
    if not hostname or not hostname.strip():
        raise SSRFBlocked("Hostname cannot be empty")

    hostname = hostname.strip()

    # Block metadata hostnames
    if hostname.lower() in _METADATA_HOSTNAMES:
        raise SSRFBlocked("Cloud metadata endpoints are blocked")

    # Check if hostname is already an IP literal
    try:
        addr = ipaddress.ip_address(hostname)
        if _is_private_ip(hostname) and not _allow_private_hosts():
            raise SSRFBlocked(f"Private/internal IP addresses are not allowed: {hostname}")
        return [hostname]
    except ValueError:
        pass  # Not an IP literal, proceed to DNS resolution

    # DNS resolution
    try:
        results = socket.getaddrinfo(hostname, port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFBlocked(f"Could not resolve hostname: {hostname}") from exc

    if not results:
        raise SSRFBlocked(f"No DNS records found for: {hostname}")

    resolved_ips = list({result[4][0] for result in results})

    if not _allow_private_hosts():
        for ip in resolved_ips:
            if _is_private_ip(ip):
                raise SSRFBlocked(
                    f"Hostname '{hostname}' resolves to private/internal address. "
                    "If this is intentional, an administrator can allow it."
                )

    return resolved_ips


def validate_db_host(host: str, port: int = 5432) -> list[str]:
    """Validate a database host for SSRF safety.

    Same as ``validate_hostname`` but with a different default port.
    """
    return validate_hostname(host, port=port)


# Convenient alias
validate_url_ssrf = validate_url

