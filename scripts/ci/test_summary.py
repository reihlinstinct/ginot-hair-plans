#!/usr/bin/env python3
"""Append lightweight JUnit/coverage totals to a GitHub job summary."""
import argparse
import ast
import html
import re
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET


def safe(text, limit=1200):
    """Escape markup and remove common credential/contact literals from diagnostics."""
    text = re.sub(r'(?i)(token|password|secret|authorization|api[_-]?key)\s*[:=]\s*\S+',
                  r'\1=[redacted]', str(text))
    text = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b', '[redacted]', text)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email redacted]', text)
    text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[IP redacted]', text)
    if len(text) > limit:
        text = text[:limit] + ' [truncated]'
    return html.escape(text)


def descriptions():
    """Index exact checked-in Python test/fixture source, qualified by module."""
    found = {}
    for path in Path('tests').glob('test_*.py'):
        try:
            source = path.read_text()
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        functions = {n.name: n for n in tree.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        module = '.'.join(path.with_suffix('').parts)
        for name, node in functions.items():
            if not name.startswith('test_'):
                continue
            doc = ast.get_docstring(node) or ''
            code = ast.get_source_segment(source, node) or ''
            decorators = [ast.get_source_segment(source, d) or '' for d in node.decorator_list]
            fixtures = [arg.arg for arg in node.args.args]
            local = [(n, ast.get_source_segment(source, functions[n]) or '')
                     for n in fixtures if n in functions]
            checks = [ast.get_source_segment(source, n) or '' for n in ast.walk(node)
                      if isinstance(n, ast.Assert)]
            found[module + '.' + name] = {
                'description': doc.splitlines()[0] if doc else '',
                'source': '\n'.join('@' + d for d in decorators) + '\n' + code,
                'fixtures': fixtures, 'local': local, 'checks': checks,
            }
    # The worker has a small fixed test module. Keep its exact checked-in
    # setup/assertions available; do not infer runtime values from JavaScript.
    for path in Path('worker').glob('*.test.mjs'):
        text = path.read_text()
        for match in re.finditer(r'test\("([^"\n]+)"', text):
            found[match[1]] = {'description': match[1], 'source': text,
                             'fixtures': [], 'local': [], 'checks': []}
    return found


def skip_explanation(name, detail):
    """Only name a replacement job when its checked-in workflow verifies it."""
    browser_modules = ('tests.test_site_browser', 'tests.test_map_browser')
    workflow = Path('.github/workflows/ci.yml')
    config = workflow.read_text() if workflow.exists() else ''
    if (any(name.startswith(module) for module in browser_modules)
            and "No module named 'playwright'" in detail
            and 'pip install -r requirements.txt playwright' in config
            and 'tests/test_site_browser.py tests/test_map_browser.py' in config):
        return ('This Python job does not install Playwright, so browser test modules '
                'are skipped here. They run instead in the separate site-browser job '
                'in this CI run, where Playwright and Chromium are installed. '
                'Check that job for their individual results; this skip is not a browser pass.')
    if 'browser binary' in detail.lower() or 'executable doesn' in detail.lower():
        return ('The browser runtime required by this test is unavailable in this job. '
                'The runner reason is shown below. No alternative successful execution '
                'is verified from this report.')
    return ('The test runner marked this entry skipped, so its checks were not executed here. '
            'The reported condition is shown below. No alternative job is confirmed '
            'for this entry; the reason is not being inferred.')


def check_detail(info, state, detail, name):
    lines = ['', '<details><summary>Exact check: inputs, steps, assertions and result</summary>', '']
    lines += ['<p>Inputs and expected values below are the checked-in test definition, '
              'not a capture of private runtime objects. Runtime values are shown only '
              'when supplied by the failure report; passing assertion operands are not captured.</p>']
    if state == 'PASSED':
        result = 'Runner result: passed. Assertions reached by this execution did not fail; '
        result += 'this does not prove every conditional branch executed.'
    elif state == 'SKIPPED':
        result = 'Runner result: skipped. Test body/assertions were not verified by this job.'
    else:
        result = 'Runner result: ' + state.lower() + '. Available expected/actual diagnostic follows.'
    lines.append('<p>' + safe(result) + '</p>')
    if state == 'SKIPPED':
        lines.append('<p>' + safe(skip_explanation(name, detail)) + '</p>')
    if detail:
        lines.append('<pre>' + safe(detail, 6000) + '</pre>')
    if not info:
        lines += ['<p>Exact source unavailable for this runner entry (for example module collection skip). '
                  'No steps, inputs or expected/actual values have been invented.</p>', '</details>', '']
        return lines
    lines += ['<p>Fixture/parameter inputs: ' + safe(', '.join(info['fixtures']) or 'defined in source') +
              '. Built-in/shared fixture implementations are not expanded here.</p>',
              '<p>Exact setup, calls, parameter cases and assertions:</p>',
              '<pre>' + safe(info['source'], 12000) + '</pre>']
    for name, source in info['local']:
        lines += ['<p>Local input fixture: ' + safe(name) + '</p>',
                  '<pre>' + safe(source, 6000) + '</pre>']
    lines += ['</details>', '']
    return lines


def per_test(cases):
    docs = descriptions()
    records = []
    for case in cases:
        state, detail = 'PASSED', ''
        priority = 2
        for tag, label, rank in [('error', 'ERROR', 0), ('failure', 'FAILED', 0),
                                 ('skipped', 'SKIPPED', 1)]:
            element = case.find(tag)
            if element is not None:
                state, priority = label, rank
                detail = '\n'.join(dict.fromkeys(part.strip() for part in
                    (element.get('message', ''), element.text or '') if part.strip()))
                detail = detail or 'No reason supplied by test runner.'
                break
        name = case.get('name', '(unnamed)')
        qualified = '.'.join(filter(None, [case.get('classname'), name]))
        info = docs.get(qualified.split('[')[0]) or docs.get(name)
        description = (info or {}).get('description')
        description = description or name.replace('test_', '', 1).replace('_', ' ')
        records.append((priority, qualified, state, detail, description, case.get('time', 'n/a'), info))
    lines = ['', '<details><summary>Per-test results (failed/errors, skipped, passed)</summary>', '',
             'What was checked: checked-in docstring where available; otherwise the test name.', '']
    for _, name, state, detail, description, duration, info in sorted(records, key=lambda r: r[:2]):
        lines += [f'- <b>{state}</b> <code>{safe(name)}</code> ({safe(duration)}s)',
                  f'  <br>Check: {safe(description)}']
        lines.extend(check_detail(info, state, detail, name))
    lines += ['', '</details>', '']
    return lines


def render(junit, coverage=None, title='Test results'):
    lines = [f'## {title}', '']
    cases = []
    try:
        root = ET.parse(junit).getroot()
        cases = list(root.iter('testcase'))
        failed = sum(case.find('failure') is not None for case in cases)
        errors = sum(case.find('error') is not None for case in cases)
        skipped = sum(case.find('skipped') is not None for case in cases)
        total = len(cases)
        lines += ['| Tests | Passed | Failed | Errors | Skipped |',
                  '| ---: | ---: | ---: | ---: | ---: |',
                  f'| {total} | {total-failed-errors-skipped} | {failed} | {errors} | {skipped} |', '']
    except (OSError, ET.ParseError):
        lines += ['Test counts unavailable: report missing or invalid (tests may not have started).', '']
    if coverage:
        try:
            pct = json.loads(Path(coverage).read_text())['totals']['percent_covered']
            lines.append(f'Coverage: {pct:.2f}% (Python unit/integration scope).')
        except (OSError, ValueError, KeyError, TypeError):
            lines.append('Coverage unavailable: report missing or invalid.')
    else:
        lines.append('Coverage: not measured in this job; see Python test jobs.')
    if cases:
        lines.extend(per_test(cases))
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--junit', required=True)
    parser.add_argument('--coverage')
    parser.add_argument('--title', default='Test results')
    args = parser.parse_args()
    text = render(args.junit, args.coverage, args.title)
    target = os.environ.get('GITHUB_STEP_SUMMARY')
    if target:
        with open(target, 'a') as summary:
            summary.write(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
