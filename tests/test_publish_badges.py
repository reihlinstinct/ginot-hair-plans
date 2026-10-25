"""Badge endpoint generation tests (issue #439): invalid metrics must raise."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "publish_badges", ROOT / "scripts/ci/publish_badges.py"
)
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)

JUNIT = """<testsuite><testcase classname="a" name="t1"/>
<testcase classname="a" name="t2"><skipped/></testcase>
<testcase classname="a" name="t3"/></testsuite>"""


def test_python_metrics_happy_path():
    cov = json.dumps({"totals": {"percent_covered": 81.234}})
    out = pb.metrics("python", JUNIT, cov)
    assert out["tests"]["message"] == "2 passed, 1 skipped"
    assert out["coverage"]["message"] == "81.2%"
    assert out["tests"]["schemaVersion"] == 1


def test_python_metrics_rejects_failing_and_empty():
    cov = json.dumps({"totals": {"percent_covered": 50}})
    with pytest.raises(ValueError):
        pb.metrics("python", "<testsuite/>", cov)
    failing = '<testsuite><testcase name="x"><failure/></testcase></testsuite>'
    with pytest.raises(ValueError):
        pb.metrics("python", failing, cov)
    with pytest.raises(ValueError):
        pb.metrics("python", JUNIT, json.dumps({"totals": {"percent_covered": 140}}))


def test_go_metrics_from_json_lines():
    lines = "\n".join([
        json.dumps({"Action": "pass", "Test": "TestA"}),
        json.dumps({"Action": "skip", "Test": "TestB"}),
        json.dumps({"Action": "pass", "Test": "TestA"}),  # duplicate keeps last state
        json.dumps({"Action": "output", "Test": "TestC"}),  # ignored action
    ])
    out = pb.metrics("go", lines, "coverage: 72.5% of statements")
    assert out["tests"]["label"] == "Go suite"
    assert out["tests"]["message"] == "1 passed, 1 skipped"
    assert out["coverage"]["message"] == "72.5%"


def test_go_metrics_missing_coverage_raises():
    with pytest.raises(ValueError, match="Missing measured coverage"):
        pb.metrics("go", '{"Action":"pass","Test":"T"}', "no percentage here")


def test_main_writes_badge_files(tmp_path):
    import subprocess
    import sys

    res = tmp_path / "r.xml"
    res.write_text(JUNIT)
    cov = tmp_path / "c.json"
    cov.write_text(json.dumps({"totals": {"percent_covered": 90}}))
    outdir = tmp_path / "badges"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/publish_badges.py"),
         "python", str(res), str(cov), str(outdir)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    tests_badge = json.loads((outdir / "tests.json").read_text())
    coverage_badge = json.loads((outdir / "coverage.json").read_text())
    assert tests_badge["color"] == "brightgreen"
    assert coverage_badge["message"] == "90.0%"
