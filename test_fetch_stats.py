import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import fetch_stats


def record(name, visitors=1):
    return dict(
        name=name,
        visitors=visitors,
        pageviews=visitors,
        bounce_rate=0,
        time_on_page=None,
        scroll_depth=50,
    )


def response(rows, status=200):
    return SimpleNamespace(status=status, data=json.dumps({'results': rows}).encode())


class FetchPagesTests(unittest.TestCase):
    def test_pagination_includes_pages_beyond_export_limit(self):
        first = [record(f'/3/page-{i}.html') for i in range(1000)]
        http = Mock()
        http.request.side_effect = [
            response(first),
            response([record('/3/bugs.html', 28)]),
            response([]),
        ]
        rows = fetch_stats.fetch_pages(http, 'docs.python.org', '3', '2026-09-22')
        self.assertEqual(len(rows), 1001)
        self.assertEqual(rows[-1]['name'], '/3/bugs.html')
        self.assertEqual(rows[-1]['visitors'], '28')
        self.assertEqual(rows[-1]['time_on_page'], '')
        for page, call in enumerate(http.request.call_args_list, start=1):
            params = parse_qs(urlsplit(call.args[1]).query)
            self.assertEqual(params['page'], [str(page)])
            self.assertEqual(params['limit'], ['1000'])
            self.assertEqual(params['date'], ['2026-09-22'])
            self.assertEqual(params['detailed'], ['true'])

    def test_short_batches_are_followed_until_empty(self):
        http = Mock()
        http.request.side_effect = [
            response([record('/3/')]),
            response([record('/3/bugs.html')]),
            response([]),
        ]
        self.assertEqual(
            len(fetch_stats.fetch_pages(http, 'docs.python.org', '3', '2026-09-22')), 2
        )
        self.assertEqual(http.request.call_count, 3)

    def test_error_after_first_batch_does_not_return_partial_data(self):
        http = Mock()
        http.request.side_effect = [response([record('/3/')]), response([], status=503)]
        with self.assertRaisesRegex(RuntimeError, 'HTTP 503'):
            fetch_stats.fetch_pages(http, 'docs.python.org', '3', '2026-09-22')

    def test_invalid_response_is_not_treated_as_empty_data(self):
        http = Mock()
        http.request.return_value = response(None)
        with self.assertRaisesRegex(ValueError, 'Expected a list'):
            fetch_stats.fetch_pages(http, 'docs.python.org', '3', '2026-09-22')

    def test_prefix_filters_are_anchored_and_escape_versions(self):
        for prefix, included, excluded in (
            ('3', '/3/bugs.html', '/pl/3/bugs.html'),
            ('3.14', '/3.14/bugs.html', '/3x14/bugs.html'),
            ('pl', '/pl/3/bugs.html', '/3/pl/bugs.html'),
        ):
            with self.subTest(prefix=prefix):
                operator, field, patterns = json.loads(
                    fetch_stats.page_filters(prefix)
                )[0]
                self.assertEqual((operator, field), ('matches', 'event:page'))
                self.assertIsNotNone(re.search(patterns[0], included))
                self.assertIsNone(re.search(patterns[0], excluded))
        self.assertEqual(json.loads(fetch_stats.page_filters('')), [])

    def test_extract_uses_full_pages_and_preserves_other_csv_reports(self):
        pages = [dict(name='/3/bugs.html', visitors='28')]
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'docs.python.org_2026-09-22.prefix-3.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('pages.csv', 'name,visitors\n/3/,100\n')
                output.writestr('entry_pages.csv', 'name,visitors\n/3/,10\n')
            extracted = fetch_stats.extract_zip(archive, pages)
            self.assertEqual(extracted['pages'], pages)
            self.assertEqual(
                extracted['entry_pages'], [{'name': '/3/', 'visitors': '10'}]
            )
            self.assertEqual(
                json.loads(archive.with_suffix('.pages.json').read_text()), pages
            )

    def test_export_uses_the_same_prefix_filter(self):
        http = Mock()
        http.request.return_value = SimpleNamespace(status=200, data=b'archive')
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(fetch_stats, 'OUTPUT_DIR', Path(directory)):
                archive = fetch_stats.fetch_export(
                    http, 'docs.python.org', '3.14', '2026-09-22'
                )
            self.assertEqual(archive.read_bytes(), b'archive')
            params = parse_qs(urlsplit(http.request.call_args.args[1]).query)
            self.assertEqual(params['filters'], [fetch_stats.page_filters('3.14')])
            self.assertEqual(params['date'], ['2026-09-22'])

    def test_main_fetches_all_pages_before_extracting_archive(self):
        pages = [{'name': '/3/bugs.html', 'visitors': '28'}]
        with patch.object(
            fetch_stats, 'SITES', {'docs.python.org': ('3',)}
        ), patch.object(
            fetch_stats, 'fetch_export', return_value=Path('snapshot.zip')
        ) as export, patch.object(
            fetch_stats, 'fetch_pages', return_value=pages
        ) as fetch, patch.object(
            fetch_stats, 'extract_zip'
        ) as extract:
            fetch_stats.main()
        self.assertEqual(export.call_args.args[-1], fetch.call_args.args[-1])
        extract.assert_called_once_with(Path('snapshot.zip'), pages)


if __name__ == '__main__':
    unittest.main()
