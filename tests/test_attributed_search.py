"""Shared discovery/attribution policy, independent of any product category."""

import re
import unittest

from amazon_scraper.validation import Evidence, search, validate


class SearchScope(unittest.TestCase):
    def setUp(self):
        self.record = {
            'title': 'Title signal',
            'food': {'ingredients': {'text': 'Ingredient signal'}},
            'raw_tables': {'Type': 'Attribute signal'},
            'content': {
                'feature_bullets': ['Bullet signal'],
                'description': 'Description signal',
                'important_information': [{'heading': 'Use', 'text': 'Info signal'}],
                'aplus': {'text': 'Comparison signal'},
            },
            'reviews': {'sample': [{'text': 'Buyer-only phrase'}]},
        }

    def test_default_preserves_discovery_and_field_order(self):
        hits = search(self.record, 'signal', limit=20)
        self.assertEqual([hit.field for hit in hits], [
            'food.ingredients', 'title', 'content.feature_bullets[0]',
            'content.description', 'raw_tables.Type',
            'content.important_information[0]', 'content.aplus'])
        self.assertEqual(hits, search(self.record, 'signal', 20, scope='page'))
        self.assertEqual(search(self.record, 'Buyer-only'), [])

    def test_self_excludes_marketing_and_comparisons(self):
        hits = search(self.record, 'signal', limit=20, scope='self')
        self.assertEqual([hit.field for hit in hits],
                         ['food.ingredients', 'title', 'raw_tables.Type'])

    def test_fields_intersect_scope_and_match_paths_not_prefixes(self):
        self.assertEqual(search(self.record, 'signal', scope='self',
                                fields=('content',)), [])
        self.assertEqual(search(self.record, 'signal', fields=('raw_table',)), [])
        self.assertEqual(search(self.record, 'signal', scope='self',
                                fields=('raw_tables.Type',)),
                         [Evidence('raw_tables.Type', 'Type: Attribute signal')])
        self.assertEqual(search(self.record, 'signal', fields=()), [])

    def test_validated_exposes_the_same_policy(self):
        self.record['title'] = 'Non-parboiled. Parboiled rice.'
        args = dict(scope='self', affirmative=True, fields=('title',), limit=1,
                    exclude='Non-parboiled')
        self.assertEqual(validate(self.record).search('parboiled', **args),
                         search(self.record, 'parboiled', **args))
        self.assertEqual(len(search(self.record, 'parboiled', **args)), 1)

    def test_invalid_scope_fails_instead_of_widening_search(self):
        with self.assertRaises(ValueError):
            search({}, 'signal', scope='sef')

    def test_nonpositive_limit_returns_no_hits(self):
        for limit in (0, -1):
            self.assertEqual(search(self.record, 'signal', limit=limit), [])


class MatchPolarity(unittest.TestCase):
    def test_discovery_preserves_negated_mentions(self):
        record = {'title': 'Non-parboiled rice'}
        self.assertTrue(search(record, 'parboiled'))
        self.assertFalse(search(record, 'parboiled', affirmative=True))

    def test_prefix_negation_in_both_languages(self):
        for prefix in ('Non-', 'non\u2011', 'nicht ', 'kein ', 'keinen ',
                       'ohne ', 'no ', 'not ', 'without ', 'free of ',
                       'free from ', 'frei von '):
            with self.subTest(prefix=prefix):
                self.assertEqual(search({'title': prefix + 'parboiled'},
                                        'parboiled', affirmative=True), [])

    def test_free_suffix_denies_presence_but_affirms_absence(self):
        for text, presence in [('mineralölfrei', 'mineralöl'),
                               ('mineral oil-free', 'mineral oil'),
                               ('solvent free', 'solvent')]:
            with self.subTest(text=text):
                self.assertEqual(search({'title': text}, presence,
                                        affirmative=True), [])
                self.assertEqual(search({'title': text}, re.escape(text),
                                        affirmative=True), [Evidence('title', text)])

    def test_negation_inside_claim_does_not_reverse_its_meaning(self):
        for text in ('ohne Mineralöl', 'frei von Mineralöl', 'free of mineral oil',
                     'greift Gummi nicht an'):
            with self.subTest(text=text):
                self.assertEqual(search({'title': text}, re.escape(text),
                                        affirmative=True), [Evidence('title', text)])
        self.assertEqual(search({'title': 'nicht mineralölfrei'}, 'mineralölfrei',
                                affirmative=True), [])

    def test_later_affirmation_survives_in_the_same_field_before_limit(self):
        text = 'Non-parboiled. Nicht parboiled. Parboiled rice.'
        hits = search({'title': text}, re.compile('parboiled', re.I),
                      limit=1, affirmative=True)
        self.assertEqual(len(hits), 1)
        self.assertIn('Parboiled rice.', hits[0].quote)
        self.assertNotIn('Non-parboiled', hits[0].quote)

    def test_filtering_precedes_quote_cropping(self):
        # Extracted layout whitespace can put the negator outside the quote.
        text = 'without ' + ' ' * 210 + 'mineral oil'
        self.assertEqual(search({'title': text}, 'mineral oil',
                                affirmative=True), [])

    def test_exclusion_only_rejects_overlapping_matches(self):
        text = 'Trocknet nicht ein im Eimer, trocknet schnell ab am Reifen.'
        hits = search({'title': text}, r'trocknet\s+(?:\w+\s+){0,2}(?:ein|ab)',
                      affirmative=True, exclude=r'trocknet nicht ein', limit=1)
        self.assertEqual(hits, [Evidence('title', text)])
        self.assertEqual(search({'title': 'Trocknet nicht ein'}, r'trocknet.*ein',
                                exclude=re.compile(r'trocknet nicht ein', re.I)), [])

    def test_unrelated_negation_does_not_veto_affirmation(self):
        for text in ('Not only parboiled', 'ohne Salz, parboiled',
                     'Non-parboiled alternative. Parboiled rice.'):
            self.assertTrue(search({'title': text}, 'parboiled', affirmative=True))

    def test_one_quote_per_field_and_limit_counts_accepted_fields(self):
        record = {'title': 'Non-parboiled', 'content': {
            'feature_bullets': ['not parboiled'] * 8 + ['Parboiled. Parboiled.'],
            'description': 'Parboiled'}}
        hits = search(record, 'parboiled', affirmative=True, limit=2)
        self.assertEqual([hit.field for hit in hits],
                         ['content.feature_bullets[8]', 'content.description'])


if __name__ == '__main__':
    unittest.main()
