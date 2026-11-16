#!/usr/bin/env python3
"""Regenerate docs/permits.html from data/permit_requests.json (#405).

The permit feed updates data/permit_requests.json on every batch, but the
permits fragment the site loads was only rebuilt by the weekly refresh -
a newly published permit stayed invisible on the site for up to a week
(user report 2026-10-24: publication-status tik 2026/0439.00 missing).
This script re-renders ONLY the fragment through the same _permits_section
code path as the weekly site build: no plan rows, no network. It also
rewrites the permits[] array inside docs/data.json (keeping generated,
rows and changes) so the public data endpoint and the MCP server stop
lagging the feed until the weekly refresh (#559). It runs in the
permit-feed publish step under set -e, so a render failure fails the
run red instead of silently shipping stale rows.
"""

import argparse
import json
import os
import sys
import tempfile

import _src_path  # noqa: F401  (shared bootstrap: adds the repo src/ to sys.path)

from ginot.mapdata import permit_points, write_permit_points
from ginot.page import _permits_section, publication_evidence_tiks, write_permit_ids
from ginot.public_api import project

DATA = "data/permit_requests.json"
OUT = "docs/permits.html"
# #441: the small default-view subset the page loads first; the full list
# above loads only on a non-default interaction. Same source, same batch.
DEFAULT_OUT = "docs/permits-default.html"
PUBLICATIONS = "data/publications_active.json"
IDS_OUT = "docs/permit-ids.json"  # read by the submit worker (#515)


DATA_JSON = "docs/data.json"


def update_data_json(permits) -> None:
    """Rewrite only permits[] inside docs/data.json (#559).

    The public data endpoint (and the MCP server that reads it) was only
    refreshed by the weekly site build, so permit-feed changes lagged it
    by up to a week. generated/rows/changes still belong to the weekly
    build; a missing data.json is left for it to create."""
    if not os.path.exists(DATA_JSON):
        print(f"{DATA_JSON} does not exist - leaving it to the weekly refresh")
        return
    with open(DATA_JSON, encoding="utf-8") as fh:
        data = json.load(fh)
    data["permits"] = project(permits, "permits")
    # Atomic replace: a crash mid-write must never leave a truncated public
    # endpoint for the publish step to stage.
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(DATA_JSON), prefix=".data-", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, DATA_JSON)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print(f"rewrote permits[] ({len(permits)} requests) in {DATA_JSON}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-dependencies",
        action="store_true",
        help="Check imports without reading or changing data",
    )
    parser.add_argument(
        "--default-only",
        action="store_true",
        help="Rewrite only the evidence-dependent default subset (#629)",
    )
    args = parser.parse_args()
    if args.check_dependencies:
        print("permit renderer dependencies available")
        return 0
    with open(DATA, encoding="utf-8") as fh:
        permits = json.load(fh).get("requests", [])
    if not permits:
        print(f"{DATA} has no requests - refusing to empty the fragment")
        return 1
    if args.default_only:
        # Match render_site's map-missing labels without rewriting other files.
        from pathlib import Path

        parcels_path = Path("data/ginot_hair_parcels.geojson")
        parcels = (
            json.loads(parcels_path.read_text(encoding="utf-8"))
            if parcels_path.exists()
            else {}
        )
        permit_map = permit_points(permits, parcels)
    else:
        permit_map = write_permit_points(
            permits, "data/ginot_hair_parcels.geojson", "docs/permit-points.json"
        )
    missing = set(permit_map["missing_location"])
    permits = [dict(p, _map_missing=p.get("tik_num") in missing) for p in permits]
    evidence = publication_evidence_tiks(PUBLICATIONS)
    if not _permits_section(
        permits,
        rows_file=None if args.default_only else OUT,
        default_rows_file=DEFAULT_OUT,
        evidence_tiks=evidence,
    ):
        print("permits section render produced no output")
        return 1
    # Per-language fragments (i18n pages, #942): the daily publication and
    # permit-feed refreshes change evidence dates, so every language's
    # fragment must regenerate with the root one or docs-fresh goes stale.
    from ginot import i18n

    for code in i18n.lang_codes():
        if code == i18n.default_lang():
            continue
        os.makedirs(f"docs/{code}", exist_ok=True)
        if not _permits_section(
            permits,
            rows_file=None if args.default_only else f"docs/{code}/permits.html",
            default_rows_file=f"docs/{code}/permits-default.html",
            evidence_tiks=evidence,
            lang=code,
            pre=i18n.asset_prefix(code),
        ):
            print(f"permits section render produced no output for {code}")
            return 1
    if args.default_only:
        print(f"rendered default permit subset into {DEFAULT_OUT}")
        return 0
    print(
        f"rendered {len(permits)} permit rows into {OUT} and the default subset into {DEFAULT_OUT}"
    )
    n = write_permit_ids(permits, IDS_OUT)
    print(f"wrote {n} permit ids into {IDS_OUT}")
    update_data_json(permits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
