import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


land = load('scripts/land_feed.py', 'land_feed_t')
l2tp = load('scripts/vpn/l2tp.py', 'l2tp_t')
watch = load('scripts/vpn/vpn_watch.py', 'vpn_watch_t')
pub = load('scripts/ci/publish_badges.py', 'pub_t')
pb = load('scripts/parcel_badges.py', 'pb_t')


def test_land_status_date_parsing():
    assert land.parse_status_date(' 21/08/26') == '2026-08-21'
    assert land.parse_status_date('01/02/2025') == '2025-02-01'
    for bad in ('', None, '31/02/26', 'x'):
        assert land.parse_status_date(bad) == ''


def _fake_run(stdout):
    return lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=stdout)


def test_land_query_prefers_exact_plan_and_handles_bad_json(monkeypatch):
    body = json.dumps({'plansSmall': [{'planNumber': 'x'}, {'planNumber': 'y', 'status': 's'}]})
    monkeypatch.setattr(land.subprocess, 'run', _fake_run(body))
    assert land.query_plan('y')['status'] == 's'
    assert land.query_plan('zzz')['planNumber'] == 'x'
    monkeypatch.setattr(land.subprocess, 'run', _fake_run('{"plansSmall": []}'))
    assert land.query_plan('y') == {}
    monkeypatch.setattr(land.subprocess, 'run', _fake_run('<html>'))
    assert land.query_plan('y') is None


def test_land_main_writes_deposit_flag_and_aborts_on_repeated_failures(monkeypatch, tmp_path):
    data = tmp_path / 'd.json'
    data.write_text(json.dumps({'rows': [{'pl_number': 'A'}, {'pl_number': 'B'}, {}]}))
    out = tmp_path / 'o.json'
    monkeypatch.setattr(land.time, 'sleep', lambda s: None)
    answers = {'A': {'status': 'הפקדה להתנגדויות', 'statusDate': '01/01/26', 'planId': 7, 'cityText': 'c'}, 'B': {}}
    monkeypatch.setattr(land, 'query_plan', lambda n: answers[n])
    monkeypatch.setattr(land.sys, 'argv', ['x', '--data-json', str(data), '--tracked', str(tmp_path / 'none'), '--out', str(out)])
    assert land.main() == 0
    plans = json.loads(out.read_text())['plans']
    assert list(plans) == ['A'] and plans['A']['is_deposit_publication'] is True
    assert plans['A']['land_status_date'] == '2026-01-01'
    data.write_text(json.dumps({'rows': [{'pl_number': str(i)} for i in range(6)]}))
    monkeypatch.setattr(land, 'query_plan', lambda n: None)
    out.unlink()
    assert land.main() == 1 and not out.exists()


def test_l2tp_negotiation_summary_is_categories_only():
    text = ('generating ID_PROT request 0\nreceived NO_PROPOSAL_CHOSEN notify\nretransmit 1\n'
            'peer not responding to 203.0.113.9')
    s = l2tp.summarize_negotiation(text)
    assert 'proposal_mismatch' in s['classes'] and 'peer_no_proposal_notification' in s['classes']
    assert s['retransmit_count'] == 1 and s['peer_reply_observed'] is True
    assert '203.0.113.9' not in json.dumps(s)
    silent = l2tp.summarize_negotiation('generating QUICK_MODE request 1')
    assert silent['request_without_observed_response'] == ['QUICK_MODE']


def test_l2tp_sa_state_requires_both_ike_and_transport():
    both = 'mavat-l2tp[1]: ESTABLISHED 1s\nmavat-l2tp{2}:  INSTALLED, TRANSPORT'
    assert all(l2tp.established_snapshot(both).values())
    assert not all(l2tp.established_snapshot('mavat-l2tp[1]: ESTABLISHED').values())


def test_l2tp_credential_and_server_validation():
    assert l2tp.quote('a"b\\c') == '"a\\"b\\\\c"'
    for bad in ('', 'caf\u00e9', 'a\nb'):
        with pytest.raises(l2tp.TunnelError):
            l2tp.quote(bad)
    env = {'VPN_L2TP_SERVER': 'vpn.example.invalid', 'VPN_L2TP_PSK': 'k', 'VPN_L2TP_USERNAME': 'u', 'VPN_L2TP_PASSWORD': 'p'}
    assert l2tp.settings(env)[0] == 'vpn.example.invalid'
    for server in ('https://x', '', '-x'):
        with pytest.raises(l2tp.TunnelError):
            l2tp.settings({**env, 'VPN_L2TP_SERVER': server})


