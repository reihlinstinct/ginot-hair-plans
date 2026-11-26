"""CSP meta tag on generated pages: every inline script must be allowed by hash."""

import glob
import re

import pytest

from ginot import csp

DOCS = "docs"


def test_hash_matches_known_digest():
    html = "<html><head><script>alert(1)</script></head></html>"
    # sha256("alert(1)") in base64
    assert csp.script_hashes(html) == [
        "'sha256-bhHHL3z2vDgxUt0W3dWQOrprscmda2Y5pLsLg4GF+pI='"
    ]


def test_json_ld_and_external_scripts_are_not_hashed():
    html = (
        '<script type="application/ld+json">{"a":1}</script>'
        "<script src='x.js'></script><script type='module' src='y.js'></script>"
    )
    assert csp.script_hashes(html) == []


def test_add_csp_is_idempotent_and_skips_fragments():
    doc = '<!DOCTYPE html><html><head><meta charset="utf-8"><script>1</script></head></html>'
    once = csp.add_csp(doc)
    assert once.count("Content-Security-Policy") == 1
    assert once.index("Content-Security-Policy") < once.index("<script>")
    assert csp.add_csp(once) == once
    fragment = "<tr><td>row</td></tr><script>1</script>"
    assert csp.add_csp(fragment) == fragment


def test_policy_has_no_script_unsafe_inline_or_wildcards():
    p = csp.policy("<script>1</script>")
    script_src = next(d for d in p.split("; ") if d.startswith("script-src"))
    assert "unsafe-inline" not in script_src and "*" not in p
    assert "default-src 'none'" in p and "base-uri 'none'" in p


def _documents():
    for path in glob.glob(f"{DOCS}/*.html") + glob.glob(f"{DOCS}/??/*.html"):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if "<head" in text:
            yield path, text


@pytest.mark.parametrize("path,text", list(_documents()))
def test_committed_pages_allow_their_inline_scripts(path, text):
    meta = re.search(r'http-equiv="Content-Security-Policy" content="([^"]*)"', text)
    assert meta, f"{path} has no CSP meta"
    content = meta.group(1).replace("&quot;", '"')
    for token in csp.script_hashes(text):
        assert token in content, f"{path}: inline script not allowed by CSP"
