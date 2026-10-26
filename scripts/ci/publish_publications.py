"""Publish only the two watch data files through a checked, text-only PR."""
import json
import os
import subprocess
import time
from pathlib import Path

EXPECTED_CHECKS = {'test (3.11)', 'test (3.12)', 'test (3.13)', 'Analyze (actions)',
                   'Analyze (python)', 'worker', 'site-browser (chromium)',
                   'site-browser (webkit)', 'CodeQL'}


def checks_pass(checks):
    names = {c.get('name') for c in checks}
    return EXPECTED_CHECKS <= names and all(
        (c.get('state') == 'SUCCESS' if c.get('__typename') == 'StatusContext'
         else c.get('conclusion') in ('SUCCESS', 'NEUTRAL', 'SKIPPED'))
        for c in checks)


FILES = ('data/publications_active.json', 'data/publications_new_latest.json')


def gh(*args, payload=None):
    cmd = ['gh', *args]
    if payload is not None:
        cmd += ['--input', '-']
    result = subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, check=True)
    if not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    root = f'repos/{repo}'
    base = gh('api', f'{root}/git/ref/heads/main')['object']['sha']
    tree = gh('api', f'{root}/git/commits/{base}')['tree']['sha']
    entries = [{'path': path, 'mode': '100644', 'type': 'blob',
                'content': Path(path).read_text(encoding='utf-8')} for path in FILES]
    updated = gh('api', f'{root}/git/trees', payload={'base_tree': tree, 'tree': entries})
    if updated['sha'] == tree:
        print('no publication changes')
        return
    commit = gh('api', f'{root}/git/commits', payload={
        'message': 'Daily publication baseline refresh (refs #527)',
        'tree': updated['sha'], 'parents': [base]})
    branch = 'publications/' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    gh('api', f'{root}/git/refs', payload={'ref': 'refs/heads/' + branch, 'sha': commit['sha']})
    pr = gh('api', f'{root}/pulls', payload={
        'title': 'Daily publications refresh', 'head': branch, 'base': 'main',
        'body': 'Automated public publication baseline and alert payload (refs #527). Text-only data update.'})
    print(pr['html_url'], flush=True)
    # Never merge an empty check set, pending checks, or a failed check.
    for _ in range(90):
        state = gh('pr', 'view', str(pr['number']), '--repo', repo,
                   '--json', 'headRefOid,statusCheckRollup')
        checks = state['statusCheckRollup']
        if checks_pass(checks):
            gh('pr', 'merge', str(pr['number']), '--repo', repo, '--squash', '--admin',
               '--match-head-commit', state['headRefOid'])
            return
        if any(c.get('conclusion') in ('FAILURE', 'CANCELLED', 'TIMED_OUT', 'ACTION_REQUIRED')
               or c.get('state') in ('FAILURE', 'ERROR') for c in checks):
            raise RuntimeError('Data PR has failed checks; left open for review')
        time.sleep(20)
    raise RuntimeError('Data PR checks did not settle; left open for review')


if __name__ == '__main__':
    main()
