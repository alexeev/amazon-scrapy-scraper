"""Extraction regression test over saved real Amazon pages.

`tests/corpus/` holds the pages the extraction layer was built against, one
gzipped HTML file per ASIN, grouped by marketplace, next to a snapshot of the
record each one is expected to produce. The test re-extracts every page and
compares it to the snapshot field by field.

This is the test that the unit tests cannot be: the fixtures in
`test_extraction.py` are hand-written and pin down structures we already
understand, while these are 2 MB pages full of structures nobody enumerated.
A runtime upgrade once silently dropped an attribute table from two of them
and no unit test noticed.

When a change is *meant* to alter extraction output, regenerate the snapshot
and review the diff as part of the change:

    uv run python tests/test_corpus.py --update
"""

import gzip
import json
import pathlib
import sys
import unittest

from parsel import Selector

# This module doubles as the snapshot updater, so it has to import the project
# when run as a script from anywhere, not only under `unittest discover`.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon_scraper.extraction import PdpExtractor, for_domain  # noqa: E402

CORPUS = pathlib.Path(__file__).resolve().parent / 'corpus'

# Directory name -> the marketplace host its pages were fetched from, which
# selects the locale profile the extractor runs with.
MARKETPLACES = {
    'amazon_de': 'www.amazon.de',
    'amazon_com': 'www.amazon.com',
}

SNAPSHOT = 'expected.jsonl.gz'

# Set by the crawl, not by the page: it would differ on every run.
VOLATILE = 'fetched_at'
PLACEHOLDER = '<runtime>'


def extract_dir(name):
    """Every page in one marketplace directory, as {asin: record}."""
    extractor = PdpExtractor(for_domain(MARKETPLACES[name]))
    records = {}
    for path in sorted((CORPUS / name).glob('*.html.gz')):
        asin = path.name[:-len('.html.gz')]
        with gzip.open(path, 'rt', encoding='utf-8') as fh:
            html = fh.read()
        record = extractor.extract(Selector(html), html, {'asin': asin})
        record[VOLATILE] = PLACEHOLDER
        records[asin] = record
    return records


def load_snapshot(name):
    with gzip.open(CORPUS / name / SNAPSHOT, 'rt', encoding='utf-8') as fh:
        return {r['asin']: r for r in map(json.loads, fh)}


def write_snapshot(name, records):
    with gzip.open(CORPUS / name / SNAPSHOT, 'wt', encoding='utf-8',
                   compresslevel=9) as fh:
        for asin in sorted(records):
            fh.write(json.dumps(records[asin], ensure_ascii=False,
                                sort_keys=True) + '\n')


def flatten(value, prefix=''):
    """A record as {dotted.path: scalar}, so a diff can name what moved."""
    flat = {}
    if isinstance(value, dict):
        for key, child in value.items():
            flat.update(flatten(child, f'{prefix}.{key}' if prefix else key))
    elif isinstance(value, list):
        flat[f'{prefix}[]'] = len(value)
        for index, child in enumerate(value):
            flat.update(flatten(child, f'{prefix}[{index}]'))
    else:
        flat[prefix] = value
    return flat


def differences(expected, actual):
    """Human-readable field-level differences between two records."""
    want, got = flatten(expected), flatten(actual)
    lines = []
    for path in sorted(set(want) | set(got)):
        a, b = want.get(path, '<absent>'), got.get(path, '<absent>')
        if a != b:
            lines.append(f'    {path}\n'
                         f'      expected: {str(a)[:160]}\n'
                         f'      actual:   {str(b)[:160]}')
    return lines


class Corpus(unittest.TestCase):

    def check(self, name):
        expected = load_snapshot(name)
        actual = extract_dir(name)

        self.assertEqual(sorted(expected), sorted(actual),
                         f'{name}: corpus and snapshot cover different ASINs; '
                         f'run `python tests/test_corpus.py --update`')

        report = []
        for asin in sorted(expected):
            diff = differences(expected[asin], actual[asin])
            if diff:
                report.append(f'  {asin}:\n' + '\n'.join(diff))
        if report:
            self.fail(
                f'{name}: extraction changed for {len(report)} of '
                f'{len(expected)} saved pages.\n' + '\n'.join(report[:5]) +
                ('\n  ...' if len(report) > 5 else '') +
                '\nIf this is intended, regenerate with '
                '`python tests/test_corpus.py --update` and review the diff.')

    def test_amazon_de(self):
        self.check('amazon_de')

    def test_amazon_com(self):
        # One page only. amazon.com is probed, not supported: it is here to
        # keep the marketplace-generic paths honest, not to claim coverage.
        self.check('amazon_com')


if __name__ == '__main__':
    if '--update' in sys.argv:
        for marketplace in MARKETPLACES:
            records = extract_dir(marketplace)
            write_snapshot(marketplace, records)
            print(f'{marketplace}: wrote {len(records)} records to '
                  f'{CORPUS / marketplace / SNAPSHOT}')
    else:
        unittest.main()
