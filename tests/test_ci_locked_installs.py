"""Every CI pip install is hash-locked (#770, approved by the owner).

The OpenSSF Scorecard baseline carried the unhashed installs as accepted
debt first tracked by #709 (now closed); the live tracker is #770. The
fix is structural: workflow install lines only reference requirements-*.txt
lock files with --require-hashes, and every locked entry pins an exact
version with at least one sha256.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows"

# Section: install lines


def _install_lines():
    for path in sorted([*WF.glob("*.yml"), *WF.glob("*.yaml")]):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"\bpip3? install\b|-m pip install\b", line):
                yield path, lineno, line


def test_every_pip_install_uses_require_hashes():
    offenders = [
        f"{p.name}:{n}"
        for p, n, line in _install_lines()
        if "--require-hashes" not in line
    ]
    assert not offenders, f"unhashed pip installs: {offenders}"


def test_every_pip_install_references_only_lock_files():
    # Strip sudo, the pip command itself, flags and shell redirections:
    # whatever is left must be a requirements-*.txt file argument.
    for path, lineno, line in _install_lines():
        body = re.split(r"[>|]", line, maxsplit=1)[0]
        body = re.sub(r"^\s*(?:-\s*)?run:\s*", "", body)  # YAML step key
        body = re.sub(r"\bsudo\b", "", body)
        body = re.sub(r"(?:\S*/)?(?:pip3?|python3?\s+-m\s+pip)\s+install", "", body)
        tokens = body.split()
        args = [
            t
            for t in tokens
            if not t.startswith("-") and t not in {"-r", "--requirement"}
        ]
        files = [t for t in tokens if t.endswith(".txt")]
        assert files, f"{path.name}:{lineno}: install line with no requirements file"
        assert args == files, f"{path.name}:{lineno}: bare package args {args}"
        for f in files:
            assert f.startswith("requirements-") and (ROOT / f).is_file(), (
                f"{path.name}:{lineno}: not a committed lock file: {f}"
            )


# Section: lock files


def _lock_entries(path):
    """(package, line-index) for each pinned entry of a lock file."""
    text = path.read_text()
    for m in re.finditer(r"^([A-Za-z0-9_.-]+)==(\S+?) \\\n", text, re.MULTILINE):
        yield m.group(1), m.start()


def test_lock_files_pin_versions_and_hashes():
    locks = sorted(ROOT.glob("requirements-*.txt"))
    assert locks, "no lock files found"
    for lock in locks:
        # Join continuation lines: an entry is `pkg==ver \` + hash lines.
        joined = re.sub(r" \\\n\s+", " ", lock.read_text())
        entries = [
            line
            for line in joined.splitlines()
            if line and not line.startswith("#") and not line.startswith(" ")
        ]
        assert entries, f"{lock.name}: no pinned entries"
        for line in entries:
            assert re.match(r"^[A-Za-z0-9_.-]+==", line), f"{lock.name}: {line}"
            assert "--hash=sha256:" in line, f"{lock.name}: unhashed entry: {line}"


def test_runtime_lock_covers_the_loose_source():
    # requirements.txt stays the human-edited source; every package it
    # names must be pinned in requirements-lock.txt (#770 regeneration).
    source = (ROOT / "requirements.txt").read_text()
    lock = (ROOT / "requirements-lock.txt").read_text()
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pkg = re.split(r"[>=<; ]", line, maxsplit=1)[0].lower()
        assert re.search(rf"^{re.escape(pkg)}==", lock, re.MULTILINE | re.IGNORECASE), (
            f"requirements-lock.txt drops {pkg}"
        )
