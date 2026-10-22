import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('test_summary', ROOT / 'scripts/ci/test_summary.py')
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def test_summary_counts_nested_junit_without_double_counting(tmp_path):
    report = tmp_path / 'tests.xml'
    report.write_text('''<testsuites><testsuite tests="99"><testsuite>
    <testcase/><testcase><failure>private failure text</failure></testcase>
    <testcase><error/></testcase><testcase><skipped/></testcase>
    </testsuite></testsuite></testsuites>''')
    coverage = tmp_path / 'coverage.json'
    coverage.write_text('{"totals":{"percent_covered":72.125}}')
    text = summary.render(report, coverage)
    assert '| 4 | 1 | 1 | 1 | 1 |' in text
    assert '72.12%' in text
    assert 'private failure text' not in text


def test_summary_missing_reports_are_unknown_not_zero(tmp_path):
    text = summary.render(tmp_path / 'none', tmp_path / 'none')
    assert 'Test counts unavailable' in text and 'Coverage unavailable' in text
    assert '| 0 |' not in text


def test_summary_invalid_reports_and_unmeasured_coverage(tmp_path):
    report = tmp_path / 'broken'
    report.write_text('<broken')
    assert 'Test counts unavailable' in summary.render(report)
    report.write_text('<testsuite><testcase/></testsuite>')
    assert '| 1 | 1 | 0 | 0 | 0 |' in summary.render(report)
    assert 'not measured' in summary.render(report)


def test_every_ci_test_job_has_always_summary_and_report():
    text = (ROOT / '.github/workflows/ci.yml').read_text()
    assert text.count('name: Test run summary') == 3
    assert text.count('if: ${{ always() }}') == 3
    assert '--junitxml=test-results.xml' in text
    assert '--junitxml=browser-results.xml' in text
    assert '--test-reporter=junit' in text
