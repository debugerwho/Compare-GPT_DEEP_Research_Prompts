#!/usr/bin/env python3
"""Offline integrity checks; these do not test any candidate tool or fetch URLs."""
import json
import re
import sys
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_json(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))


class CatalogIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_json('tool_candidates.json')
        cls.items = cls.catalog['items']
        cls.posts = [json.loads(line) for line in (HERE / 'post_index.jsonl').read_text(encoding='utf-8').splitlines()]
        cls.index = {int(p['id'].removeprefix('message')): p for p in cls.posts}
        cls.checks = load_json('github_checks.json')['repositories']
        cls.by_repo = {r['repo'].lower(): r for r in cls.checks}
        cls.manifest = load_json('source_manifest.json')

    def test_unique_ids_and_required_fields(self):
        self.assertEqual(len(self.items), len({x['id'] for x in self.items}))
        for n, item in enumerate(self.items, 1):
            self.assertEqual(item['id'], f'VC{n:03}')
            for key in ('name', 'stages', 'kind', 'purpose', 'sources', 'origin', 'evidence', 'windows10', 'risk'):
                self.assertTrue(item[key], (item['id'], key))
            self.assertTrue(set(item['stages']) <= set('0123456'))

    def test_source_ids_dates_and_backlinks(self):
        self.assertEqual(len(self.index), len(self.posts))
        expected = {i: [] for i in self.index}
        for item in self.items:
            for source in item['sources']:
                post = self.index[source['post_id']]
                self.assertEqual(source['date'], post['date'])
                self.assertEqual(source['url'], f"https://t.me/vibecoding_tg/{source['post_id']}")
                expected[source['post_id']].append(item['id'])
        for i, post in self.index.items():
            self.assertEqual(sorted(post['selected_candidate_ids']), sorted(expected[i]))

    def test_readme_status_and_license_are_not_invented(self):
        self.assertEqual(len(self.checks), len(self.by_repo))
        for item in self.items:
            if item['evidence'].startswith('README/metadata'):
                check = self.by_repo[item['repo'].lower()]
                self.assertEqual(check['status'], 'metadata_verified')
                self.assertRegex(check['readme_blob'], r'^[0-9a-f]{40}$')
                self.assertEqual(item['license'], check.get('license'))
            elif item['evidence'].startswith('GitHub недоступен'):
                self.assertEqual(self.by_repo[item['repo'].lower()]['status'], 'unavailable')
            else:
                self.assertTrue(item['evidence'].startswith('Только пост/фотография'))

    def test_manifest_and_photo_provenance(self):
        source = self.manifest['source']
        self.assertEqual(source['posts'], len(self.posts))
        self.assertEqual(source['photo_references'], sum(len(p['photo_paths']) for p in self.posts))
        self.assertEqual(source['photo_only_posts'], sum(not p['title_excerpt'] and bool(p['photo_paths']) for p in self.posts))
        self.assertRegex(source['sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(len(self.manifest['photos']), 7)
        for photo in self.manifest['photos']:
            i = int(photo['source_post_id'].removeprefix('message'))
            self.assertIn(photo['file_name'], [Path(p).name for p in self.index[i]['photo_paths']])
            self.assertRegex(photo['sha256'], r'^[0-9a-f]{64}$')
            self.assertEqual(photo['date'], self.index[i]['date'])

    def test_primary_document_blobs(self):
        for doc in load_json('documentation_checks.json'):
            self.assertRegex(doc['blob_sha'], r'^[0-9a-f]{40}$')
            self.assertTrue(doc['url'].startswith('https://github.com/' + doc['repo'] + '/blob/'))

    def test_every_card_is_in_markdown(self):
        md = (HERE / 'TOOL_CANDIDATES.md').read_text(encoding='utf-8')
        for item in self.items:
            self.assertEqual(len(re.findall(r'\b' + item['id'] + r'\b', md)), 1)

    def test_local_navigation(self):
        files = list(HERE.glob('*.md')) + [ROOT / 'README.md', ROOT / 'research/STAGED_TOOL_CATALOG.md', ROOT / 'research/LOCAL_PILOT_CONTEXT.md']
        for file in files:
            for link in re.findall(r'\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
                if '://' in link or link.startswith(('mailto:', '#')):
                    continue
                target = unquote(link.split('#')[0])
                self.assertTrue((file.parent / target).is_file(), (str(file), link))

    def test_no_raw_download_deliverables(self):
        ignored = (ROOT / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('/google_drive/', ignored.splitlines())
        self.assertFalse(any(p.suffix.lower() in {'.html', '.jpg', '.png'} for p in HERE.iterdir()))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CatalogIntegrity)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        cards = load_json('tool_candidates.json')['items']
        repos = load_json('github_checks.json')['repositories']
        print(f"Integrity only: {len(cards)} cards; {len(repos)} repositories; statuses {dict(Counter(r['status'] for r in repos))}")
    sys.exit(0 if result.wasSuccessful() else 1)
