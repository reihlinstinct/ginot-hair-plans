import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

def load(path):
    spec = importlib.util.spec_from_file_location('badges', ROOT / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_counter_deduplicates_and_clamps_final_range():
    m = load('scripts/parcel_badges.py')
    parcels = {'features': [{'properties': {'gush': 1, 'helka': h}} for h in [1, 1, 2]]}
    assert m.progress(parcels, {'batch': {'offset': 1, 'limit': 280}}) == (2, 2)
    with pytest.raises(ValueError):
        m.progress(parcels, {'batch': {'offset': 0, 'limit': 1}, 'checkpoint': True})


def test_badges_from_measured_success_not_hardcoded():
    m = load('scripts/ci/publish_badges.py')
    xml = '<testsuites><testsuite><testcase/><testcase><skipped/></testcase></testsuite></testsuites>'
    result = m.metrics('python', xml, json.dumps({'totals': {'percent_covered': 78.25}}))
    assert result['tests']['message'] == '1 passed, 1 skipped'
    assert result['coverage']['message'] == '78.2%'
    with pytest.raises(ValueError):
        m.metrics('python', '<testsuite><testcase><failure/></testcase></testsuite>', json.dumps({'totals': {'percent_covered': 1}}))
