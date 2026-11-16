"""Daily active-publications diff for the Rishui149 watch (issue #527).

Scope: the seven council neighborhoods AND a parcel inside the council
polygon, or explicit official-address point evidence for unknown parcel joins.
Rewrites the baseline (inside + unresolved rows) and reports new or newly
resolved rows. First run seeds the baseline without an alert storm.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from publication_points import load_points, resolve_official_points
from rishui_publish import (
    SCOPE_SCHN,
    detect_new,
    load_parcel_keys,
    load_tik_parcels,
    resolve_in_polygon,
)


def load_rows(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def update(
    old_rows: list[dict] | None, new_rows: list[dict]
) -> tuple[list[dict], dict, bool]:
    """Return (baseline_to_write, alert_payload, seeded).

    Baseline keeps in-polygon rows plus unresolved-tik rows (so an unresolved
    row is not re-flagged daily); out-of-polygon rows are dropped (issue #527:
    the ingest ignores everything outside the polygon).
    """
    in_scope = [r for r in new_rows if r["in_polygon"] is not False]
    if old_rows is None:
        return in_scope, {"new_in_polygon": [], "unresolved_new": []}, True
    fresh = detect_new(old_rows, new_rows)
    # A baseline row whose tik later resolves (the tracker learns its parcel)
    # is not "new" by myIndex, but entering the polygon IS alertable.
    old_flags = {r.get("myIndex"): r.get("in_polygon") for r in old_rows}
    resolved = [
        r
        for r in new_rows
        if r["in_polygon"] is True
        and r["myIndex"] in old_flags
        and old_flags[r["myIndex"]] is not True
    ]
    payload = {
        "new_in_polygon": [r for r in fresh if r["in_polygon"] is True] + resolved,
        "unresolved_new": [r for r in fresh if r["in_polygon"] is None],
    }
    return in_scope, payload, False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--old", required=True, help="committed baseline JSON (may not exist)"
    )
    parser.add_argument("--new", required=True, help="freshly fetched JSON")
    parser.add_argument("--permits", required=True, help="data/permit_requests.json")
    parser.add_argument(
        "--parcels", required=True, help="data/ginot_hair_parcels.geojson"
    )
    parser.add_argument(
        "--point-evidence",
        default="data/publication_point_evidence.json",
        help="curated municipal-address point evidence for unresolved joins",
    )
    parser.add_argument(
        "--council",
        default="data/council_ginot_hair.geojson",
        help="council boundary GeoJSON (repo-root relative default)",
    )
    parser.add_argument("--out-active", required=True, help="baseline to write")
    parser.add_argument("--out-new", required=True, help="alert payload to write")
    args = parser.parse_args(argv)

    old_rows = load_rows(Path(args.old))
    new_rows = json.loads(Path(args.new).read_text(encoding="utf-8"))
    resolve_in_polygon(
        new_rows,
        load_tik_parcels(Path(args.permits)),
        load_parcel_keys(Path(args.parcels)),
    )
    resolve_official_points(
        new_rows, load_points(Path(args.point_evidence)), Path(args.council), SCOPE_SCHN
    )
    baseline, payload, seeded = update(old_rows, new_rows)
    write_json(Path(args.out_active), baseline)
    write_json(Path(args.out_new), payload)
    if seeded:
        print(
            f"seeded baseline with {len(baseline)} in-scope publications; no alert entries"
        )
    else:
        print(
            f"{len(payload['new_in_polygon'])} new in-polygon publication(s); "
            f"{len(payload['unresolved_new'])} unresolved (tik not in tracker)"
        )
        for row in payload["new_in_polygon"] + payload["unresolved_new"]:
            deadline = row["objection_deadline"] or "-"
            marker = "" if row["in_polygon"] else " [UNRESOLVED]"
            if row.get("in_polygon_source") == "publication_point_evidence":
                marker += " [POINT-EVIDENCE]"
            print(
                f"  NEW {row['tik_num']} | {row['street']} {row['house_number']} | "
                f"{row['neighborhood']} | published {row['publication_date']} | deadline {deadline}{marker}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
