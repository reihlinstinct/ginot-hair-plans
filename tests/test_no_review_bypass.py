"""#564: repo-wide guard that no workflow can bypass review of data PRs.

The per-workflow tests (#582, #584, #590) each keep their own forbidden-string
list. This is the catch-all: it scans every ``.github/workflows/*.yml`` run
step and every ``scripts/ci/*`` file the workflows call, after normalizing
whitespace, quoting and line continuations, for merge, approval, dispatch,
re-run, Pages and default-branch/mirror push forms, including the alternate
spellings the per-PR lists miss.

Known exceptions live in ALLOWLIST, each with a reason and, where it is
reachable only after a reviewed merge, the gate its step must keep.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
CI_SCRIPTS = ROOT / "scripts/ci"

# (rule id, regex over normalized text). Normalized text: quotes removed,
# backslash-newline joined, full-line shell comments dropped, whitespace
# runs collapsed to one space.
RULES = [
    ("gh-pr-merge", r"\bgh pr merge\b"),
    ("gh-pr-review", r"\bgh pr review\b"),
    ("admin-flag", r"(?<![\w-])--admin\b"),
    ("update-branch", r"\bgh pr update-branch\b|/update-branch\b"),
    ("graphql-merge", r"\bmergePullRequest\b|\benablePullRequestAutoMerge\b"),
    ("rest-merge", r"/pulls/\S*/merge\b|/merges\b"),
    ("rest-approve-review", r"\bevent=APPROVE\b|/approve\b"),
    ("dispatch", r"/dispatches\b"),
    ("gh-workflow-run", r"\bgh workflow run\b"),
    ("gh-run-rerun", r"\bgh run rerun\b|/rerun(-failed-jobs)?\b"),
    ("pages", r"/pages/builds\b|/pages/deployments?\b|actions/deploy-pages\b"),
    (
        "push-default-or-mirror",
        r"\bgit (?:-C \S+ )?push\b[^\n;&|]*?(?:[\s:+](?:refs/heads/)?(?:main|mirror)\b)",
    ),
    (
        "push-force",
        r"\bgit (?:-C \S+ )?push\b[^\n;&|]*?(?:\s--force(?:-with-lease)?\b|\s-f\b|\s\+\S)",
    ),
]

FORBIDDEN_PERMISSIONS = {"actions": "write", "pages": "write", "id-token": "write"}

# (file, rule id, substring of the normalized command, required substring of
# the step's ``if`` or None, reason).
ALLOWLIST = [
    (
        "permit-feed.yml",
        "gh-workflow-run",
        "gh workflow run ci.yml --ref $BRANCH",
        None,
        "runs CI on the PR branch just pushed; starts checks, merges nothing",
    ),
    (
        "permit-feed.yml",
        "gh-workflow-run",
        "gh workflow run audit.yml --repo reihlinstinct/parcel-coverage-audit",
        "steps.publish.outputs.merged == 'true'",
        "read-only auditor, only after a reviewed merge (#562)",
    ),
    (
        "permit-feed.yml",
        "gh-workflow-run",
        "gh workflow run permit-feed.yml -f mode=enrich",
        "steps.publish.outputs.merged == 'true'",
        "enrich chain, only after a reviewed merge (#145, #562)",
    ),
]

# Workflow-level permissions that are known and reviewed elsewhere.
PERMISSION_ALLOWLIST = {
    ("permit-feed.yml", "actions"): "needed by the allowlisted gh workflow run steps",
    (
        "permit-feed.yml",
        "pages",
    ): "pre-existing; no Pages step remains (see #564 review note)",
}


def normalize(text):
    text = text.replace("\\\n", " ")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    text = "\n".join(lines).replace('"', "").replace("'", "")
    return re.sub(r"[ \t]+", " ", text)


def _allowed(file, rule, command, step_if):
    for a_file, a_rule, needle, gate, _reason in ALLOWLIST:
        if (a_file, a_rule) == (file, rule) and needle in command:
            return gate is None or gate in (step_if or "")
    return False


def _permission_violations(file, perms, where):
    out = []
    if isinstance(perms, str):
        if perms == "write-all":
            out.append((file, "permissions", f"{where}: write-all"))
        return out
    for key, value in (perms or {}).items():
        if (
            FORBIDDEN_PERMISSIONS.get(key) == value
            and (file, key) not in PERMISSION_ALLOWLIST
        ):
            out.append((file, "permissions", f"{where}: {key}: {value}"))
    return out


def scan_workflow(file, text):
    """Return [(file, rule, detail)] for one workflow's YAML text."""
    doc = yaml.safe_load(text) or {}
    found = _permission_violations(file, doc.get("permissions"), "top-level")
    for job_id, job in (doc.get("jobs") or {}).items():
        found += _permission_violations(file, job.get("permissions"), f"job {job_id}")
        for step in job.get("steps") or []:
            uses = step.get("uses", "")
            if re.search(RULES[[r[0] for r in RULES].index("pages")][1], uses):
                found.append((file, "pages", uses))
            run = step.get("run")
            if not run:
                continue
            command = normalize(run)
            for rule, pattern in RULES:
                for m in re.finditer(pattern, command):
                    line = command[command.rfind("\n", 0, m.start()) + 1 :].split(
                        "\n", 1
                    )[0]
                    if not _allowed(file, rule, line, step.get("if")):
                        found.append((file, rule, line.strip()))
    return found


