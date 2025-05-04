"""Fetch daily statistics from the Plausible export API.

- https://plausible.io/docs/export-stats
- https://plausible.io/docs/stats-api/
"""

# /// script
# dependencies = [
#     "urllib3>=2"
# ]
# ///

from __future__ import annotations

import csv
import json
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import urllib3

# Site ID -> prefixes
SITES = {
    'python.org': (),
    'docs.python.org': (
        # symlinks
        'dev',
        '3',
        # versions
        '3.14',
        '3.13',
        '3.12',  # first version with the Plausible script
        # languages
        'es',
        'fr',
        'it',
        'ja',
        'ko',
        'pl',
        'pt-br',
        'tr',
        'zh-cn',
        'zh-tw',
    ),
    'packaging.python.org': (
        'en',
        'ja',
        'pt-br',
    ),
    'peps.python.org': (),
    # 'pypi.org': (),
    # 'blog.pypi.org': (),
}
HEADERS = {
    'Cache-Control': 'no-cache',
}
OUTPUT_DIR = Path('stats')
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)


def fetch_export(http: urllib3.PoolManager, site_id: str, prefix: str) -> Path | None:
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    slug = f'{site_id}/{prefix}/' if prefix else f'{site_id}/'
    params = {
        'period': 'day',
        'date': yesterday,
        'filters': '[]',
    }
    if prefix:
        params['filters'] = f'[["contains","event:page",["/{prefix}/"]]]'
    url = f'https://analytics.python.org/{site_id}/export?{urlencode(params)}'
    print(f'Fetching Plausible statistics for {slug} from {yesterday}...')
    resp = http.request('GET', url, timeout=30, headers=HEADERS)
    if resp.status != 200:
        print(
            f'Failed to fetch statistics for {slug} (HTTP {resp.status})'
        )
        return None
    content = resp.data
    print(f'Received {len(content)} bytes')

    export_dir = OUTPUT_DIR / f'{site_id}_{yesterday}'
    export_dir.mkdir(exist_ok=True, parents=True)

    if prefix:
        prefix = prefix.replace('/', '-')
        output_filename = export_dir / f'{site_id}_{yesterday}.prefix-{prefix}.zip'
    else:
        output_filename = export_dir / f'{site_id}_{yesterday}.zip'
    output_filename.write_bytes(content)
    print(f'Saved statistics archive for {slug} to {output_filename}')
    return output_filename


def extract_zip(zip_path: Path) -> dict[str, list[dict[str, str]]]:
    extracted = {}
    zf = zipfile.ZipFile(zip_path)
    zp = zipfile.Path(zf)
    for file in zp.iterdir():
        print(f'{zip_path.name}: Converting {file.name} to JSON...')
        if not file.name.endswith('.csv'):
            continue
        with file.open(encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        json_filename = f'{zip_path.stem}.{file.stem}.json'
        zip_path.with_name(json_filename).write_text(json.dumps(rows, indent=0))
        extracted[file.stem] = rows
    return extracted


def main() -> None:
    start = time.perf_counter()
    http = urllib3.PoolManager()
    for site_id, prefixes in SITES.items():
        print(f'Fetching Plausible statistics for {site_id}...')
        for prefix in prefixes or ('',):
            archive_path = fetch_export(http, site_id, prefix)
            if archive_path is not None:
                extract_zip(archive_path)
    print(f'Finished in {time.perf_counter() - start:.2f} seconds')


if __name__ == '__main__':
    main()
