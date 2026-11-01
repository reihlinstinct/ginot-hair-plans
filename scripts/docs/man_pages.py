#!/usr/bin/env python3
"""Generate, check or install public command manuals (internal packaging tool)."""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ginot.cli_spec import COMMANDS, man_page


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="Fail if committed pages drift."
    )
    mode.add_argument(
        "--install",
        type=Path,
        metavar="PREFIX",
        help="Install under PREFIX/share/man/man1.",
    )
    args = parser.parse_args(argv)
    pages = ROOT / "man" / "man1"
    if args.install:
        target = args.install / "share" / "man" / "man1"
        # Check before copying so stale manuals cannot be installed silently.
        if main(["--check"]):
            return 1
        target.mkdir(parents=True, exist_ok=True)
        for command in COMMANDS:
            shutil.copyfile(pages / f"{command}.1", target / f"{command}.1")
        print(f"Installed {len(COMMANDS)} manuals in {target}")
        return 0
    expected = {f"{command}.1" for command in COMMANDS}
    if args.check and {p.name for p in pages.glob("*.1")} != expected:
        print(
            "Manual package file list differs from command specification",
            file=sys.stderr,
        )
        return 1
    for command in COMMANDS:
        path = pages / f"{command}.1"
        content = man_page(command)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                print(f"Manual drift: {path.relative_to(ROOT)}", file=sys.stderr)
                return 1
        else:
            pages.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
