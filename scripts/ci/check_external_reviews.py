#!/usr/bin/env python3
"""CI guard: data/external_reviews.json is append-only and valid.
Usage: check_external_reviews.py [--base REF]  (base skipped if the ref/file is absent)"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from ginot import external_reviews as er

PATH = "data/external_reviews.json"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="")
    args = ap.parse_args(argv)
    head = er.load(PATH)
    problems = er.validate_entries(head)
    if args.base:
        r = subprocess.run(
            ["git", "show", f"{args.base}:{PATH}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode == 0:
            problems += er.check_append_only(
                json.loads(r.stdout).get("entries", []), head
            )
    for p in problems:
        print("FAIL:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
