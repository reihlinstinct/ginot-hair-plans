"""Stage scoped public watch data for independent review; never self-merge."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ginot.publications import write_projection

FILES = ('data/publications_active.json', 'data/publications_new_latest.json',
         'docs/publications_active.json', 'docs/index.json')


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


def pending_publication_prs(repo):
    # Paginated same-repo heads only. API/JSON errors propagate: fail closed.
    prs = gh('api', '--paginate', '--slurp',
             f'repos/{repo}/pulls?state=open&base=main&per_page=100')
    if not isinstance(prs, list) or any(not isinstance(page, list) for page in prs):
        raise RuntimeError('Invalid pending PR response')
    return [pr['number'] for page in prs for pr in page
            if pr.get('head', {}).get('repo', {}).get('full_name') == repo
            and pr.get('head', {}).get('ref', '').startswith('publications/')]


def main():
    subprocess.run(['python3', 'scripts/build_site_index.py', 'data', 'docs/index.json'], check=True)
    # Public deadline-only projection follows every daily publication refresh.
    if not write_projection('data/publications_active.json', 'docs/publications_active.json'):
        raise RuntimeError('Publication source unavailable; refusing to publish a data PR')
    repo = os.environ['GITHUB_REPOSITORY']
    pending = pending_publication_prs(repo)
    if pending:
        print(f'publication PR(s) awaiting review: {pending}; no new PR or head update')
        return
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
        'body': 'Automated public publication baseline and alert payload (refs #527). Text-only data update. Requires independent and exact-head Claude reviews, green CI and eligible approval before normal manual merge.'})
    print(pr['html_url'], flush=True)
    print('awaiting independent and exact-head Claude reviews, green CI and eligible approval; '
          'staged PR is not publication', flush=True)


if __name__ == '__main__':
    main()
