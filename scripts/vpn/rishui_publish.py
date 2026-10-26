"""Active s.149 publications list from the municipality's Rishui149 API (issue #519).

One GET through the owner-operated L2TP tunnel. Stop-on-challenge contract:
HTTP 403/429/503 or a challenge-shaped body exits 2 with no retry and no
workaround. The payload carries only public notice fields (tik number, street,
house number, neighborhood, dates) - no personal data.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PUBLISH_URL = (
    "https://jergisrishuimessages.jerusalem.muni.il"
    "/Rishui149/api/publish/?fromDate=&toDate=&tik_num=&streetcode=&schncode=&betokef=true"
)
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) ginot-hair-plans/1.0"
CHALLENGE_STATUSES = {403, 429, 503}
CHALLENGE_MARKERS = ("access denied", "akamai", "captcha", "challenge")

# The 7 Ginot HaIr council neighborhoods, user-confirmed 2026-10-26 against
# ginothair.org.il/about-us (the exported council polygon is wider - issue to
# tighten it is separate). Municipal spelling variants included.
TRACKED_SCHN = frozenset(
    {
        "קטמון הישנה",
        "רחביה",
        "קריית שמואל",
        "מושבה גרמנית",
        "המושבה היוונית",
        "טלביה",
        "טלביה/המוגרבים",
        "נוה שאנן/ניות",
    }
)


class ChallengeError(Exception):
    """Anti-bot challenge or access denial: hard stop (exit 2), never worked around."""


def is_challenge(status: int, body: str) -> bool:
    if status in CHALLENGE_STATUSES:
        return True
    low = body.lower()
    return any(marker in low for marker in CHALLENGE_MARKERS)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Single-GET contract: never follow redirects. A redirect would turn the
    one allowed request into several (and is how anti-bot systems bounce
    clients), so it is surfaced as an HTTPError and stopped on."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch_publish(url: str = PUBLISH_URL, timeout: int = 40) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        if 300 <= exc.code < 400:
            raise ChallengeError(f"HTTP {exc.code} redirect (not followed)") from exc
        if is_challenge(exc.code, body):
            raise ChallengeError(f"HTTP {exc.code}") from exc
        raise
    if is_challenge(status, body):
        raise ChallengeError(f"HTTP {status}")
    return parse_rows(body)


def _date(value: object) -> str | None:
    if not value:
        return None
    return str(value)[:10]


def normalize_row(item: dict) -> dict:
    return {
        "myIndex": item["myIndex"],
        "tik_num": item["tik_num"],
        "street": item.get("rehov"),
        "house_number": item.get("misp_bait"),
        "neighborhood": item.get("schn"),
        "place_description": item.get("teur_makom"),
        "publication_date": _date(item.get("ED800")),
        "objection_deadline": _date(item.get("PD900")),
        "ed700": _date(item.get("ED700")),
        "connected_rec_id": item.get("connectedRecID"),
        "doc_id": item.get("DocId"),
    }


def parse_rows(payload: str) -> list[dict]:
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("publish API did not return a list")
    rows = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("unexpected publish API row shape")
        # myIndex is the dedup key and tik_num the permit join key: both must
        # be real scalars, not null/containers (a null myIndex would collapse
        # detect_new's known-set onto one key).
        my_index = item.get("myIndex")
        tik_num = item.get("tik_num")
        if isinstance(my_index, bool) or not isinstance(my_index, (int, str)) or my_index == "":
            raise ValueError("unexpected publish API row shape: bad myIndex")
        if not isinstance(tik_num, str) or not tik_num:
            raise ValueError("unexpected publish API row shape: bad tik_num")
        rows.append(normalize_row(item))
    return rows


def detect_new(old_rows: list[dict], new_rows: list[dict]) -> list[dict]:
    known = {row["myIndex"] for row in old_rows}
    return [row for row in new_rows if row["myIndex"] not in known]


def filter_tracked(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("neighborhood") in TRACKED_SCHN]


def summarize(rows: list[dict]) -> str:
    lines = [f"active publications: {len(rows)}"]
    tracked = filter_tracked(rows)
    lines.append(f"in tracked neighborhoods: {len(tracked)}")
    for row in tracked:
        deadline = row["objection_deadline"] or "-"
        lines.append(
            f"  {row['tik_num']} | {row['street']} {row['house_number']} | "
            f"{row['neighborhood']} | published {row['publication_date']} | deadline {deadline}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    fetch_cmd = sub.add_parser("fetch", help="fetch the active publications list (one request)")
    fetch_cmd.add_argument("--out", required=True, help="output JSON path")
    args = parser.parse_args(argv)
    if args.cmd == "fetch":
        try:
            rows = fetch_publish()
        except ChallengeError as exc:
            print(f"CHALLENGE: {exc}; hard stop, no retry", file=sys.stderr)
            return 2
        Path(args.out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(summarize(rows))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
