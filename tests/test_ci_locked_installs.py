"""Every CI pip install is hash-locked (#770; the hash-locking was
owner-approved after that issue's body was written).

The OpenSSF Scorecard baseline carried the unhashed installs as accepted
debt first tracked by #709 (now closed); the live tracker is #770. The
fix is structural: workflow install lines only reference requirements-*.txt
lock files with --require-hashes, and every locked entry pins an exact
version with at least one sha256. #1009 adds source-vs-lock specifier and
co-installed-lock pin-equality coverage.
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


# Section: source vs lock

_CI_PYTHONS = ["3.11", "3.12", "3.13", "3.15"]


def _marker_env(py):
    return {
        "python_version": py,
        "python_full_version": py + ".0",
        "implementation_version": py + ".0",
        "os_name": "posix",
        "sys_platform": "linux",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
        "platform_python_implementation": "CPython",
        "platform_release": "",
        "platform_version": "",
        "implementation_name": "cpython",
        "extra": "",
    }


def _lock_pins(path):
    """{canonical name: [(version, marker-or-None)]} from a lock file."""
    from packaging.utils import canonicalize_name

    joined = re.sub(r" \\\n\s+", " ", path.read_text())
    pins = {}
    for line in joined.splitlines():
        # Drop hash options and trailing comments before parsing the pin.
        line = re.split(r"\s+--hash=", line, maxsplit=1)[0]
        line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
        m = re.match(r"^([A-Za-z0-9_.-]+)==(\S+?)(?:\s*;\s*(\S.*))?$", line)
        if not m:
            continue
        name, version, marker = m.group(1), m.group(2), m.group(3)
        pins.setdefault(canonicalize_name(name), []).append(
            (version, marker.strip() if marker else None)
        )
    return pins


def test_source_specifiers_cover_locked_versions():
    # #1009: requirements.txt is the human-edited source; every locked pin
    # whose marker overlaps a source requirement's marker must satisfy that
    # requirement's specifier, or a bump in the source silently never takes
    # effect (CI installs only the lock).
    from packaging.markers import Marker
    from packaging.requirements import Requirement

    pins = _lock_pins(ROOT / "requirements-lock.txt")
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        req = Requirement(line)
        for version, marker in pins.get(canonical := req.name.lower(), []):
            for py in _CI_PYTHONS:
                env = _marker_env(py)
                if req.marker is not None and not req.marker.evaluate(env):
                    continue
                if marker is not None and not Marker(marker).evaluate(env):
                    continue
                assert req.specifier.contains(version, prereleases=True), (
                    f"requirements-lock.txt pins {canonical}=={version} "
                    f"(marker {marker!r}) which violates source specifier "
                    f"{req.specifier} on Python {py}"
                )
                break  # one overlapping environment is enough to check


# Section: cross-lock pins


def _co_installed_lock_groups():
    """Lock-file sets co-installed by one pip, derived from the workflows."""
    import yaml

    groups = []
    for wf in sorted([*WF.glob("*.yml"), *WF.glob("*.yaml")]):
        doc = yaml.safe_load(wf.read_text())
        for job_name, job in (doc.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                run = step.get("run") or ""
                for line in run.splitlines():
                    m = re.search(
                        r"((?:\S*/)?pip3?|python3?\s+-m\s+pip)\s+install", line
                    )
                    if not m:
                        continue
                    locks = [
                        t
                        for t in line.split()
                        if t.startswith("requirements-") and t.endswith(".txt")
                    ]
                    if locks:
                        groups.append((wf.name, str(job_name), m.group(1), locks))
    # Same pip executable inside one job shares one environment.
    merged = {}
    for wf_name, job, pip, locks in groups:
        merged.setdefault((wf_name, job, pip), set()).update(locks)
    return [
        (wf_name, job, pip, sorted(locks))
        for (wf_name, job, pip), locks in merged.items()
        if len(locks) > 1
    ]


def test_co_installed_locks_pin_equal_versions():
    # #1009: two locks installed into one environment must pin any shared
    # package at the same version and marker, or the pair fails only at
    # resolver time in CI with an unclear error.
    groups = _co_installed_lock_groups()
    assert groups, "no co-installed lock groups found in workflows"
    for wf_name, job, pip, locks in groups:
        pin_maps = {lock: _lock_pins(ROOT / lock) for lock in locks}
        shared = set.intersection(*[set(m) for m in pin_maps.values()])
        for name in sorted(shared):
            seen = {
                (lock, version, marker)
                for lock, pins in pin_maps.items()
                for version, marker in pins[name]
            }
            versions = {(version, marker) for _, version, marker in seen}
            assert len(versions) == 1, (
                f"{wf_name} job {job!r} ({pip}): {name} pinned differently "
                f"across co-installed locks: {sorted(seen)}"
            )