def test_l2tp_configs_embed_inputs_and_force_safe_options():
    c = l2tp.configs('192.0.2.1', '"k"', '"u"', '"p"')
    assert 'right=192.0.2.1' in c['ipsec.conf'] and 'authby=psk' in c['ipsec.conf']
    assert c['ipsec.secrets'] == ': PSK "k"\n'
    assert 'require-mschap-v2' in c['ppp-options'] and 'nodefaultroute' in c['ppp-options']
    assert 'lns = 192.0.2.1' in c['xl2tpd.conf']


def test_l2tp_failure_labels_never_leak_detail():
    assert l2tp.safe_failure(subprocess.TimeoutExpired('x', 1)) == 'command_timeout'
    assert l2tp.safe_failure(l2tp.TunnelError('command_exit_3')) == 'command_exit_3'
    assert l2tp.safe_failure(l2tp.TunnelError('secret detail')) == 'stage_validation_failed'
    assert l2tp.safe_failure(OSError(13, 'x')) == 'os_error_13'
    assert l2tp.safe_failure(ValueError('x')) == 'unexpected_error'


def test_l2tp_bounded_attempts_and_down_without_state(monkeypatch):
    with pytest.raises(l2tp.TunnelError):
        l2tp.connect_bounded({}, attempts=2)
    monkeypatch.setattr(l2tp, 'ROOT', Path('/nonexistent-root-for-test'))
    l2tp.down()


def test_l2tp_connect_retries_then_gives_up(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(l2tp, 'up', lambda env: calls.append(1) or (_ for _ in ()).throw(l2tp.TunnelError('x')))
    monkeypatch.setattr(l2tp, 'down', lambda: None)
    monkeypatch.setattr(l2tp.time, 'sleep', lambda s: None)
    monkeypatch.setattr(l2tp, 'ROOT', Path('/nonexistent-root-for-test'))
    with pytest.raises(l2tp.TunnelError):
        l2tp.connect_bounded({}, attempts=3)
    assert len(calls) == 3
    assert 'vpn_failed' in capsys.readouterr().out


def test_watch_ppp_and_probe_reports(monkeypatch):
    monkeypatch.setattr(watch, '_run', lambda *c: '')
    assert 'DOWN' in watch._ppp()
    monkeypatch.setattr(watch, '_run', lambda *c: '3: ppp43: state UP\n    100 5 0 0 0 0\n    200 6 0 0 0 0\n')
    assert 'UP' in watch._ppp()

    def boom(*a, **k):
        raise OSError('no route')
    monkeypatch.setattr(watch.socket, 'create_connection', boom)
    assert 'FAIL OSError' in watch._probe()


def test_watch_run_swallows_command_errors(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError('x')
    monkeypatch.setattr(watch.subprocess, 'run', boom)
    assert watch._run('ipsec') == '<FileNotFoundError>'


def test_go_badge_metrics_and_failure_modes():
    events = '\n'.join(json.dumps(e) for e in [{'Test': 'A', 'Action': 'pass'}, {'Test': 'B', 'Action': 'skip'}])
    r = pub.metrics('go', events, 'total: 81.5%')
    assert r['tests']['message'] == '1 passed, 1 skipped' and r['coverage']['message'] == '81.5%'
    with pytest.raises(ValueError):
        pub.metrics('go', events, 'no coverage here')
    with pytest.raises(ValueError):
        pub.metrics('go', json.dumps({'Test': 'A', 'Action': 'fail'}), '80%')
    with pytest.raises(ValueError):
        pub.metrics('go', '', '80%')


def test_progress_badges_written_from_public_files(tmp_path):
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/ginot_hair_parcels.geojson').write_text(json.dumps(
        {'features': [{'properties': {'gush': 1, 'helka': h}} for h in (1, 2, 3, 4)]}))
    (tmp_path / 'data/permit_requests.json').write_text(json.dumps({'batch': {'offset': 0, 'limit': 1}}))
    pb.build_badges(tmp_path)
    prog = json.loads((tmp_path / 'docs/badge/parcel-progress.json').read_text())
    rem = json.loads((tmp_path / 'docs/badge/parcel-remaining.json').read_text())
    assert prog['message'] == '1/4 (25.0%)' and rem['message'] == '3'
