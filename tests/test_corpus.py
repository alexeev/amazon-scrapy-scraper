"""Regression test over saved real Amazon pages: extraction, then validation.

`tests/corpus/` holds the pages the extraction layer was built against, one
gzipped HTML file per ASIN, grouped by marketplace, next to two snapshots:

`expected.jsonl.gz`
    the record each page should extract to -- what the page says.
`validated.jsonl.gz`
    the contract record each of those should validate to, with **no category
    profile** -- how much of what the page says holds up on its own.

Both are compared field by field. The second exists because the published
contract is now something downstream code depends on, and a change in a
status, a source or a note is exactly as much of a breaking change as a
change in an extracted value -- and far easier to make by accident, because
the validation rules interact. It is deliberately run without a category:
what is pinned is the layer that belongs to nobody.

This is the test the unit tests cannot be: the fixtures in
`test_extraction.py` are hand-written and pin down structures we already
understand, while these are 2 MB pages full of structures nobody enumerated.
A runtime upgrade once silently dropped an attribute table from two of them
and no unit test noticed.

When a change is *meant* to alter either output, regenerate the snapshots and
review the diff as part of the change:

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
from amazon_scraper.validation import validate  # noqa: E402

CORPUS = pathlib.Path(__file__).resolve().parent / 'corpus'

# Directory name -> the marketplace host its pages were fetched from, which
# selects the locale profile the extractor runs with.
MARKETPLACES = {
    'amazon_de': 'www.amazon.de',
    'amazon_com': 'www.amazon.com',
}

SNAPSHOT = 'expected.jsonl.gz'
VALIDATED = 'validated.jsonl.gz'

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


def validate_all(records):
    """Every extracted record put through the contract, category-free."""
    return {asin: validate(record).as_dict()
            for asin, record in records.items()}


def load_snapshot(name, filename=SNAPSHOT):
    with gzip.open(CORPUS / name / filename, 'rt', encoding='utf-8') as fh:
        return {r['asin']: r for r in map(json.loads, fh)}


def write_snapshot(name, records, filename=SNAPSHOT):
    with gzip.open(CORPUS / name / filename, 'wt', encoding='utf-8',
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

    def check(self, name, what, expected, actual):
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
                f'{name}: {what} changed for {len(report)} of '
                f'{len(expected)} saved pages.\n' + '\n'.join(report[:5]) +
                ('\n  ...' if len(report) > 5 else '') +
                '\nIf this is intended, regenerate with '
                '`python tests/test_corpus.py --update` and review the diff.')

    def check_extraction(self, name):
        self.check(name, 'extraction', load_snapshot(name), extract_dir(name))

    def check_validation(self, name):
        self.check(name, 'validation output',
                   load_snapshot(name, VALIDATED),
                   validate_all(extract_dir(name)))

    def test_amazon_de(self):
        self.check_extraction('amazon_de')

    def test_amazon_com(self):
        # One page only. amazon.com is probed, not supported: it is here to
        # keep the marketplace-generic paths honest, not to claim coverage.
        self.check_extraction('amazon_com')

    def test_amazon_de_validation(self):
        self.check_validation('amazon_de')

    def test_amazon_com_validation(self):
        self.check_validation('amazon_com')


if __name__ == '__main__':
    if '--update' in sys.argv:
        for marketplace in MARKETPLACES:
            records = extract_dir(marketplace)
            write_snapshot(marketplace, records)
            write_snapshot(marketplace, validate_all(records), VALIDATED)
            print(f'{marketplace}: wrote {len(records)} records to '
                  f'{CORPUS / marketplace / SNAPSHOT} and '
                  f'{CORPUS / marketplace / VALIDATED}')
    else:
        unittest.main()
