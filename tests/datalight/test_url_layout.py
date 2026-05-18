import hashlib

from datalight.contracts.constants import URL_FINGERPRINT_HEX_LEN
from datalight.ingest.url_layout import build_url_storage_paths

def test_host_sanitized_port_replaces_colon():
    rel, host, fp = build_url_storage_paths("https://example.com:8443/a/b/c.pdf?x=1")
    assert host == "example.com:8443"
    assert rel.parts[0] == "urls"
    assert rel.parts[1] == "example.com_8443"
    assert len(rel.parts[2]) == URL_FINGERPRINT_HEX_LEN
    assert (rel / "source.md").as_posix().endswith("/source.md")

def test_fingerprint_is_prefix_of_sha256():
    u = "https://x.example.org/p.pdf"
    rel, host, fp = build_url_storage_paths(u)
    want = hashlib.sha256(u.encode("utf-8")).hexdigest()[:16]
    assert rel.parts[2] == want
    assert fp == want
