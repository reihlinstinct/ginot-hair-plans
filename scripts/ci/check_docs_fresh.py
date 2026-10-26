#!/usr/bin/env python3
"""Fail when the committed site in docs/ is stale against src/ginot (#539).

#531 merged a src/ginot/page.py change without the regenerated docs/, so the
merge deployed nothing visible. This check re-renders the site with
page.render_site from the committed inputs only (snapshots/latest.json,
out/changes.json, data/permit_requests.json and the other committed data
files render_site reads) into a temp dir and compares the result with docs/.

It is hermetic: no network, no live data. The clock is pinned per file to
the "generated" date stamped in that committed file (index.html, about.html,
the review pages, feed.xml, data.json, open.json); files without a stamp use
the date stamped in docs/index.html. Committed docs may carry two dates (for
example a permit-feed batch or a hand regeneration that kept the old
data.json), so one render per distinct stamp date is made.

Scope (what the gate covers): every text file render_site writes - the HTML
pages and fragments, style.css, the copied static assets, feed.xml and the
JSON it writes, except data.json (see EXCLUDED). CRLF is normalized to LF before comparing, because permit
descriptions carry CR LF that the committed copies do not keep.

Orphans: a committed reviews/talking_points_*.html or vendor/ file that the
render no longer produces is reported stale, and --write deletes it.

Not covered (reported by --list-uncovered): data.json, the PNG previews (og.png,
reviews/og_*.png; they depend on matplotlib and font versions), and the docs/
files other pipelines write (index.json, plan-points.json, parcel-audit.json,
badge/, favicons, design/, reviews/ fact-check pages).

Regenerate the site from the committed inputs (same pinned clock):

    python scripts/ci/check_docs_fresh.py --write

Exit codes: 0 fresh, 1 stale (or a rendered file is missing from docs/),
2 the check itself could not run: a missing or unreadable input, a missing
or invalid date stamp, or any unexpected error while rendering or comparing.
CI fails on any nonzero exit.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

BASE_URL = "https://reihlinstinct.github.io/ginot-hair-plans/"  # refresh.py default
SKIP_SUFFIXES = (".png",)
# render_site writes these, but other pipelines leave them behind on purpose,
# so comparing them would flag every PR. Listed by --list-uncovered.
EXCLUDED = {
    # The permit feed batches refresh permits.html / permit-ids.json /
    # permit-points.json (scripts/render_permits_page.py) but not data.json,
    # whose permits[] is only rewritten by the weekly refresh.
    "data.json": "permits[] is refreshed only by the weekly refresh, not by permit-feed batches",
}
# Paths only render_site writes. A committed file matching one that the render
# no longer produces (a removed plans/*/analysis review, a dropped vendor
# asset) is an orphan: still published, so it counts as stale and --write
# deletes it. Other pipelines' files never match these patterns.
RENDER_OWNED = ("reviews/talking_points_*.html", "vendor/**/*")
_HTML_STAMP = re.compile(r"עודכן: (\d{4}-\d{2}-\d{2})")
_FEED_STAMP = re.compile(r"<updated>(\d{4}-\d{2}-\d{2})T00:00:00Z</updated>")


class CheckError(Exception):
    """The check could not run (as opposed to: the docs are stale)."""


def stamp_date(path: Path) -> str | None:
    """The generated date stamped in a committed file, or None when the file
    carries no stamp. A stamp that is present but not a real date raises
    CheckError: the clock cannot be pinned, so the check cannot run. (A
    committed JSON output that does not parse has no stamp; it then compares
    as stale against the render.)"""
    if not path.is_file():
        return None
    if path.suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(data, dict) or "generated" not in data:
            return None
        value = data["generated"]
    elif path.suffix in (".html", ".xml"):
        text = path.read_text(encoding="utf-8", errors="replace")
        m = (_FEED_STAMP if path.suffix == ".xml" else _HTML_STAMP).search(text)
        if not m:
            return None
        value = m.group(1)
    else:
        return None
    if not (isinstance(value, str) and _iso(value)):
        raise CheckError(f"invalid generated date stamp {value!r} in {path.name}")
    return value


def _iso(value: str) -> bool:
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def render(out_dir: Path, date: str) -> None:
    """render_site over the committed inputs with today_il pinned to date."""
    from ginot import page

    inputs = {
        "snapshot": ROOT / "snapshots" / "latest.json",
        "changes": ROOT / "out" / "changes.json",
        "permits": ROOT / "data" / "permit_requests.json",
    }
    missing = [str(p.relative_to(ROOT)) for p in inputs.values() if not p.is_file()]
    if missing:
        raise CheckError(f"missing committed input(s): {', '.join(missing)}")
    try:
        rows = json.loads(inputs["snapshot"].read_text(encoding="utf-8"))["rows"]
        changes = json.loads(inputs["changes"].read_text(encoding="utf-8"))["changes"]
        json.loads(inputs["permits"].read_text(encoding="utf-8"))["requests"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CheckError(f"unreadable committed input: {type(exc).__name__}: {exc}") from exc
    pinned = datetime.date.fromisoformat(date)
    original = page.today_il
    page.today_il = lambda: pinned
    cwd = os.getcwd()
    try:
        os.chdir(ROOT)  # render_site reads data/ and plans/ relative to cwd
        page.render_site(
            rows,
            changes,
            str(out_dir),
            base_url=BASE_URL,
            permits_path="data/permit_requests.json",
            council_geojson="data/council_ginot_hair.geojson",
        )
    finally:
        os.chdir(cwd)
        page.today_il = original


def _files(tree: Path) -> list[str]:
    return sorted(
        p.relative_to(tree).as_posix()
        for p in tree.rglob("*")
        if p.is_file() and not p.name.endswith(SKIP_SUFFIXES)
        and p.relative_to(tree).as_posix() not in EXCLUDED
    )


def _normalized(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def first_difference(a: bytes, b: bytes) -> int:
    """1-based line number of the first differing line."""
    for n, (x, y) in enumerate(zip(a.split(b"\n"), b.split(b"\n")), start=1):
        if x != y:
            return n
    return min(a.count(b"\n"), b.count(b"\n")) + 1


def check(docs: Path, write: bool = False) -> list[str]:
    """Return problems (empty when docs/ is fresh). With write=True,
    copy the regenerated files over docs/ instead."""
    base_date = stamp_date(docs / "index.html")
    if not base_date:
        raise CheckError(f"no generated date stamp in {docs / 'index.html'}")
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="docs-fresh-") as tmp:
        renders: dict[str, Path] = {}

        def rendered_for(date: str) -> Path:
            if date not in renders:
                out = Path(tmp) / date
                render(out, date)
                renders[date] = out
            return renders[date]

        names = _files(rendered_for(base_date))
        for name in names:
            committed = docs / name
            date = stamp_date(committed) or base_date
            fresh = rendered_for(date) / name
            if not fresh.is_file():
                problems.append(f"{name}: not rendered for stamp date {date}")
                continue
            if write:
                committed.parent.mkdir(parents=True, exist_ok=True)
                committed.write_bytes(_normalized(fresh))  # LF, as committed
                continue
            if not committed.is_file():
                problems.append(f"{name}: rendered but missing from {docs.name}/")
                continue
            a, b = _normalized(committed), _normalized(fresh)
            if a != b:
                problems.append(
                    f"{name}: stale (first difference at line {first_difference(a, b)}, "
                    f"rendered with generated={date})"
                )
        rendered = set(names)
        for name in orphans(docs, rendered):
            if write:
                (docs / name).unlink()
            else:
                problems.append(f"{name}: no longer rendered (orphan; --write removes it)")
    return problems


def orphans(docs: Path, rendered: set[str]) -> list[str]:
    """Committed render-owned files the current render does not produce."""
    found = set()
    for pattern in RENDER_OWNED:
        for p in docs.glob(pattern):
            name = p.relative_to(docs).as_posix()
            if p.is_file() and name not in rendered and not name.endswith(SKIP_SUFFIXES):
                found.add(name)
    return sorted(found)


def uncovered(docs: Path) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="docs-fresh-") as tmp:
        base_date = stamp_date(docs / "index.html")
        if not base_date:
            raise CheckError(f"no generated date stamp in {docs / 'index.html'}")
        render(Path(tmp), base_date)
        covered = set(_files(Path(tmp)))
    return (
        [n for n in _files(docs) if n not in covered]
        + [f"{n} ({why})" for n, why in sorted(EXCLUDED.items())]
        + sorted(p.relative_to(docs).as_posix() for p in docs.rglob("*.png"))
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--docs", default=str(ROOT / "docs"))
    ap.add_argument("--write", action="store_true",
                    help="regenerate the covered files in docs/ instead of checking")
    ap.add_argument("--list-uncovered", action="store_true",
                    help="list docs/ files this check does not compare")
    args = ap.parse_args(argv)
    docs = Path(args.docs)
    try:
        if args.list_uncovered:
            for name in uncovered(docs):
                print(name)
            return 0
        problems = check(docs, write=args.write)
    except CheckError as exc:
        print(f"docs freshness check could not run: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - any other failure is "could not run", never "stale"
        print(f"docs freshness check could not run: unexpected "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.write:
        print(f"regenerated covered files in {docs}")
        return 0
    if problems:
        print("docs/ is stale against src/ginot - regenerate with "
              "`python scripts/ci/check_docs_fresh.py --write` and commit:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("docs/ is fresh: every covered render_site output matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
