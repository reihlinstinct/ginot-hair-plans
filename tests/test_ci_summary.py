import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('test_summary', ROOT / 'scripts/ci/test_summary.py')
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def test_summary_counts_nested_junit_without_double_counting(tmp_path):
    report = tmp_path / 'tests.xml'
    report.write_text('''<testsuites><testsuite tests="99"><testsuite>
    <testcase/><testcase><failure>token=privatevalue</failure></testcase>
    <testcase><error/></testcase><testcase><skipped/></testcase>
    </testsuite></testsuite></testsuites>''')
    coverage = tmp_path / 'coverage.json'
    coverage.write_text('{"totals":{"percent_covered":72.125}}')
    text = summary.render(report, coverage)
    assert '| 4 | 1 | 1 | 1 | 1 |' in text
    assert '72.12%' in text
    assert 'privatevalue' not in text


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


def test_per_test_lists_failure_skip_reasons_first_and_escapes_content(tmp_path):
    report = tmp_path / 'results.xml'
    report.write_text('''<testsuite>
      <testcase classname="checks" name="test_pass" time=".1"/>
      <testcase classname="checks" name="test_skip"><skipped message="collection skipped">optional browser unavailable</skipped></testcase>
      <testcase classname="checks" name="test_failure"><failure message="expected &lt;safe&gt;, got token=abc123"/></testcase>
    </testsuite>''')
    text = summary.render(report)
    assert text.index('<b>FAILED') < text.index('<b>SKIPPED') < text.index('<b>PASSED')
    assert 'optional browser unavailable' in text
    assert 'expected &lt;safe&gt;' in text and 'abc123' not in text
    assert 'Check: pass' in text and '<details>' in text


def test_diagnostic_redaction_and_length_limit():
    text = summary.safe('email a@example.invalid IP 192.0.2.1 password=foo github_pat_abcd')
    assert 'a@example.invalid' not in text and '192.0.2.1' not in text
    assert 'foo' not in text and 'github_pat_abcd' not in text
    assert '[truncated]' in summary.safe('x' * 1500)


def test_nested_detail_is_closed_and_has_source_assertions_and_honest_actual(tmp_path):
    report = tmp_path / 'results.xml'
    report.write_text('''<testsuite><testcase classname="tests.test_ci_summary"
      name="test_summary_missing_reports_are_unknown_not_zero"/></testsuite>''')
    text = summary.render(report)
    assert '<details><summary>Exact check:' in text
    assert '<details open' not in text
    assert 'Test counts unavailable' in text and 'assert ' in text
    assert 'passing assertion operands are not captured' in text
    assert 'Runner result: passed' in text
    assert 'tmp_path' in text


def test_skipped_detail_never_claims_assertions_ran(tmp_path):
    report = tmp_path / 'results.xml'
    report.write_text('<testsuite><testcase name="unknown"><skipped message="no browser"/></testcase></testsuite>')
    text = summary.render(report)
    assert 'not verified by this job' in text and 'Exact source unavailable' in text
    assert 'no browser' in text


def test_description_lookup_is_module_qualified():
    lookup = summary.descriptions()
    assert 'tests.test_ci_summary.test_summary_counts_nested_junit_without_double_counting' in lookup
    assert 'test_summary_counts_nested_junit_without_double_counting' not in lookup


def test_browser_skip_plain_reason_names_only_verified_replacement_job():
    text = summary.skip_explanation('tests.test_map_browser', "No module named 'playwright'")
    assert 'does not install Playwright' in text
    assert 'site-browser job' in text
    assert 'not a browser pass' in text
    other = summary.skip_explanation('tests.test_unknown', 'conditional skip')
    assert 'No alternative job is confirmed' in other