def scan_script(file, text):
    command = normalize(text)
    found = []
    for rule, pattern in RULES:
        for m in re.finditer(pattern, command):
            line = command[command.rfind("\n", 0, m.start()) + 1 :].split("\n", 1)[0]
            found.append((file, rule, line.strip()))
    return found


def test_no_workflow_or_ci_script_can_bypass_review():
    found = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        found += scan_workflow(path.name, path.read_text())
    for path in sorted(CI_SCRIPTS.iterdir()):
        if (
            path.is_file()
            and path.suffix in {".py", ".sh"}
            and path.name != "pending_data_pr.py"
        ):
            found += scan_script(path.name, path.read_text())
    assert found == []


def test_every_allowlist_entry_still_matches_a_real_step():
    """A stale entry would silently widen the allowlist for future edits."""
    for file, rule, needle, gate, _reason in ALLOWLIST:
        doc = yaml.safe_load((WORKFLOWS / file).read_text())
        steps = [s for j in doc["jobs"].values() for s in j.get("steps") or []]
        hits = [s for s in steps if needle in normalize(s.get("run") or "")]
        assert len(hits) == 1, (file, needle)
        if gate:
            assert gate in hits[0]["if"], (file, needle)


CLEAN = """
name: clean
on: workflow_dispatch
permissions:
  contents: write
  pull-requests: write
jobs:
  data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - run: |
          # comments may mention gh pr merge without running it
          BRANCH="weekly-refresh/$(date +%Y%m%d)"
          git push -u origin "$BRANCH"
          gh pr create --base main --head "$BRANCH"
          git push origin HEAD:badge-data
"""


def planted(
    run=None,
    permissions=None,
    job_permissions=None,
    uses=None,
    file="planted.yml",
    step_if=None,
):
    doc = yaml.safe_load(CLEAN)
    if permissions is not None:
        doc["permissions"] = permissions
    job = doc["jobs"]["data"]
    if job_permissions is not None:
        job["permissions"] = job_permissions
    step = {}
    if run is not None:
        step["run"] = run
    if uses is not None:
        step["uses"] = uses
    if step_if is not None:
        step["if"] = step_if
    if step:
        job["steps"].append(step)
    return file, yaml.safe_dump(doc, sort_keys=False)


def test_clean_fixture_passes():
    assert scan_workflow("clean.yml", CLEAN) == []


