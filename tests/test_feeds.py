"""Tests for reading a study's feeds as one corpus.

A research question outlives a single crawl, and the moment two feeds are read
together something has to decide which sighting of an ASIN the study uses. The
rule is ``fetched_at``, and these tests exist because the obvious alternative
-- whichever feed was named last -- is wrong in a way nothing would report: a
shell glob sorts alphabetically, and the alphabetically later feed is not the
younger one.

The CLI tests are here too, because telling a feed path from an ASIN is the
one piece of argument handling this command line does by hand.
"""

import gzip
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon_scraper.analysis import feeds  # noqa: E402
from amazon_scraper.analysis.__main__ import split_arguments  # noqa: E402


def record(asin, fetched_at, **extra):
    row = {'asin': asin, 'title': f'{asin} pasta'}
    if fetched_at is not None:
        row['fetched_at'] = fetched_at
    row.update(extra)
    return row


class Feeds(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def write(self, name, records):
        path = pathlib.Path(self.directory.name) / name
        opener = gzip.open if name.endswith('.gz') else open
        with opener(path, 'wt', encoding='utf-8') as handle:
            for row in records:
                handle.write(json.dumps(row) + '\n')
        return str(path)


class Merge(Feeds):

    def test_one_feed_is_read_unchanged(self):
        path = self.write('a.jsonl', [record('B000000001', '2026-09-15T10:00:00+00:00'),
                                      record('B000000002', '2026-09-15T10:01:00+00:00')])
        records, provenance = feeds.merge([path])
        self.assertEqual([r['asin'] for r in records],
                         ['B000000001', 'B000000002'])
        self.assertEqual(provenance,
                         {'records': 2, 'feeds': 1, 'superseded': 0})

    def test_the_freshest_crawl_wins_not_the_last_argument(self):
        """The bug this rule exists for. ``data/study_*.jsonl`` expands
        alphabetically, which has nothing to do with when each crawl ran, and
        price and availability are exactly the fields that would go stale."""
        older = self.write('z_older.jsonl',
                           [record('B000000001', '2026-09-15T08:00:00+00:00',
                                   price={'amount': 9.99})])
        newer = self.write('a_newer.jsonl',
                           [record('B000000001', '2026-09-15T14:00:00+00:00',
                                   price={'amount': 7.49})])
        for order in ([newer, older], [older, newer]):
            records, provenance = feeds.merge(order)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['price']['amount'], 7.49,
                             f'argument order {order} decided the winner')
            self.assertEqual(provenance['superseded'], 1)

    def test_an_asin_crawled_three_times_is_one_record_and_one_supersession(self):
        stamps = ['2026-09-15T08:00:00+00:00', '2026-09-15T09:00:00+00:00',
                  '2026-09-15T10:00:00+00:00']
        paths = [self.write(f'{index}.jsonl', [record('B000000001', stamp)])
                 for index, stamp in enumerate(reversed(stamps))]
        records, provenance = feeds.merge(paths)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['fetched_at'], stamps[-1])
        self.assertEqual(provenance,
                         {'records': 1, 'feeds': 3, 'superseded': 1})

    def test_a_record_that_will_not_say_when_it_was_fetched_loses(self):
        undated = self.write('undated.jsonl', [record('B000000001', None,
                                                      price={'amount': 1.0})])
        dated = self.write('dated.jsonl',
                           [record('B000000001', '2026-01-01T00:00:00+00:00',
                                   price={'amount': 2.0})])
        for order in ([undated, dated], [dated, undated]):
            records, _ = feeds.merge(order)
            self.assertEqual(records[0]['price']['amount'], 2.0)

    def test_a_timestamp_without_an_offset_is_read_as_utc_not_dropped(self):
        """Naive and aware timestamps raise when compared. A feed that lost
        its offset is still a feed, and must not take the whole merge down."""
        naive = self.write('naive.jsonl', [record('B000000001',
                                                  '2026-09-15T14:00:00')])
        aware = self.write('aware.jsonl', [record('B000000001',
                                                  '2026-09-15T08:00:00+00:00')])
        records, _ = feeds.merge([aware, naive])
        self.assertEqual(records[0]['fetched_at'], '2026-09-15T14:00:00')

    def test_an_unparseable_timestamp_does_not_end_the_merge(self):
        broken = self.write('broken.jsonl', [record('B000000001', 'yesterday')])
        good = self.write('good.jsonl', [record('B000000001',
                                                '2026-09-15T08:00:00+00:00')])
        records, _ = feeds.merge([broken, good])
        self.assertEqual(records[0]['fetched_at'], '2026-09-15T08:00:00+00:00')

    def test_records_keep_the_order_they_were_first_seen_in(self):
        first = self.write('first.jsonl',
                           [record('B000000001', '2026-09-15T08:00:00+00:00'),
                            record('B000000002', '2026-09-15T08:00:00+00:00')])
        second = self.write('second.jsonl',
                            [record('B000000003', '2026-09-15T09:00:00+00:00'),
                             record('B000000001', '2026-09-15T09:00:00+00:00')])
        records, _ = feeds.merge([first, second])
        self.assertEqual([r['asin'] for r in records],
                         ['B000000001', 'B000000002', 'B000000003'],
                         'a fresher copy replaces a record, it does not move it')

    def test_a_record_with_no_asin_is_kept_rather_than_collided(self):
        path = self.write('odd.jsonl', [{'title': 'no asin'},
                                        {'title': 'also no asin'}])
        records, provenance = feeds.merge([path])
        self.assertEqual(len(records), 2)
        self.assertEqual(provenance['superseded'], 0)

    def test_gzipped_feeds_are_read_directly(self):
        plain = self.write('plain.jsonl',
                           [record('B000000001', '2026-09-15T08:00:00+00:00')])
        packed = self.write('packed.jsonl.gz',
                            [record('B000000002', '2026-09-15T08:00:00+00:00')])
        records, provenance = feeds.merge([plain, packed])
        self.assertEqual(provenance['records'], 2)
        self.assertEqual({r['asin'] for r in records},
                         {'B000000001', 'B000000002'})


