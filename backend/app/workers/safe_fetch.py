import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx


BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "instance-data",
    "169.254.169.254",
    "100.100.100.200",
    "fd00:ec2::254",
}

BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),      # Carrier-grade NAT / Alibaba IMDS
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("169.254.0.0/16"),    # AWS / Cloud Link-Local IMDS
    ipaddress.ip_network("172.16.0.0/12"),     # Private RFC1918
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),    # Private RFC1918
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 Unique Local (includes fd00:ec2::254)
    ipaddress.ip_network("fe80::/10"),         # IPv6 Link-Local
]


class SSRFProtectionError(ValueError):
    """Raised when a target URI violates AWS Agentic Value Accelerator v5.0 safe_fetch rules."""


@dataclass
class SafeFetchResult:
    final_url: str
    status_code: int
    raw_bytes: bytes
    normalized_text: str
    sha256_hash: str
    etag: Optional[str]
    not_modified: bool = False


def validate_ip_ssrf_safe(ip_str: str) -> None:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError as exc:
        raise SSRFProtectionError(f"Invalid IP address '{ip_str}'") from exc

    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        raise SSRFProtectionError(
            f"SSRF blocked: IP '{ip_str}' falls within a restricted non-public address range."
        )

    for net in BLOCKED_NETWORKS:
        if addr in net:
            raise SSRFProtectionError(
                f"SSRF blocked: IP '{ip_str}' matches blocked CIDR network {net}."
            )


def validate_url_ssrf_safe(target_url: str) -> str:
    """Validate URL against AWS Agentic Value Accelerator v5.0 safe_fetch SSRF rules."""
    parsed = urlparse(target_url.strip())
    if parsed.scheme not in ("http", "https"):
        raise SSRFProtectionError(
            f"SSRF blocked: Unsupported URL scheme '{parsed.scheme}'. Only http/https allowed."
        )
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise SSRFProtectionError("SSRF blocked: URL is missing a valid hostname.")

    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".internal") or hostname.endswith(".local"):
        raise SSRFProtectionError(
            f"SSRF blocked: Hostname '{hostname}' is a restricted internal or metadata endpoint."
        )

    # Check if hostname is a literal IP
    try:
        ipaddress.ip_address(hostname)
        validate_ip_ssrf_safe(hostname)
        return target_url.strip()
    except ValueError:
        pass

    # Resolve DNS and verify every resolved IP address
    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise SSRFProtectionError(f"DNS resolution failed for host '{hostname}': {exc}") from exc

    if not addr_info:
        raise SSRFProtectionError(f"No DNS records resolved for host '{hostname}'.")

    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        # Strip IPv6 zone index if present
        if "%" in ip_str:
            ip_str = ip_str.split("%", 1)[0]
        validate_ip_ssrf_safe(ip_str)

    return target_url.strip()


def normalize_and_extract_html_text(raw_html: str) -> str:
    """Strip boilerplate navigation DOM elements and normalize text for deterministic SHA256 hashing."""
    soup = BeautifulSoup(raw_html, "lxml")

    # Strip boilerplate navigation and non-content DOM elements
    for tag in soup.find_all(
        [
            "nav",
            "header",
            "footer",
            "script",
            "style",
            "noscript",
            "aside",
            "svg",
            "iframe",
            "form",
            "button",
        ]
    ):
        tag.decompose()

    # Remove common cookie/banner/navigation role containers
    for attr_selector in (
        {"role": re.compile(r"^(navigation|banner|contentinfo|complementary|search)$", re.I)},
        {"class": re.compile(r"(cookie-banner|nav-bar|navbar|site-header|site-footer|sidebar|breadcrumbs)", re.I)},
        {"id": re.compile(r"(cookie-banner|navbar|header|footer|sidebar)", re.I)},
    ):
        for el in soup.find_all(attrs=attr_selector):
            el.decompose()

    extracted = soup.get_text(separator="\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in extracted.splitlines()]
    non_empty_lines = [line for line in lines if line]
    return "\n".join(non_empty_lines)


def compute_normalized_sha256(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def safe_fetch(
    target_url: str,
    *,
    previous_etag: Optional[str] = None,
    timeout_seconds: float = 15.0,
    max_redirects: int = 3,
) -> SafeFetchResult:
    """Fetch public vendor URL with strict SSRF protection, redirect validation, and DOM normalization."""
    current_url = validate_url_ssrf_safe(target_url)
    headers = {
        "User-Agent": "Enterprise-AI-Vendor-Governance-Monitor/2.0 (+FINOS-AI-Governance-v2)",
        "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.9",
    }
    if previous_etag:
        headers["If-None-Match"] = previous_etag

    with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            response = client.get(current_url, headers=headers)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    break
                next_url = urljoin(current_url, location)
                current_url = validate_url_ssrf_safe(next_url)
                continue
            break
        else:
            raise SSRFProtectionError(f"Exceeded maximum safe redirect hops ({max_redirects}).")

    if response.status_code == 304:
        return SafeFetchResult(
            final_url=current_url,
            status_code=304,
            raw_bytes=b"",
            normalized_text="",
            sha256_hash="",
            etag=response.headers.get("ETag", previous_etag),
            not_modified=True,
        )

    response.raise_for_status()
    raw_bytes = response.content
    content_type = response.headers.get("Content-Type", "").lower()
    raw_text = response.text

    if "html" in content_type or "<html" in raw_text[:500].lower():
        normalized_text = normalize_and_extract_html_text(raw_text)
    else:
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines()]
        normalized_text = "\n".join(line for line in lines if line)

    sha256_hash = compute_normalized_sha256(normalized_text)
    return SafeFetchResult(
        final_url=current_url,
        status_code=response.status_code,
        raw_bytes=raw_bytes,
        normalized_text=normalized_text,
        sha256_hash=sha256_hash,
        etag=response.headers.get("ETag"),
        not_modified=False,
    )
