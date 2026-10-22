"""Validate auditor callback against immutable public source before publication."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def validate(report, source_bytes, current_bytes):
    if report.get('schema_version') != 1:
        raise ValueError('Unknown analysis schema')
    for key in ('source_run', 'auditor_run'):
        if not re.fullmatch(r'[0-9]+', str(report.get(key, ''))):
            raise ValueError('Invalid run identifier')
    if not re.fullmatch(r'[0-9a-f]{40}', report.get('source_commit', '')):
        raise ValueError('Invalid source commit')
    digest = hashlib.sha256(source_bytes).hexdigest()
    if report.get('source_digest') != digest:
        raise ValueError('Source digest mismatch')
    if hashlib.sha256(current_bytes).hexdigest() != digest:
        raise ValueError('Stale audit: current published scan changed; do not overwrite latest result')
    feed = json.loads(source_bytes)
    cursor = feed['batch']['offset'] + feed['batch']['limit']
    total = report.get('total_unique_parcels')
    if not isinstance(total, int) or total < 1:
        raise ValueError('Invalid total')
    cursor = min(cursor, total)
    if report.get('published_cursor') != cursor or report.get('remaining') != total - cursor:
        raise ValueError('Cursor arithmetic mismatch')
    # Construct local canonical output, never render arbitrary callback strings.
    return {'schema_version': 1, 'source_commit': report['source_commit'],
            'source_run': report['source_run'], 'auditor_run': report['auditor_run'],
            'source_digest': digest, 'total_unique_parcels': total, 'published_cursor': cursor,
            'remaining': total - cursor, 'cursor_percent': 100 * cursor / total,
            'warning': 'Cursor/range progress only, not proof that every query succeeded.'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', required=True)
    args = ap.parse_args()
    raw = Path(args.report).read_text()
    if len(raw) > 6000:
        raise ValueError('Oversized report')
    report = json.loads(raw)
    sha = report.get('source_commit', '')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid SHA')
    source = subprocess.run(['git', 'show', f'{sha}:data/permit_requests.json'],
                            capture_output=True, check=True).stdout
    parcels = json.loads(subprocess.run(['git', 'show', f'{sha}:data/ginot_hair_parcels.geojson'],
                                       capture_output=True, check=True).stdout)
    unique = {(int(f['properties']['gush']), int(f['properties']['helka']))
              for f in parcels['features'] if f.get('properties', {}).get('gush')
              and f.get('properties', {}).get('helka')}
    if report.get('total_unique_parcels') != len(unique):
        raise ValueError('Parcel total mismatch with source snapshot')
    result = validate(report, source, Path('data/permit_requests.json').read_bytes())
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    Path('data/parcel_audit.json').write_text(text)
    Path('docs/parcel-audit.json').write_text(text)


if __name__ == '__main__':
    main()