class ProvenanceLine(Feeds):

    def test_it_states_records_feeds_and_supersessions(self):
        line = feeds.provenance_line({'records': 471, 'feeds': 3,
                                      'superseded': 95})
        self.assertEqual(line, '471 records from 3 feeds, 95 ASINs superseded '
                               'by a fresher crawl')

    def test_it_counts_in_the_singular_too(self):
        line = feeds.provenance_line({'records': 1, 'feeds': 1,
                                      'superseded': 1})
        self.assertIn('1 feed,', line)
        self.assertIn('1 ASIN superseded', line)


class Arguments(Feeds):
    """Feeds and ASINs share one positional list, so it has to be split."""

    def test_a_readable_file_is_a_feed_and_the_rest_are_asins(self):
        path = self.write('a.jsonl', [])
        paths, asins = split_arguments([path, 'B0CPQ5HGC8', 'B003CJ707C'])
        self.assertEqual(paths, [path])
        self.assertEqual(asins, ['B0CPQ5HGC8', 'B003CJ707C'])

    def test_several_feeds_and_no_asins(self):
        first, second = self.write('a.jsonl', []), self.write('b.jsonl', [])
        paths, asins = split_arguments([first, second])
        self.assertEqual(paths, [first, second])
        self.assertEqual(asins, [])

    def test_a_mistyped_path_stops_the_command(self):
        """The failure this guards against is an analysis of nothing that
        still prints a well-formed report."""
        with self.assertRaises(SystemExit) as raised:
            split_arguments([self.write('a.jsonl', []), 'data/typo.jsonl'])
        self.assertIn('data/typo.jsonl', str(raised.exception))

    def test_asins_alone_are_not_an_analysis(self):
        with self.assertRaises(SystemExit) as raised:
            split_arguments(['B0CPQ5HGC8'])
        self.assertIn('feed', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
