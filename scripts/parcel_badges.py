"""Public aggregate-only progress endpoints; raw permit data remains untouched."""
import json
from pathlib import Path


def progress(parcels, feed):
    unique = {(int(p['properties']['gush']), int(p['properties']['helka']))
              for p in parcels['features'] if p.get('properties', {}).get('gush')
              and p.get('properties', {}).get('helka')}
    total = len(unique)
    b = feed['batch']
    if not total or b['offset'] < 0 or b['limit'] <= 0 or feed.get('checkpoint'):
        raise ValueError('Invalid published cursor')
    cursor = min(total, b['offset'] + b['limit'])
    return cursor, total


def build_badges(root=Path('.')):
    cursor, total = progress(json.loads((root / 'data/ginot_hair_parcels.geojson').read_text()),
                             json.loads((root / 'data/permit_requests.json').read_text()))
    out = root / 'docs/badge'
    out.mkdir(parents=True, exist_ok=True)
    for name, label, message in [('progress', 'published range', f'{cursor}/{total} ({100*cursor/total:.1f}%)'),
                                  ('remaining', 'remaining parcels', str(total-cursor))]:
        (out / f'parcel-{name}.json').write_text(json.dumps({'schemaVersion': 1, 'label': label,
              'message': message, 'color': 'blue'}) + '\n')


if __name__ == '__main__':
    build_badges()
