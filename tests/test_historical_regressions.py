"""Historical workflow/parser incidents. All commands and source calls are mocked."""
import importlib.util
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def workflow(name):
    return (ROOT / '.github/workflows' / name).read_text()


@pytest.mark.parametrize('name', ['weekly-refresh.yml', 'permit-feed.yml', 'mavat-watch.yml', 'mirror-ingest.yml'])
@pytest.mark.parametrize('state,ok', [('CLEAN', True), ('DIRTY', False), ('BLOCKED', False)])
def test_publish_wait_executes_clean_conflict_timeout_paths(tmp_path, name, state, ok):
    """#170/#187/#277: real shell must wait clean, reject conflicts/timeouts."""
    text = workflow(name)
    begin = text.index('          gh pr update-branch "$PR"')
    end = text.index('gh pr merge "$PR" --squash', begin)
    script = '\n'.join(line[10:] for line in text[begin:end].splitlines())
    assert '--jq .mergeStateStatus' in script and '--jq -r' not in script
    prelude = f'''set -euo pipefail
PR=123
gh() {{ if [ "$1 $2" = "pr view" ]; then echo {state}; fi; if [ "$1 $2" = "pr checks" ]; then printf 'ci\\tpending\\n'; fi; }}
sleep() {{ :; }}
'''
    result = subprocess.run(['bash', '-c', prelude + script], capture_output=True, text=True, check=False)
    assert (result.returncode == 0) == ok
    if state == 'BLOCKED':
        assert result.stdout.count('merge state:') == 90
        assert 'timed out' in result.stdout
    if state == 'DIRTY':
        assert 'PR has conflicts' in result.stdout


@pytest.mark.parametrize('name', ['permit-feed.yml', 'mirror-ingest.yml', 'mavat-watch.yml', 'weekly-refresh.yml'])
def test_publish_blocked_by_review_rule_proceeds_only_when_checks_green(tmp_path, name):
    """Runs 39755426256/39804643780/39897078238: BLOCKED by the required review, checks green -> admin merge."""
    text = workflow(name)
    begin = text.index('          gh pr update-branch "$PR"')
    end = text.index('gh pr merge "$PR" --squash', begin)
    script = '\n'.join(line[10:] for line in text[begin:end].splitlines())
    for checks, ok in (('ci\\tpass', True), ('ci\\tfail', False), ('ci\\tpending', False)):
        prelude = f'''set -euo pipefail
PR=123
gh() {{ if [ "$1 $2" = "pr view" ]; then echo BLOCKED; fi; if [ "$1 $2" = "pr checks" ]; then printf '{checks}\\n'; fi; }}
sleep() {{ :; }}
'''
        r = subprocess.run(['bash', '-c', prelude + script], capture_output=True, text=True, check=False)
        assert (r.returncode == 0) == ok, (checks, r.stdout)


