"""Secret-scan guard (#1141): the gitleaks workflow stays read-only, quiet and
pinned, its allowlist stays narrow, and a runtime-built sentinel in a scratch
file is still reported by the shipped config without printing its value.

The sentinel is generated at test time from random characters, so no
credential-shaped string is ever committed."""

import re
import secrets
import shutil
import string
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "gitleaks.yml").read_text(encoding="utf-8")
CONFIG = (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
AUTOMERGE = (ROOT / ".github" / "workflows" / "data-automerge.yml").read_text(
    encoding="utf-8"
)


# Section: workflow settings


def test_workflow_is_read_only_and_quiet():
    assert re.search(r"^permissions:\s*\n\s+contents: read\s*$", WORKFLOW, re.MULTILINE)
    assert "persist-credentials: false" in WORKFLOW
    assert 'GITLEAKS_ENABLE_COMMENTS: "false"' in WORKFLOW
    assert 'GITLEAKS_ENABLE_UPLOAD_ARTIFACT: "false"' in WORKFLOW
    assert "GITLEAKS_LICENSE" not in WORKFLOW
    assert "pull_request_target" not in WORKFLOW


def test_runs_on_push_and_pull_request_with_the_repo_config():
    assert re.search(r"^on:\s*\n\s+push:\s*\n\s+pull_request:", WORKFLOW, re.MULTILINE)
    assert "GITLEAKS_CONFIG: .gitleaks.toml" in WORKFLOW


def test_gitleaks_check_is_known_to_data_automerge():
    assert "      - Gitleaks\n" in AUTOMERGE


# Section: allowlist stays narrow


def test_config_extends_defaults_and_allowlists_only_two_exact_test_files():
    assert "useDefault = true" in CONFIG
    paths = re.findall(r"paths = \['''([^']+)'''\]", CONFIG)
    assert sorted(paths) == [
        r"^tests/test_l2tp_safety_928\.py$",
        r"^tests/test_permit_archive_fetch\.py$",
    ]
    assert CONFIG.count('targetRules = ["generic-api-key"]') == 2
    assert "regexes" not in CONFIG and "stopwords" not in CONFIG


# Section: the shipped config still catches a runtime sentinel


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks not installed")
def test_sentinel_is_reported_without_its_value(tmp_path):
    alphabet = string.ascii_letters + string.digits
    value = "ghp_" + "".join(secrets.choice(alphabet) for _ in range(36))
    (tmp_path / "leak.txt").write_text(f'token = "{value}"\n', encoding="utf-8")
    result = subprocess.run(
        [
            "gitleaks",
            "detect",
            "--no-git",
            "--redact",
            "--no-banner",
            "--source",
            str(tmp_path),
            "--config",
            str(ROOT / ".gitleaks.toml"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert value not in result.stdout + result.stderr
