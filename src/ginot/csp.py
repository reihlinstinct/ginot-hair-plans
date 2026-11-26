"""Content-Security-Policy for the generated site (GitHub Pages cannot send headers).

GitHub Pages serves the site without response headers, so the policy is a
<meta http-equiv="Content-Security-Policy"> tag. The tag is added to each
generated HTML document after rendering: every inline <script> is allowed by
its SHA-256 hash, so no 'unsafe-inline' for scripts and no per-build nonce.

The allow-list is the set of origins the pages actually use:
- scripts: the site itself and the Cloudflare Web Analytics beacon;
- connect: the site's own JSON, the stats API worker, the ArcGIS plan layer
  used by the map, the e-mail endpoint and the Cloudflare beacon;
- images: the site, data: URIs and OpenStreetMap tiles.
Styles keep 'unsafe-inline' because the pages and Leaflet set style attributes.
frame-ancestors, report-uri and sandbox are ignored in a meta tag, so they are
not listed.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re

STATS_API = "https://ginot-hair-api.reihlinstinct.workers.dev"
EMAIL_API = "https://ginot-hair-plans.vercel.app"
ARCGIS = "https://ags.iplan.gov.il"
TILES = "https://tile.openstreetmap.org"
BEACON_SCRIPT = "https://static.cloudflareinsights.com"
BEACON_CONNECT = "https://cloudflareinsights.com"

_INLINE_SCRIPT = re.compile(
    r"<script([^>]*)>(.*?)</script[^>]*>", re.DOTALL | re.IGNORECASE
)
_HAS_CSP = re.compile(r"http-equiv=[\"']?Content-Security-Policy", re.IGNORECASE)
_CHARSET = re.compile(r"<meta\s+charset=[^>]*>", re.IGNORECASE)
_HEAD = re.compile(r"<head[^>]*>", re.IGNORECASE)


def script_hashes(html: str) -> list[str]:
    """CSP source tokens for every executable inline script, in page order."""
    out: list[str] = []
    for attrs, body in _INLINE_SCRIPT.findall(html):
        if re.search(r"\bsrc\s*=", attrs, re.IGNORECASE):
            continue
        type_match = re.search(r"\btype\s*=\s*[\"']?([^\"'\s>]+)", attrs, re.IGNORECASE)
        if type_match and type_match.group(1).lower() not in (
            "module",
            "text/javascript",
            "application/javascript",
        ):
            continue  # JSON-LD and other data blocks never execute
        digest = hashlib.sha256(body.encode("utf-8")).digest()
        token = "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"
        if token not in out:
            out.append(token)
    return out


def policy(html: str) -> str:
    scripts = " ".join(["'self'", BEACON_SCRIPT, *script_hashes(html)])
    return "; ".join(
        [
            "default-src 'none'",
            f"script-src {scripts}",
            "style-src 'self' 'unsafe-inline'",
            f"img-src 'self' data: {TILES}",
            f"connect-src 'self' {STATS_API} {ARCGIS} {EMAIL_API} {BEACON_CONNECT}",
            "base-uri 'none'",
            "form-action 'self'",
        ]
    )


def add_csp(html: str) -> str:
    """Return html with the CSP meta tag; idempotent, skips fragments."""
    if _HAS_CSP.search(html) or not _HEAD.search(html):
        return html
    tag = (
        '<meta http-equiv="Content-Security-Policy" content="'
        + policy(html).replace('"', "&quot;")
        + '">'
    )
    charset = _CHARSET.search(html)
    if charset:
        return html[: charset.end()] + "\n" + tag + html[charset.end() :]
    head = _HEAD.search(html)
    end = head.end() if head else 0
    return html[:end] + "\n" + tag + html[end:]


def apply_to_site(out_dir: str) -> int:
    """Add the CSP to the generated pages under out_dir; return the count."""
    n = 0
    for sub in ("", "reviews"):
        base = os.path.join(out_dir, sub)
        if not os.path.isdir(base):
            continue
        names = [d for d in os.listdir(base) if d.endswith(".html")]
        if sub == "reviews":
            names = [d for d in names if d.startswith("talking_points_")]
        dirs = [base]
        if sub == "":
            dirs += [
                os.path.join(base, d)
                for d in os.listdir(base)
                if os.path.isdir(os.path.join(base, d)) and len(d) == 2
            ]
        for d in dirs:
            for name in names if d == base else os.listdir(d):
                if not name.endswith(".html"):
                    continue
                path = os.path.join(d, name)
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                new = add_csp(text)
                if new != text:
                    with open(path, "w", encoding="utf-8", newline="") as fh:
                        fh.write(new)
                    n += 1
    return n
