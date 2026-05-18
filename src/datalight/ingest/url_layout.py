from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from urllib.parse import urlparse

from datalight.contracts.constants import URL_FINGERPRINT_HEX_LEN

def sanitize_host_for_fs(netloc: str) -> str:
    """
    Map `urlparse` netloc to a single path segment: host + port, ':' → '_' for host:port.
    Bracketed IPv6 with optional :port is handled without mangling the inner address beyond ':' → '_'.
    """
    s = netloc
    if s.startswith("["):
        m = re.match(r"^(\[[^\]]+\]):(\d+)$", s, re.IGNORECASE)
        if m:
            inner = m.group(1).lower()
            # [::1] -> bracket form; replace : inside for FS safety
            return inner.replace(":", "_") + "_" + m.group(2)
        return s.lower().replace(":", "_")
    if ":" in s and s.count(":") == 1 and not s.startswith("["):
        host, port = s.rsplit(":", 1)
        if port.isdigit():
            return f"{host.lower()}_{port}"
    return s.lower().replace(":", "_")

def build_url_storage_paths(url: str) -> tuple[PurePosixPath, str, str]:
    """Return (path under output_dir, raw netloc for manifest, 16-hex url fingerprint)."""
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        raise ValueError("URL must be absolute with a netloc")
    host_raw = p.netloc
    host_fs = sanitize_host_for_fs(host_raw)
    fp = hashlib.sha256(url.encode("utf-8")).hexdigest()[:URL_FINGERPRINT_HEX_LEN]
    rel = PurePosixPath("urls") / host_fs / fp
    return rel, host_raw, fp
