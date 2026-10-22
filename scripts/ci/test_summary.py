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
    """Only literal checked-in docstrings, never inferred claims of coverage."""
    found = {}
    for path in Path('tests').glob('test_*.py'):
        try:
            tree = ast.parse(path.read_text())
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if doc:
                    found[node.name] = doc.splitlines()[0]
    return found


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
        description = docs.get(name.split('[')[0])
        description = description or name.replace('test_', '', 1).replace('_', ' ')
        records.append((priority, qualified, state, detail, description, case.get('time', 'n/a')))
    lines = ['', '<details><summary>Per-test results (failed/errors, skipped, passed)</summary>', '',
             'What was checked: checked-in docstring where available; otherwise the test name.', '']
    for _, name, state, detail, description, duration in sorted(records):
        lines += [f'- <b>{state}</b> <code>{safe(name)}</code> ({safe(duration)}s)',
                  f'  <br>Check: {safe(description)}']
        if detail:
            lines.append(f'  <pre>{safe(detail)}</pre>')
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
