#!/usr/bin/env python3
"""Per-language permit-page fragment paths: the ONE copy of the rule (#979).

docs/<lang>/{index,permits,permits-default}.html for every i18n language
except the default. Shared by permit-feed.yml (staging regenerated pages,
#972) and permit_router._language_permit_fragment (publication allowlist,
#942) so the workflow and the router can never drift.

Usage: python3 scripts/ci/permit_fragments.py   (prints the space-joined list)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _src_path  # noqa: F401  (shared bootstrap: adds the repo src/ to sys.path)

from ginot import i18n

FRAGMENT_NAMES = ("index.html", "permits.html", "permits-default.html")


def languages():
    return frozenset(i18n.lang_codes()) - {i18n.default_lang()}


def fragments():
    return [
        f"docs/{code}/{name}" for code in sorted(languages()) for name in FRAGMENT_NAMES
    ]


def main():
    print(" ".join(fragments()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