PLANTED = [
    ("gh-pr-merge", {"run": 'gh pr merge "$PR" --squash'}),
    ("gh-pr-merge", {"run": 'gh  pr   merge "$PR"'}),  # double spaces
    ("gh-pr-merge", {"run": 'gh pr \\\n  merge "$PR"'}),  # line continuation
    ("gh-pr-merge", {"run": 'gh pr merge --auto --squash "$PR"'}),
    ("admin-flag", {"run": "gh pr create --admin"}),
    ("gh-pr-review", {"run": 'gh pr review "$PR" --approve'}),
    ("update-branch", {"run": 'gh pr update-branch "$PR"'}),
    ("update-branch", {"run": "gh api -X PUT repos/o/r/pulls/1/update-branch"}),
    (
        "graphql-merge",
        {
            "run": "gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'"
        },
    ),
    (
        "graphql-merge",
        {
            "run": "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: {}) { clientMutationId } }'"
        },
    ),
    ("rest-merge", {"run": 'gh api -X PUT "repos/$GITHUB_REPOSITORY/pulls/$N/merge"'}),
    (
        "rest-merge",
        {"run": 'gh api -X POST repos/o/r/merges -f base=main -f head="$BRANCH"'},
    ),
    (
        "rest-approve-review",
        {"run": "gh api repos/o/r/pulls/1/reviews -f event=APPROVE"},
    ),
    ("rest-approve-review", {"run": "gh api -X POST repos/o/r/actions/runs/1/approve"}),
    (
        "dispatch",
        {"run": "gh api repos/o/r/actions/workflows/x.yml/dispatches -f ref=main"},
    ),
    ("dispatch", {"run": "gh api repos/o/r/dispatches -f event_type=go"}),
    ("gh-workflow-run", {"run": "gh workflow run ci.yml"}),
    ("gh-run-rerun", {"run": 'gh run rerun "$RUN"'}),
    (
        "gh-run-rerun",
        {"run": "gh api -X POST repos/o/r/actions/runs/1/rerun-failed-jobs"},
    ),
    ("pages", {"run": "gh api -X POST repos/o/r/pages/builds"}),
    ("pages", {"uses": "actions/deploy-pages@v4"}),
    ("push-default-or-mirror", {"run": "git push origin main"}),
    ("push-default-or-mirror", {"run": "git push origin HEAD:main"}),
    ("push-default-or-mirror", {"run": "git push origin HEAD:refs/heads/main"}),
    ("push-default-or-mirror", {"run": 'git push origin "$BRANCH":main'}),
    ("push-default-or-mirror", {"run": "git push origin origin/main:mirror"}),
    ("push-default-or-mirror", {"run": 'git -C "$WORK" push origin HEAD:mirror'}),
    ("push-force", {"run": 'git push --force origin "$BRANCH"'}),
    ("push-force", {"run": 'git push -f origin "$BRANCH"'}),
    ("push-force", {"run": 'git push origin +"$BRANCH"'}),
    ("permissions", {"permissions": {"contents": "write", "actions": "write"}}),
    ("permissions", {"job_permissions": {"actions": "write"}}),
    ("permissions", {"job_permissions": {"pages": "write"}}),
    ("permissions", {"permissions": "write-all"}),
    # Allowlisted command outside its file, or without its merge gate.
    ("gh-workflow-run", {"run": "gh workflow run permit-feed.yml -f mode=enrich"}),
    (
        "gh-workflow-run",
        {
            "run": "gh workflow run permit-feed.yml -f mode=enrich",
            "file": "permit-feed.yml",
            "step_if": "${{ success() }}",
        },
    ),
]


@pytest.mark.parametrize(
    "rule,kwargs", PLANTED, ids=[f"{r}-{i}" for i, (r, _) in enumerate(PLANTED)]
)
def test_planted_violation_is_caught(rule, kwargs):
    file, text = planted(**kwargs)
    assert rule in {r for _, r, _ in scan_workflow(file, text)}


def test_gated_allowlist_entry_passes_only_in_its_file():
    file, text = planted(
        run="gh workflow run permit-feed.yml -f mode=enrich",
        file="permit-feed.yml",
        step_if="${{ success() && steps.publish.outputs.merged == 'true' }}",
    )
    assert scan_workflow(file, text) == []


def test_script_scanner_catches_planted_form(tmp_path):
    assert {
        r for _, r, _ in scan_script("x.sh", 'git -C "$W" push origin HEAD:main\n')
    } == {"push-default-or-mirror"}
    assert scan_script("x.sh", 'git -C "$W" push origin HEAD:badge-data\n') == []
