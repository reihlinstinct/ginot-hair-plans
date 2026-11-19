#!/usr/bin/env python3
"""Fail when private repo names or per-repo private-minute figures leak into public text.

Issue #1053 (follow-up to the #1052 scrub): private repository names, and the
per-repo Actions-minute figures tied to them, were removed from this repo's
public issues and PRs on 2026-11-19. This guard keeps them out of tracked
content (including the PR/issue templates under .github/) and, via the
private-guard CI job, out of PR bodies.

The blocklist (.github/private-guard-hashes.json) stores sha256 hashes, first
16 hex chars, of lowercase single tokens and adjacent two-token phrases, so
the blocklist itself does not expose the names. A token matches the regex
``[a-z0-9][a-z0-9._-]*`` after lowercasing; hyphenated names are single
tokens, and the spaced variant of a name is covered as a two-token phrase.

To block a new word or two-word phrase, append its hash:

    python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].lower().encode()).hexdigest()[:16])" "word or phrase"

Exit codes: 0 clean, 1 blocked content found (locations plus the matched hash
are printed, never the plaintext), 2 usage or blocklist error.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLOCKLIST = ROOT / ".github" / "private-guard-hashes.json"
TOKEN = re.compile(r"[a-z0-9][a-z0-9._-]*")


def load_hashes(path: Path = BLOCKLIST) -> frozenset[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(data["hashes"])


_digest_cache: dict[str, str] = {}


def _digest(text: str) -> str:
    digest = _digest_cache.get(text)
    if digest is None:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        _digest_cache[text] = digest
    return digest


def find_hits(text: str, hashes: frozenset[str]) -> list[tuple[int, str]]:
    """Return (line_number, hash) for every blocked token or token pair."""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        words = TOKEN.findall(line.lower())
        candidates = set(words) | {f"{a} {b}" for a, b in itertools.pairwise(words)}
        for candidate in candidates:
            digest = _digest(candidate)
            if digest in hashes:
                hits.append((lineno, digest))
    return hits


def tracked_files(root: Path = ROOT) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
    )
    return [root / name for name in out.stdout.splitlines()]


def scan_paths(paths: list[Path], hashes: frozenset[str]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:
            continue  # binary file: names cannot be scanned as text
        text = raw.decode("utf-8", errors="ignore")
        for lineno, digest in find_hits(text, hashes):
            problems.append(
                f"{path.relative_to(ROOT)}:{lineno}: blocked entry {digest}"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="scan this file instead of tracked content (repeatable)",
    )
    parser.add_argument(
        "--text",
        default=None,
        help="scan this literal text (used by the CI job for the PR body)",
    )
    parser.add_argument(
        "--source",
        default="text",
        help="label for --text hits, e.g. 'PR body'",
    )
    args = parser.parse_args(argv)

    try:
        hashes = load_hashes()
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"private-names guard: cannot load blocklist: {exc}")
        return 2

    problems: list[str] = []
    if args.text is not None:
        for lineno, digest in find_hits(args.text, hashes):
            problems.append(f"{args.source}:{lineno}: blocked entry {digest}")
    paths = [Path(f) for f in args.file]
    if not paths and args.text is None:
        paths = tracked_files()
    problems.extend(scan_paths(paths, hashes))

    if problems:
        print(
            "private-names guard: blocked content found (hash shown, never plaintext):"
        )
        print("\n".join(problems))
        return 1
    print("private-names guard: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
