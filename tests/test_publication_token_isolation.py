"""Regression (#567): third-party renderer/dependency code in permit-feed must
never see a publication token.

The renderer job installs wheels from requirements.txt, and every python3
start runs their .pth startup code. Publication secrets therefore live only
in a separate job that runs no Python at all, and that job accepts the
renderer's commit only through a fail-closed bundle check
(scripts/ci/verify_publication_bundle.sh), executed here against synthetic
repositories.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/permit-feed.yml"
VERIFY = ROOT / "scripts/ci/verify_publication_bundle.sh"
PUBLICATION_SECRETS = ("REFRESH_DISPATCH_TOKEN", "PARCEL_AUDIT_DISPATCH_TOKEN")
# Anything that starts an interpreter able to import installed packages, or
# installs them.
INTERPRETER = re.compile(r"\b(python[0-9.]*|pip[0-9.]*|pytest|node|npm|npx|uv|pipx)\b")


def load(text=None):
    return yaml.safe_load(text if text is not None else WORKFLOW.read_text())


def dormant(step, doc):
    """The read-only auditor dispatch (PARCEL_AUDIT_DISPATCH_TOKEN) still sits in
    the renderer job but only runs after a confirmed reviewed merge, which this
    workflow never reports (merged=true is emitted nowhere, #562/#564). Its
    secret is never materialized. #565 must move it out before enabling it."""
    return ("steps.publish.outputs.merged == 'true'" in step.get("if", "")
            and "merged=true" not in yaml.safe_dump(doc)
            and "REFRESH_DISPATCH_TOKEN" not in str(step))


def secret_jobs(doc):
    return {name: job for name, job in doc["jobs"].items()
            if any(any(s in str(step) for s in PUBLICATION_SECRETS) and not dormant(step, doc)
                   for step in job.get("steps", []))
            or any(s in str(job.get("env", {})) for s in PUBLICATION_SECRETS)}


def violations(doc):
    """Return reasons the workflow lets dependency code reach a publication secret."""
    found = []
    if any(s in str(doc.get("env", {})) for s in PUBLICATION_SECRETS):
        found.append("workflow-level env carries a publication secret")
    for name, job in secret_jobs(doc).items():
        for step in job.get("steps", []):
            if "actions/setup-python" in step.get("uses", ""):
                found.append(f"{name}: setup-python in a token job")
            if INTERPRETER.search(step.get("run", "")):
                found.append(f"{name}: interpreter in a token job: {step.get('name')}")
            if "requirements" in step.get("run", ""):
                found.append(f"{name}: installs requirements in a token job")
    for name, job in doc["jobs"].items():
        runs = "\n".join(s.get("run", "") for s in job.get("steps", []))
        if "-r requirements.txt" in runs and name in secret_jobs(doc):
            found.append(f"{name}: renderer dependencies share a job with a publication secret")
    return found


def test_publication_secrets_never_share_a_job_with_python():
    doc = load()
    assert set(secret_jobs(doc)) == {"publish"}
    auditor = [s for s in doc["jobs"]["permit-feed"]["steps"]
               if "PARCEL_AUDIT_DISPATCH_TOKEN" in str(s)]
    assert len(auditor) == 1 and dormant(auditor[0], doc)
    assert violations(doc) == []


def test_refresh_token_only_in_the_isolated_publish_job():
    doc = load()
    holders = [(job, step.get("name")) for job, body in doc["jobs"].items()
               for step in body.get("steps", [])
               if "REFRESH_DISPATCH_TOKEN" in str(step)]
    assert holders == [("publish", "Publish changes as a PR for review")]
    renderer = doc["jobs"]["permit-feed"]
    assert "REFRESH_DISPATCH_TOKEN" not in str(renderer)
    assert "-r requirements.txt" in "\n".join(s.get("run", "") for s in renderer["steps"])


def test_publish_job_is_fresh_least_privilege_and_verifies_before_the_token():
    job = load()["jobs"]["publish"]
    assert job["needs"] == "permit-feed"
    assert "needs.permit-feed.result == 'success'" in job["if"]
    assert "needs.permit-feed.outputs.changed == 'true'" in job["if"]
    assert job["permissions"] == {"contents": "read", "actions": "read"}
    steps = job["steps"]
    checkout = steps[0]
    assert "actions/checkout@" in checkout["uses"]
    assert checkout["with"]["persist-credentials"] is False
    names = [s.get("name", s.get("uses")) for s in steps]
    verify = names.index("Verify publication bundle (fail closed, no token)")
    publish = names.index("Publish changes as a PR for review")
    assert verify < publish == len(steps) - 1
    assert "verify_publication_bundle.sh" in steps[verify]["run"]
    assert "env" not in steps[verify]  # no token while untrusted input is checked
    assert steps[publish]["env"]["TIP"] == "${{ steps.verify.outputs.tip }}"
    # Only git and gh from the runner image; no action can run dependency code.
    assert [s["uses"].split("@")[0] for s in steps if "uses" in s] == ["actions/checkout"]


def test_renderer_job_hands_over_only_a_bundle():
    doc = load()
    steps = doc["jobs"]["permit-feed"]["steps"]
    prepare = next(s for s in steps if s.get("id") == "publish")
    assert "env" not in prepare
    assert "gh auth" not in prepare["run"] and "git push" not in prepare["run"]
    assert "git bundle create" in prepare["run"]
    upload = next(s for s in steps if "actions/upload-artifact@" in s.get("uses", ""))
    assert upload["with"]["path"].endswith("/publication/publication.bundle")
    assert doc["jobs"]["permit-feed"]["outputs"]["changed"] == "${{ steps.publish.outputs.changed }}"


@pytest.mark.parametrize("mutation", [
    # Re-adding Python to the token job.
    ("          git push -u origin \"$BRANCH\"\n",
     "          python3 scripts/build_site_index.py\n          git push -u origin \"$BRANCH\"\n"),
    # Moving the token back into the renderer job.
    ("        id: publish\n",
     "        id: publish\n        env:\n          GH_TOKEN: ${{ secrets.REFRESH_DISPATCH_TOKEN }}\n"),
    # Installing dependencies in the token job.
    ("      - name: Download publication bundle\n",
     ("      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0\n"
      "      - name: Download publication bundle\n")),
    # Waking the dormant auditor dispatch in the renderer job.
    ("          echo \"changed=true\" >> \"$GITHUB_OUTPUT\"\n",
     "          echo \"changed=true\" >> \"$GITHUB_OUTPUT\"\n          echo \"merged=true\" >> \"$GITHUB_OUTPUT\"\n"),
    # Workflow-wide secret env.
    ("permissions:\n  contents: read\n",
     "env:\n  GH_TOKEN: ${{ secrets.REFRESH_DISPATCH_TOKEN }}\n\npermissions:\n  contents: read\n"),
])
def test_mutations_that_expose_the_token_are_caught(mutation):
    old, new = mutation
    text = WORKFLOW.read_text()
    assert text.count(old) == 1
    assert violations(load(text.replace(old, new))) != []


# ---- bundle verification against synthetic repositories -------------------

def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def repos(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git unavailable")
    origin = tmp_path / "origin"
    origin.mkdir()
    env = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    git(origin, "init", "-q", "-b", "main")
    (origin / "data").mkdir()
    (origin / "data/permit_requests.json").write_text("{}\n")
    (origin / "scripts").mkdir()
    (origin / "scripts/x.py").write_text("print(1)\n")
    git(origin, "add", "-A")
    git(origin, *env, "commit", "-q", "-m", "base")
    renderer = tmp_path / "renderer"
    git(tmp_path, "clone", "-q", str(origin), str(renderer))
    publisher = tmp_path / "publisher"
    git(tmp_path, "clone", "-q", str(origin), str(publisher))

    def bundle(change, extra_commit=False, from_ref="origin/main"):
        git(renderer, "checkout", "-q", "-B", "work", from_ref)
        change(renderer)
        git(renderer, "add", "-A")
        git(renderer, *env, "commit", "-q", "-m", "batch")
        if extra_commit:
            (renderer / "data/second.json").write_text("{}\n")
            git(renderer, "add", "-A")
            git(renderer, *env, "commit", "-q", "-m", "second")
        out = tmp_path / "publication.bundle"
        git(renderer, "bundle", "create", str(out), f"{from_ref}..HEAD")
        return out

    def verify(path):
        return subprocess.run(["bash", str(VERIFY), str(path), "origin/main"],
                              cwd=publisher, capture_output=True, text=True, check=False)

    return bundle, verify, renderer, publisher, env


def write(rel, text="{}\n"):
    def change(repo):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    return change


@pytest.mark.parametrize("rel", ["data/permit_requests.json", "docs/index.json",
                                 "docs/badge/parcel-1-2.json", "docs/permits.html",
                                 "docs/permits-default.html", "docs/permit-ids.json",
                                 "docs/permit-points.json"])
def test_generated_data_commit_is_accepted(repos, rel):
    bundle, verify, renderer, *_ = repos
    result = verify(bundle(write(rel, '{"n": 1}\n')))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == git(renderer, "rev-parse", "HEAD")


def symlink(repo):
    (repo / "data/link.json").symlink_to("../scripts/x.py")


def executable(repo):
    path = repo / "data/run.sh"
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)


@pytest.mark.parametrize("change,reason", [
    (write("scripts/x.py", "print(2)\n"), "outside the publication allowlist"),
    (write(".github/workflows/ci.yml", "on: push\n"), "outside the publication allowlist"),
    (write("docs/index.html", "<p>\n"), "outside the publication allowlist"),
    (write("docs/badge/x/parcel-1.json"), "outside the publication allowlist"),
    (symlink, "disallowed file mode 120000"),
    (executable, "disallowed file mode 100755"),
])
def test_disallowed_changes_are_rejected(repos, change, reason):
    bundle, verify, *_ = repos
    result = verify(bundle(change))
    assert result.returncode != 0
    assert reason in result.stderr
    assert result.stdout == ""


def test_more_than_one_commit_is_rejected(repos):
    bundle, verify, *_ = repos
    result = verify(bundle(write("data/a.json"), extra_commit=True))
    assert result.returncode != 0
    assert "does not verify" in result.stderr or "exactly one parent" in result.stderr \
        or "parent is not on" in result.stderr


def test_parent_off_main_is_rejected(repos):
    bundle, verify, renderer, publisher, env = repos
    # A side commit the publisher also has, but which is not on its main.
    git(renderer, "checkout", "-q", "-b", "side", "origin/main")
    (renderer / "data/side.json").write_text("{}\n")
    git(renderer, "add", "-A")
    git(renderer, *env, "commit", "-q", "-m", "side")
    git(publisher, "fetch", "-q", str(renderer), "side:refs/remotes/side")
    result = verify(bundle(write("data/a.json"), from_ref="side"))
    assert result.returncode != 0
    assert "parent is not on origin/main" in result.stderr


def test_missing_or_garbage_bundle_is_rejected(repos, tmp_path):
    _, verify, *_ = repos
    assert "missing bundle" in verify(tmp_path / "nope.bundle").stderr
    junk = tmp_path / "junk.bundle"
    junk.write_text("not a bundle\n")
    result = verify(junk)
    assert result.returncode != 0 and "does not verify" in result.stderr


def test_merge_commit_is_rejected(repos, tmp_path):
    _, verify, renderer, _, env = repos
    git(renderer, "checkout", "-q", "-B", "side2", "origin/main")
    (renderer / "scripts/x.py").write_text("print(3)\n")  # code hidden in a side parent
    git(renderer, "add", "-A")
    git(renderer, *env, "commit", "-q", "-m", "side")
    git(renderer, "checkout", "-q", "-B", "work2", "origin/main")
    (renderer / "data/a.json").write_text("{}\n")
    git(renderer, "add", "-A")
    git(renderer, *env, "commit", "-q", "-m", "data")
    git(renderer, *env, "merge", "-q", "--no-ff", "-m", "merge", "side2")
    out = tmp_path / "merge.bundle"
    git(renderer, "bundle", "create", str(out), "origin/main..HEAD")
    result = verify(out)
    assert result.returncode != 0
    assert "exactly one parent" in result.stderr
