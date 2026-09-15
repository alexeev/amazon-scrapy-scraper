"""Marketplace word boundaries are an opt-in language policy for consumers."""

import re
import unittest

from amazon_scraper.extraction.marketplaces import Marketplace, for_domain


class WordMatching(unittest.TestCase):

    def test_german_accepts_compounds_and_punctuation(self):
        pattern = re.compile(for_domain('amazon.de').word('basmati'), re.I)
        for text in ('BASMATI', 'AKASH Basmatireis 10 kg', '(Basmati-Reis)'):
            with self.subTest(text=text):
                self.assertIsNotNone(pattern.search(text))

    def test_english_requires_a_whole_word(self):
        for host in ('amazon.com', 'amazon.co.uk', 'unknown.example', None):
            pattern = re.compile(for_domain(host).word('basmati'), re.I)
            with self.subTest(host=host):
                self.assertIsNotNone(pattern.search('(BASMATI) rice'))
                self.assertIsNone(pattern.search('Basmatireis'))
                self.assertIsNone(pattern.search('basmatic'))

    def test_both_languages_reject_embedded_stems(self):
        for host in ('amazon.de', 'amazon.com'):
            pattern = re.compile(for_domain(host).word('basmati'), re.I)
            for text in ('superbasmati', 'äbasmati', '1basmati', '_basmati'):
                with self.subTest(host=host, text=text):
                    self.assertIsNone(pattern.search(text))

    def test_stems_are_literal_and_callers_choose_case_sensitivity(self):
        for host in ('amazon.de', 'amazon.com'):
            pattern = re.compile(for_domain(host).word('a.b'))
            with self.subTest(host=host):
                self.assertIsNotNone(pattern.search('(a.b)'))
                self.assertIsNone(pattern.search('axb'))
                self.assertIsNone(pattern.search('A.B'))

    def test_empty_stems_cannot_match_every_listing(self):
        for stem in ('', '  '):
            with self.subTest(stem=stem), self.assertRaises(ValueError):
                for_domain('amazon.de').word(stem)

    def test_policy_follows_profile_language_not_host(self):
        profile = Marketplace('amazon.de', 'en', 'EUR', ',')
        self.assertIsNone(re.search(profile.word('basmati'), 'basmatireis'))
        profile = Marketplace('amazon.com', 'de', 'USD', '.')
        self.assertIsNotNone(re.search(profile.word('basmati'), 'basmatireis'))
        profile = Marketplace('example.test', 'fr', 'EUR', ',')
        self.assertIsNone(re.search(profile.word('basmati'), 'basmatireis'))


if __name__ == '__main__':
    unittest.main()
