"""Generate minimal public badge endpoints from successful CI result files."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def badge(label, message, color='blue'):
    return {'schemaVersion': 1, 'label': label, 'message': str(message), 'color': color}


def metrics(kind, result, coverage):
    if kind == 'python':
        suites = ET.fromstring(result)
        cases = list(suites.iter('testcase'))
        passed = sum(not any(c.tag in ('failure', 'error', 'skipped') for c in case) for case in cases)
        skipped = sum(any(c.tag == 'skipped' for c in case) for case in cases)
        pct = float(json.loads(coverage)['totals']['percent_covered'])
        label = 'Python suite'
    else:
        states = {}
        for line in result.splitlines():
            e = json.loads(line)
            if e.get('Test') and e.get('Action') in ('pass', 'fail', 'skip'):
                states[e['Test']] = e['Action']
        passed = list(states.values()).count('pass')
        skipped = list(states.values()).count('skip')
        cases = states
        matches = re.findall(r'([0-9.]+)%', coverage)
        if not matches:
            raise ValueError('Missing measured coverage')
        pct = float(matches[-1])
        label = 'Go suite'
    if not cases or passed + skipped != len(cases) or not 0 <= pct <= 100:
        raise ValueError('Empty, failing or invalid CI metrics')
    return {'tests': badge(label, f'{passed} passed, {skipped} skipped', 'brightgreen'),
            'coverage': badge('test coverage', f'{pct:.1f}%', 'blue')}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('kind', choices=['python', 'go'])
    p.add_argument('results')
    p.add_argument('coverage')
    p.add_argument('out')
    a = p.parse_args()
    values = metrics(a.kind, Path(a.results).read_text(), Path(a.coverage).read_text())
    Path(a.out).mkdir(parents=True, exist_ok=True)
    for name, value in values.items():
        Path(a.out, name + '.json').write_text(json.dumps(value) + '\n')
