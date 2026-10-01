from __future__ import annotations
import ipaddress
import socket
from urllib.parse import urlparse


class URLValidationError(ValueError):
    pass


class SSRFProtection:
    """Validate outbound URLs and reject local/private/link-local targets."""
    ALLOWED_SCHEMES = frozenset({"https"})

    def __init__(self, resolver=socket.getaddrinfo) -> None:
        self._resolver = resolver

    def validate(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in self.ALLOWED_SCHEMES:
            raise URLValidationError("Only HTTPS URLs are allowed")
        if not parsed.hostname or parsed.username or parsed.password:
            raise URLValidationError("URL must contain a hostname and no embedded credentials")
        if parsed.fragment:
            # Fragments are client-side and do not belong in server fetch targets.
            raise URLValidationError("URL fragments are not allowed")
        try:
            infos = self._resolver(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except (OSError, ValueError) as exc:
            raise URLValidationError("Unable to resolve URL host") from exc
        if not infos:
            raise URLValidationError("URL host did not resolve to an address")
        for info in infos:
            address = info[4][0]
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                raise URLValidationError("URL resolves to a restricted network address")
        return url
