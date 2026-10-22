#!/usr/bin/env python3
"""Append lightweight JUnit/coverage totals to a GitHub job summary."""
import argparse
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET


def render(junit, coverage=None, title='Test results'):
    lines = [f'## {title}', '']
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
