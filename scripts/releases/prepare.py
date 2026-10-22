#!/usr/bin/env python3
"""Lightweight release preparation from merged PR metadata; never pushes tags.

Input: gh pr list --state merged --json number,title,labels,mergedAt,url
Only pass PRs since the last release. Output is a reviewable version bump,
CHANGELOG and bilingual notes. Public release is a separate CI-green snapshot.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path


def bump(version, prs):
    major, minor, patch = map(int, version.split('.'))
    labels = {label['name'].lower() for pr in prs for label in pr.get('labels', [])}
    if labels & {'breaking', 'release:major'}:
        return f'{major+1}.0.0'
    if labels & {'enhancement', 'feature', 'release:minor'}:
        return f'{major}.{minor+1}.0'
    return f'{major}.{minor}.{patch+1}'


def prepare(root, prs, date):
    prs = [p for p in prs if p.get('mergedAt')]
    if not prs:
        raise ValueError('no merged PRs to release')
    version_file = root / 'src/ginot/__init__.py'
    content = version_file.read_text()
    old = re.search(r'__version__ = "([0-9.]+)"', content)[1]
    version = bump(old, prs)
    entries = '\n'.join(f"- #{p['number']}: {p['title']}" for p in prs)
    notes = f'# {version} - {date}\n\n## עברית\n\nשינויים שנכללו בגרסה:\n{entries}\n\n## English\n\nChanges included in this release:\n{entries}\n'
    version_file.write_text(content.replace(f'"{old}"', f'"{version}"'))
    output = root / 'releases' / f'{version}.md'
    output.parent.mkdir(exist_ok=True)
    output.write_text(notes)
    changelog = root / 'CHANGELOG.md'
    text = changelog.read_text()
    changelog.write_text(text.replace('# Changelog', f'# Changelog\n\n## [{version}] - {date}\n\n{entries}', 1))
    # Keep committed static footers aligned without running a network refresh.
    for file in (root / 'docs').rglob('*.html'):
        html = file.read_text()
        html = html.replace(f'>Version {old}<', f'>Version {version}<')
        html = html.replace(f'Version {old}</p>', f'Version {version}</p>')
        html = html.replace(f'dir="ltr">{old}</span>', f'dir="ltr">{version}</span>')
        file.write_text(html)
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prs', type=Path, help='Optional metadata file; otherwise collect merged PRs since latest tag')
    parser.add_argument('--date', required=True)
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    if args.prs:
        prs = json.loads(args.prs.read_text())
    else:
        tag = subprocess.run(['git', 'describe', '--tags', '--abbrev=0'], cwd=args.root,
                             text=True, capture_output=True)
        since = None
        if tag.returncode == 0:
            since = subprocess.check_output(['git', 'show', '-s', '--format=%cI', tag.stdout.strip()],
                                            cwd=args.root, text=True).strip()
        command = ['gh', 'pr', 'list', '--state', 'merged', '--limit', '100',
                   '--json', 'number,title,labels,mergedAt,url']
        if since:
            command += ['--search', 'merged:>' + since]
        prs = json.loads(subprocess.check_output(command, cwd=args.root, text=True))
    print(prepare(args.root, prs, args.date))


if __name__ == '__main__':
    main()