@pytest.mark.parametrize('name', ['weekly-refresh.yml', 'permit-feed.yml', 'mavat-watch.yml', 'mirror-ingest.yml'])
def test_publish_poll_survives_ci_restart_near_miss(tmp_path, name):
    """Run 39900080019 (#380): update-branch restarts pull_request CI; checks
    pending past the old 45-poll budget then green must still merge."""
    text = workflow(name)
    begin = text.index('          gh pr update-branch "$PR"')
    end = text.index('gh pr merge "$PR" --squash', begin)
    script = '\n'.join(line[10:] for line in text[begin:end].splitlines())
    count = tmp_path / 'checks_calls'
    count.write_text('0')
    prelude = f'''set -euo pipefail
PR=123
gh() {{ if [ "$1 $2" = "pr view" ]; then echo BLOCKED; fi; if [ "$1 $2" = "pr checks" ]; then n=$(cat "{count}"); n=$((n+1)); echo "$n" > "{count}"; if [ "$n" -le 50 ]; then printf 'ci\\tpending\\n'; else printf 'ci\\tpass\\n'; fi; fi; }}
sleep() {{ :; }}
'''
    result = subprocess.run(['bash', '-c', prelude + script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout
    assert 'timed out' not in result.stdout


def test_refresh_mirror_fetches_lease_ref_before_force_push():
    """#227: force-with-lease must use a fresh tracking ref."""
    text = workflow('weekly-refresh.yml')
    fetch = text.index('git fetch origin mirror')
    push = text.index('git push origin origin/main:refs/heads/mirror --force-with-lease')
    assert fetch < push
    assert 'git push origin origin/main:refs/heads/mirror --force\n' not in text


def test_refresh_inline_tests_precede_merge_without_approval_gated_dispatch():
    """#85/#132: current refresh avoids the impossible self-approval path."""
    text = workflow('weekly-refresh.yml')
    assert text.index('python -m pytest -q') < text.index('gh pr merge')
    assert text.index('ruff check') < text.index('gh pr merge')
    assert 'gh workflow run ci.yml' not in text
    permit = workflow('permit-feed.yml')
    assert '--event workflow_dispatch --limit 1' in permit
    assert permit.index('/approve') < permit.index('gh run watch')


def test_refresh_timeout_and_bounded_scan_size():
    """#79/#147: long refresh and batch must not revert to known-small limits."""
    assert 'timeout-minutes: 120' in workflow('weekly-refresh.yml')
    assert 'timeout-minutes: 355' in workflow('permit-feed.yml')
    assert 'L=280' in workflow('permit-feed.yml')


def test_mavat_kill_switch_uses_valid_job_vars_context():
    """#44: env is invalid at jobs.<job>.if."""
    text = workflow('mavat-watch.yml')
    line = next(line for line in text.splitlines() if line.startswith('    if:'))
    assert 'vars.MAVAT_WATCH_ENABLED' in line and 'env.' not in line


def test_mavat_browser_install_launch_share_path_and_runner_user():
    """#59/#61: root installation and runner launch must agree on browser path."""
    text = workflow('mavat-watch.yml')
    assert text.count('PLAYWRIGHT_BROWSERS_PATH: /opt/ms-playwright') == 2
    assert 'sudo -E python3 -m playwright install --with-deps chromium' in text
    assert 'run: python3 scripts/vpn/mavat_check.py' in text
    assert 'run: sudo python3 scripts/vpn/mavat_check.py' not in text
    assert 'PYTHONUNBUFFERED: "1"' in text


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts/vpn' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_vpn_rekeys_before_default_one_hour_expiry():
    """#83: assert current preventive config, not unproved provider cancellation cause."""
    vpn = load('l2tp')
    config = vpn.configs('example.invalid', 'test', 'test', 'test')['ipsec.conf']
    assert 'rekey=yes' in config and 'rekey=no' not in config
    for key in ('ikelifetime', 'lifetime'):
        value = int(re.search(rf'^    {key}=(\d+)m$', config, re.MULTILINE)[1])
        assert value < 60
    assert 'rekeymargin=5m' in config
    assert 'scripts/vpn/vpn_watch.py' in workflow('permit-feed.yml')


def test_discovery_parses_content_type_with_spaces(monkeypatch, tmp_path):
    """#45: tabs, not whitespace, delimit curl status/type/length."""
    probe = load('mavat_discover')
    body = tmp_path / 'body'
    body.write_bytes(b'{"documents":[]}')
    def run(cmd, **kwargs):
        cmd[cmd.index('-o') + 1] = str(body)
        return subprocess.CompletedProcess(cmd, 0, '200\tapplication/json; charset=utf-8\t16', '')
    original = open
    def opened(path, *args, **kwargs):
        return original(body if str(path) == '/tmp/probe_body' else path, *args, **kwargs)
    monkeypatch.setattr(probe.subprocess, 'run', run)
    monkeypatch.setattr('builtins.open', opened)
    result = probe.probe('synthetic', 'https://example.invalid')
    assert result['http'] == '200'
    assert result['content_type'] == 'application/json'
    assert result['bytes'] == 16 and result['json_like']
