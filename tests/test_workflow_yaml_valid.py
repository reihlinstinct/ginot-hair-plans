"""#631: every workflow file must stay parseable YAML.

Regression: an inline `run: pip ... --only-binary=:all: ...` step put a
colon-space inside an unquoted YAML scalar (such commands belong in a block
scalar or quoted string). GitHub tolerated it once; a parse guard makes the
next one fail CI instead of silently misreading the workflow.
"""

from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted(
    Path(__file__).parent.parent.glob(".github/workflows/*.yml")
) + sorted(Path(__file__).parent.parent.glob(".github/workflows/*.yaml"))


def test_workflow_files_exist():
    assert WORKFLOWS, "no workflow files found - the glob itself must be broken"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_is_parseable_yaml(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), f"{path.name}: top level must be a mapping"
    assert isinstance(doc.get("jobs"), dict), f"{path.name}: jobs section missing or not a mapping - misparsed?"
