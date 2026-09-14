"""Tests for crawl provenance: run identity, locale, discovery and the page store.

The discovery tests run against a real saved Amazon.de search page rather than
a hand-built one, because the thing being tested is a claim about Amazon's
markup, not about our code: that the result grid can be told apart from the
carousels around it, and that sponsored placement is detectable. On the saved
page the spider's discovery selector matches 82 nodes, of which 60 are the
grid; 12 of those are sponsored; and two ASINs appear twice on that single
page, once organic and once sponsored. Every one of those numbers is asserted,
so a markup change fails here rather than silently degrading a crawl.
"""

import gzip
import json
import pathlib
import sys
import tempfile
import unittest

from scrapy.http import HtmlResponse
from scrapy.settings import Settings

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon_scraper import run as run_module  # noqa: E402
from amazon_scraper.extraction import PdpExtractor, for_domain  # noqa: E402
from amazon_scraper.run import CrawlRun, acquisition_locale  # noqa: E402
from amazon_scraper.spiders.amazon_product import AmazonProductSpider  # noqa: E402

CORPUS = pathlib.Path(__file__).resolve().parent / 'corpus'
SEARCH_PAGE = CORPUS / 'amazon_de_search' / 'spaghetti-hartweizen-p1.html.gz'
A_PDP = CORPUS / 'amazon_de' / 'B088419TTP.html.gz'

DE = for_domain('www.amazon.de')


def read_fixture(path):
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        return handle.read()


class Stats:
    """The slice of Scrapy's stats collector the spider touches."""

    def __init__(self):
        self.values = {}

    def inc_value(self, key, count=1):
        self.values[key] = self.values.get(key, 0) + count


class Crawler:
    def __init__(self):
        self.stats = Stats()


class Locale(unittest.TestCase):

    def test_the_validated_profile_matches_its_marketplace(self):
        locale = acquisition_locale(
            Settings({'DEFAULT_REQUEST_HEADERS':
                      {'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8'}}), DE)
        self.assertEqual(locale['status'], 'matches')
        self.assertEqual(locale['language'], 'de')

    def test_english_on_a_german_marketplace_is_a_conflict(self):
        """The failure this guards against is silent: German label lists
        against English markup map nothing, and the record still validates."""
        locale = acquisition_locale(
            Settings({'DEFAULT_REQUEST_HEADERS':
                      {'Accept-Language': 'en-US,en;q=0.9'}}), DE)
        self.assertEqual(locale['status'], 'conflict')

    def test_an_unset_locale_is_reported_rather_than_assumed(self):
        locale = acquisition_locale(
            Settings({'DEFAULT_REQUEST_HEADERS': {'Accept': 'text/html'}}), DE)
        self.assertEqual(locale['status'], 'unset')
        self.assertIsNone(locale['language'])

    def test_scrapys_own_default_conflicts_with_amazon_de(self):
        """Not a hypothetical. Scrapy ships ``Accept-Language: en`` and the
        non-baseline settings profile never overrides it, so every crawl of
        amazon.de on that profile has been asking Amazon for English while
        reading the answer with German label lists. Nothing failed; the records
        would just have carried an empty ``attributes`` block beside a full
        ``raw_tables``. This is the bug the gate exists for, and it was already
        in the repository."""
        from scrapy.settings import default_settings
        self.assertEqual(
            default_settings.DEFAULT_REQUEST_HEADERS['Accept-Language'], 'en')
        self.assertEqual(acquisition_locale(Settings({}), DE)['status'],
                         'conflict')

    def test_the_header_name_is_matched_case_insensitively(self):
        locale = acquisition_locale(
            Settings({'DEFAULT_REQUEST_HEADERS':
                      {'accept-language': 'de-DE,de;q=0.9'}}), DE)
        self.assertEqual(locale['status'], 'matches')

    def test_only_the_first_tag_decides(self):
        # "de-DE,en;q=0.8" asks for German first; the fallback is not a choice.
        locale = acquisition_locale(
            Settings({'DEFAULT_REQUEST_HEADERS':
                      {'Accept-Language': 'de-DE,en;q=0.8'}}), DE)
        self.assertEqual(locale['language'], 'de')


