from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_site_security_txt_matches_worker_copy_and_policy():
    site = (ROOT / "docs/.well-known/security.txt").read_text(encoding="utf-8")
    worker = (ROOT / "worker/securitytxt.mjs").read_text(encoding="utf-8")
    for line in site.strip().splitlines():
        assert line in worker, line
    assert "Contact: https://github.com/reihlinstinct/ginot-hair-plans/security/advisories/new" in site
    assert "@" not in site
    assert "security/advisories/new" in (ROOT / "SECURITY.md").read_text(encoding="utf-8")
