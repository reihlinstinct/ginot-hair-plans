"""Supply-chain guard (#125): every third-party action is pinned to a full
commit SHA, and every workflow declares a top-level permissions block so
jobs start from least privilege. A mutable tag (@v4) lets whoever controls
the tag change the code our workflows run with repository secrets."""

import re
from pathlib import Path

WORKFLOWS = sorted(
    (Path(__file__).parent.parent / ".github" / "workflows").glob("*.yml")
)
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)")
PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _uses():
    for path in WORKFLOWS:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = USES.match(line)
            if m:
                yield path.name, lineno, m.group(1)


def test_found_workflows_and_actions():
    assert WORKFLOWS
    assert list(_uses())


def test_third_party_actions_are_sha_pinned():
    unpinned = [
        f"{name}:{lineno}: {ref}"
        for name, lineno, ref in _uses()
        if not ref.startswith("./") and not PINNED.match(ref)
    ]
    assert not unpinned, "pin these actions to a full commit SHA:\n" + "\n".join(
        unpinned
    )


def test_every_workflow_has_top_level_permissions():
    missing = [
        p.name
        for p in WORKFLOWS
        if not re.search(r"^permissions:", p.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert not missing, "add a top-level permissions block to: " + ", ".join(missing)