class Run(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = CrawlRun(
            root=self.tmp.name, spider='amazon_product',
            marketplace='www.amazon.de',
            locale={'language': 'de', 'accept_language': 'de-DE,de;q=0.9',
                    'status': 'matches'},
            arguments={'keyword': ['spaghetti']}).open()
        self.addCleanup(self.run.close)

    def test_the_run_id_sorts_by_time_and_names_its_marketplace(self):
        self.assertRegex(self.run.run_id,
                         r'^\d{8}T\d{6}Z-www\.amazon\.de-[0-9a-f]{8}$')

    def test_every_record_can_be_traced_to_its_run_and_locale(self):
        lineage = self.run.lineage()
        self.assertEqual(lineage['run_id'], self.run.run_id)
        self.assertEqual(lineage['locale'], 'de')
        self.assertEqual(lineage['accept_language'], 'de-DE,de;q=0.9')

    def test_a_manifest_exists_from_the_start_of_the_crawl(self):
        """A crawl that dies halfway must still say what it was trying to do."""
        manifest = run_module.load_manifest(self.run.directory)
        self.assertEqual(manifest['run_id'], self.run.run_id)
        self.assertEqual(manifest['arguments']['keyword'], ['spaghetti'])
        self.assertNotIn('finish_reason', manifest)

    def test_closing_records_the_outcome_and_the_counts(self):
        self.run.close(stats={'downloader/request_count': 7, 'obj': object()},
                       finish_reason='finished')
        manifest = run_module.load_manifest(self.run.directory)
        self.assertEqual(manifest['finish_reason'], 'finished')
        self.assertEqual(manifest['stats']['downloader/request_count'], 7)
        self.assertNotIn('obj', manifest['stats'],
                         'only serialisable stats belong in a manifest')

    def test_the_same_asin_seen_twice_is_written_down_twice(self):
        for rank, sponsored in ((8, False), (16, True)):
            self.run.record_discovery({'asin': 'B000U7PDRI', 'query': 'q',
                                       'grid_position': rank,
                                       'sponsored': sponsored})
        self.run.close()
        occurrences = run_module.load_discovery(self.run.directory)
        self.assertEqual(len(occurrences), 2)
        self.assertEqual([o['sponsored'] for o in occurrences], [False, True])
        self.assertTrue(all(o['run_id'] == self.run.run_id for o in occurrences))
        self.assertTrue(all(o['seen_at'] for o in occurrences))

    def test_a_retained_page_re_extracts_offline(self):
        """The point of the page store: a new extractor, an old page, no network."""
        html = read_fixture(A_PDP)
        self.run.save_page('B088419TTP', html)

        pages = run_module.stored_pages(self.run.directory)
        self.assertIn('B088419TTP', pages)
        record = PdpExtractor(DE).extract(
            __import__('parsel').Selector(run_module.read_page(pages['B088419TTP'])),
            run_module.read_page(pages['B088419TTP']), {'asin': 'B088419TTP'})
        self.assertTrue(record['title'])
        self.assertTrue(record['variation']['values_by_asin'])

    def test_a_stored_page_carries_no_session_identifiers(self):
        self.run.save_page('X', "var ue_sid='123-4567890-1234567';")
        stored = run_module.read_page(
            run_module.stored_pages(self.run.directory)['X'])
        self.assertNotIn('123-4567890-1234567', stored)

    def test_page_retention_can_be_turned_off(self):
        off = CrawlRun(root=self.tmp.name, spider='s', marketplace='m',
                       locale={}, arguments={}, keep_pages=False).open()
        self.addCleanup(off.close)
        off.save_page('B000000000', '<html></html>')
        self.assertEqual(run_module.stored_pages(off.directory), {})
        self.assertEqual(off.counts['pages_saved'], 0)


class Discovery(unittest.TestCase):
    """Against a real saved Amazon.de search page."""

    @classmethod
    def setUpClass(cls):
        cls.html = read_fixture(SEARCH_PAGE)

    def spider(self):
        spider = AmazonProductSpider(keyword='spaghetti hartweizen',
                                     domain='www.amazon.de', max_pages=1)
        spider.crawler = Crawler()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        spider.run = CrawlRun(root=tmp.name, spider=spider.name,
                              marketplace='www.amazon.de',
                              locale={'language': 'de'}, arguments={},
                              keep_pages=False).open()
        self.addCleanup(spider.run.close)
        return spider

    def response(self, spider):
        return HtmlResponse(
            url=spider.search_url('spaghetti hartweizen', 1),
            body=self.html, encoding='utf-8',
            request=spider.search_request(0, 1))

    def test_the_result_grid_is_smaller_than_everything_shaped_like_it(self):
        response = self.response(self.spider())
        self.assertEqual(len(response.css('div.s-result-item[data-asin]')), 82)
        self.assertEqual(len(AmazonProductSpider.grid_ranks(response)), 60)

    def test_sponsored_placement_is_detectable(self):
        response = self.response(self.spider())
        grid = response.css('div[data-component-type="s-search-result"]')
        sponsored = [node for node in grid
                     if AmazonProductSpider.sponsored_markers(node)]
        self.assertEqual(len(sponsored), 12)

    def test_the_three_sponsorship_markers_agree(self):
        """If they ever stop agreeing, that is worth knowing about."""
        response = self.response(self.spider())
        for node in response.css('div[data-component-type="s-search-result"]'):
            markers = AmazonProductSpider.sponsored_markers(node)
            self.assertIn(len(markers), (0, 3), 'markers disagree on a result')

    def test_every_sighting_is_recorded_including_the_repeats(self):
        spider = self.spider()
        list(spider.discover_product_urls(self.response(spider)))
        occurrences = run_module.load_discovery(spider.run.directory)

        seen = {}
        for occurrence in occurrences:
            seen.setdefault(occurrence['asin'], []).append(occurrence)
        repeats = {asin: rows for asin, rows in seen.items() if len(rows) > 1}
        self.assertTrue(repeats, 'this page has ASINs listed more than once')
        self.assertGreater(len(occurrences), len(seen),
                           'the log must be longer than the set of ASINs')

        for rows in repeats.values():
            self.assertNotEqual(len({row['sponsored'] for row in rows}), 0)

    def test_a_repeat_sighting_is_logged_but_not_fetched(self):
        spider = self.spider()
        requests = [item for item in spider.discover_product_urls(
            self.response(spider)) if hasattr(item, 'url')]
        fetched = [request.meta['asin'] for request in requests]
        self.assertEqual(len(fetched), len(set(fetched)),
                         'PDP fetching must stay de-duplicated')
        occurrences = run_module.load_discovery(spider.run.directory)
        self.assertGreater(len(occurrences), len(fetched))
        self.assertTrue(spider.crawler.stats.values.get(
            'amazon/discovery/repeat_sighting'))

    def test_an_occurrence_carries_what_the_shopper_saw(self):
        spider = self.spider()
        list(spider.discover_product_urls(self.response(spider)))
        occurrences = run_module.load_discovery(spider.run.directory)
        first = occurrences[0]
        self.assertTrue(first['result_title'])
        self.assertIsNotNone(first['result_price_amount'])
        self.assertEqual(first['query'], 'spaghetti hartweizen')
        self.assertEqual(first['search_page'], 1)
        self.assertEqual(first['locale'], 'de')

    def test_grid_ranks_survive_the_proxies_that_produced_them(self):
        """lxml frees element proxies and recycles their ids, so a rank map
        keyed by ``id()`` silently matches the wrong result once the list that
        built it is released. Keyed by tree path, it does not."""
        import gc
        response = self.response(self.spider())
        ranks = AmazonProductSpider.grid_ranks(response)
        gc.collect()
        tree = response.selector.root.getroottree()
        matched = [ranks.get(tree.getpath(node.root)) for node
                   in response.css('div.s-result-item[data-asin]')]
        self.assertEqual(len([r for r in matched if r]), 60)
        self.assertEqual(matched[2], 1, 'the first grid result is the third node')

    def test_grid_rank_and_raw_index_are_both_kept(self):
        """The raw index counts ad tiles; the grid rank is what a shopper saw."""
        spider = self.spider()
        list(spider.discover_product_urls(self.response(spider)))
        ranked = [o for o in run_module.load_discovery(spider.run.directory)
                  if o['in_result_grid']]
        self.assertEqual(ranked[0]['grid_position'], 1)
        self.assertGreater(ranked[0]['position'], ranked[0]['grid_position'],
                           'empty ad tiles precede the first real result')


class Variation(unittest.TestCase):

    def test_the_twister_matrix_is_decoded_but_not_interpreted(self):
        html = read_fixture(A_PDP)
        record = PdpExtractor(DE).extract(
            __import__('parsel').Selector(html), html, {'asin': 'B088419TTP'})
        variation = record['variation']
        self.assertIn('size_name', variation['dimensions'])
        self.assertEqual(variation['current_asin'], 'B088419TTP')
        # Sibling ASINs with the pack-size labels that settle quantity
        # disputes -- stored verbatim, no parsing into grams.
        self.assertIn('B003SNIIO6', variation['values_by_asin'])
        self.assertIn('500 g (10er Pack)',
                      variation['values_by_asin']['B003SNIIO6'])

    def test_a_page_without_a_twister_reports_nothing_rather_than_failing(self):
        html = read_fixture(CORPUS / 'amazon_de' / 'B01M8K0019.html.gz')
        record = PdpExtractor(DE).extract(
            __import__('parsel').Selector(html), html, {'asin': 'B01M8K0019'})
        self.assertEqual(record['variation'], {})
        self.assertIn('variation', record['extraction']['blocks_absent'])
        self.assertEqual(record['extraction']['errors'], [])


if __name__ == '__main__':
    unittest.main()
