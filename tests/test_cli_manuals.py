"""Public help/man contracts and offline entrypoint smoke tests (#720)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ginot.cli_spec import COMMANDS, man_page, parser_for

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = {
    "ginot-refresh": ["refresh.py"],
    "ginot-land-feed": ["scripts/land_feed.py"],
    "ginot-mcp-server": ["-m", "ginot.mcp_server"],
}


def run(*args):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("command", COMMANDS)
def test_real_entrypoint_help_without_data_or_network(command):
    # Invalid paths prove --help exits before opening data or making requests.
    flag = COMMANDS[command]["options"][0][0]
    result = run(*ENTRYPOINTS[command], flag, "/missing/cli-help-fixture", "--help")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert COMMANDS[command]["summary"] in result.stdout
    for option, default, description in COMMANDS[command]["options"]:
        assert option in result.stdout
        # argparse wraps help; compare normalized whitespace.
        text = " ".join(result.stdout.split())
        assert str(default) in text
        assert description in text


@pytest.mark.parametrize("command", COMMANDS)
def test_defaults_and_manual_share_argument_definitions(command):
    parser = parser_for(command)
    args = vars(parser.parse_args([]))
    expected = {
        flag[2:].replace("-", "_"): default
        for flag, default, _ in COMMANDS[command]["options"]
    }
    assert args == expected
    assert {action.option_strings[0] for action in parser._actions} == {
        "-h",
        *(flag for flag, _, _ in COMMANDS[command]["options"]),
    }
    assert (ROOT / "man" / "man1" / f"{command}.1").read_text() == man_page(command)


@pytest.mark.parametrize("command", COMMANDS)
def test_unknown_arguments_fail_without_work(command):
    result = run(*ENTRYPOINTS[command], "--not-a-supported-option")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_man_package_is_current():
    result = run("scripts/docs/man_pages.py", "--check")
    assert result.returncode == 0, result.stderr


def test_install_man_pages_under_custom_prefix(tmp_path):
    prefix = tmp_path / "prefix with spaces"
    result = run("scripts/docs/man_pages.py", "--install", str(prefix))
    assert result.returncode == 0, result.stderr
    target = prefix / "share" / "man" / "man1"
    assert {p.name for p in target.iterdir()} == {f"{c}.1" for c in COMMANDS}
    for command in COMMANDS:
        assert (target / f"{command}.1").read_text() == man_page(command)


def test_check_and_install_refuse_drift(tmp_path):
    # Exercise the packaging tool in an isolated miniature checkout.
    import shutil

    for relative in ("scripts/docs/man_pages.py", "src/ginot/cli_spec.py"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    tool = tmp_path / "scripts/docs/man_pages.py"

    def invoke(*args):
        return subprocess.run(
            [sys.executable, str(tool), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    assert invoke().returncode == 0
    page = tmp_path / "man/man1/ginot-refresh.1"
    page.write_text("stale manual\n")
    result = invoke("--check")
    assert result.returncode == 1
    assert "Manual drift" in result.stderr
    prefix = tmp_path / "install"
    assert invoke("--install", str(prefix)).returncode == 1
    assert not prefix.exists()
    assert invoke().returncode == 0
    assert invoke("--check").returncode == 0
    (page.parent / "unexpected.1").write_text("extra")
    assert invoke("--check").returncode == 1
