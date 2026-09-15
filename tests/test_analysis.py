"""Tests for the dry-pasta category analyzer.

The generic rules it rests on are tested in ``test_validation.py``; what is
here is what only a pasta layer can be wrong about -- classification, raw
material, the quality claims, and the plausibility bands it hands to the
generic layer.

The case tests run the whole thing over real records from the validation
crawl, kept in ``cases/pasta_v1.jsonl.gz``. They exist because the rules were
not designed in the abstract: each one was written after a real Amazon page
produced a confidently wrong number, and an earlier version of the reconciler
disputed five correct records before the evidence rules were narrowed. Both
directions need guarding, so the cases assert the false-positive guards as
loudly as the true positives.
"""

import gzip
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon_scraper.analysis import report  # noqa: E402
from amazon_scraper.analysis.categories.dry_pasta import (  # noqa: E402
    CATEGORY, evaluate)
from amazon_scraper.validation import (  # noqa: E402
    DISPUTED, NOT_CLAIMED, TRUSTED, UNKNOWN, UNVERIFIED, nutrition as
    generic_nutrition, search, validate)

CASES = pathlib.Path(__file__).resolve().parent / 'cases' / 'pasta_v1.jsonl.gz'


def load_cases():
    with gzip.open(CASES, 'rt', encoding='utf-8') as handle:
        return {record['asin']: record for record in map(json.loads, handle)}


def record(**overrides):
    """A minimal dry-pasta record with everything the analysis reads."""
    base = {
        'asin': 'B000000000',
        'title': 'Spaghetti',
        'brand': 'Test',
        'product_url': 'https://www.amazon.de/dp/B000000000',
        'search_query': 'spaghetti',
        'breadcrumbs': ['Lebensmittel & Getränke', 'Nudeln & Pasta'],
        'price': {'amount': 2.0, 'currency': 'EUR'},
        'unit_price': {},
        'package': {},
        'raw_tables': {},
        'content': {'feature_bullets': [], 'description': '',
                    'important_information': [], 'aplus': {}},
        'food': {'ingredients': {}, 'allergens': [], 'nutrition': {}},
    }
    base.update(overrides)
    return base


def pasta_nutrition(rec):
    """The nutrition the category sees, i.e. validated against its bands."""
    return validate(rec, CATEGORY.profile).nutrition


class Classification(unittest.TestCase):

    def test_a_cleaning_brush_is_not_pasta(self):
        card = evaluate(record(title='Fugenbürste',
                               breadcrumbs=['Küche, Haushalt & Wohnen',
                                            'Badausstattung', 'Badaccessoires']))
        self.assertEqual(card['category'].value, 'other')

    def test_chilled_pasta_is_not_dry_pasta(self):
        card = evaluate(record(breadcrumbs=['Lebensmittel & Getränke',
                                            'Kühlprodukte', 'Gekühlte Pasta']))
        self.assertEqual(card['category'].value, 'other')

    def test_no_breadcrumbs_is_unclassified_not_excluded(self):
        card = evaluate(record(breadcrumbs=[]))
        self.assertEqual(card['category'].status, UNKNOWN)

    def test_raw_material_from_the_declaration_is_trusted(self):
        card = evaluate(record(food={
            'ingredients': {'text': 'HARTWEIZENGRIESS, Wasser'},
            'allergens': [], 'nutrition': {}}))
        self.assertEqual(card['axes']['raw_materials'].status, TRUSTED)
        self.assertIn('durum_wheat', card['axes']['raw_materials'].value)

    def test_raw_material_from_marketing_text_is_unverified(self):
        card = evaluate(record(title='Spaghetti aus Hartweizengrieß'))
        self.assertEqual(card['axes']['raw_materials'].status, UNVERIFIED)


class Claims(unittest.TestCase):

    def test_a_claim_carries_the_sentence_it_came_from(self):
        card = evaluate(record(content={
            'feature_bullets': ['Bronze gezogen und langsam getrocknet.'],
            'description': '', 'important_information': [], 'aplus': {}}))
        self.assertEqual(card['claims']['bronze_die'].status, TRUSTED)
        self.assertIn('Bronze', card['claims']['bronze_die'].evidence[0].quote)

    def test_an_absent_claim_is_not_claimed_rather_than_false(self):
        card = evaluate(record())
        self.assertEqual(card['claims']['bronze_die'].status, NOT_CLAIMED)

    def test_gragnano_needs_the_protected_designation_too(self):
        plain = evaluate(record(title='Pasta aus Gragnano'))
        self.assertEqual(plain['claims']['gragnano_igp'].status, NOT_CLAIMED)
        protected = evaluate(record(title='Pasta di Gragnano IGP Fusilli'))
        self.assertEqual(protected['claims']['gragnano_igp'].status, TRUSTED)

    def test_a_pure_durum_claim_the_ingredients_contradict(self):
        card = evaluate(record(
            title='100% Hartweizen Pasta',
            food={'ingredients': {'text': 'Kichererbsenmehl, Wasser'},
                  'allergens': [], 'nutrition': {}}))
        self.assertEqual(card['claims']['pure_durum'].status, DISPUTED)

    def test_evidence_quotes_are_readable_not_whole_blobs(self):
        blob = ('Lorem ipsum. ' * 40) + 'Trafilata al bronzo. ' + ('dolor sit. ' * 40)
        found = search(record(content={'feature_bullets': [], 'description': blob,
                                       'important_information': [], 'aplus': {}}),
                       r'bronzo')
        self.assertTrue(found)
        self.assertLess(len(found[0].quote), 200)


class ContractUse(unittest.TestCase):
    """The category must inherit trust, not re-derive it."""

    def test_the_axes_are_the_validated_values_themselves(self):
        rec = record(package={'size_name': '500 g (5er Pack)',
                              'total_quantity_base': 2500.0,
                              'total_quantity_unit': 'g',
                              'total_quantity_source': 'unit_count'})
        card = evaluate(rec)
        validated = card['validated']
        self.assertIs(card['axes']['quantity'], validated.quantity)
        self.assertIs(card['axes']['price_per_base'], validated.price_per_base)

    def test_the_module_never_names_a_status_of_its_own_for_a_number(self):
        """The category may classify and claim; it may not decide whether a
        *measured* value survived.

        The plausibility bands are still here -- they are category knowledge --
        but they are handed over as data on a profile, and the ordering that
        makes them work lives in the contract. Before R2 these four names were
        all called from this module, and the ordering comment above them was
        the only specification a second category would have had.
        """
        source = (pathlib.Path(__file__).resolve().parent.parent /
                  'amazon_scraper' / 'analysis' / 'categories' /
                  'dry_pasta.py').read_text(encoding='utf-8')
        # `check_claim_consistency` may dispute a *claim*; nothing may touch
        # the numeric pipeline.
        body = source.split('def check_claim_consistency')[0]
        self.assertNotIn('.dispute(', body)
        for forbidden in ('promote(', 'resolve_contradictions(',
                          'apply_bands(', 'reconcile('):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class RealCases(unittest.TestCase):
    """Every rule, against the records that made it necessary."""

    @classmethod
    def setUpClass(cls):
        cls.records = load_cases()
        cls.cards = {asin: evaluate(rec) for asin, rec in cls.records.items()}

    DISPUTED_QUANTITY = ('B08JLSVW3J', 'B08HQSZR3D', 'B0173KFFIG', 'B0BG28G6SZ',
                         'B0C3WCFKHT', 'B0C5XK2QFR', 'B0BTPZ7TXJ', 'B0GQ5BKHPT')
    CORROBORATED = ('B0CH3MHVF8', 'B08BNQ2D54', 'B0D4R7K82Q', 'B0C2VN9NCD',
                    'B00XUMS46W', 'B0G6D354JV')

    def price(self, asin):
        return self.cards[asin]['axes']['price_per_base']

    def test_known_bad_pack_quantities_are_never_ranked(self):
        for asin in self.DISPUTED_QUANTITY:
            with self.subTest(asin=asin):
                price = self.price(asin)
                self.assertEqual(price.status, DISPUTED)
                self.assertFalse(price.usable)
                self.assertTrue(price.evidence,
                                'a disputed value must show what contradicts it')

    def test_correct_pack_quantities_are_not_disputed(self):
        for asin in self.CORROBORATED:
            with self.subTest(asin=asin):
                self.assertNotEqual(self.price(asin).status, DISPUTED)

    def test_the_garofalo_sixteen_pack_offers_the_right_price(self):
        self.assertTrue(any('3.91' in note
                            for note in self.price('B08JLSVW3J').notes))

    def test_implausible_nutrition_is_never_trusted(self):
        expected = {
            # a mistyped kJ column: the energy is wrong, the macros are not
            'B0C3WCFKHT': ('energy_kj', 'energy_kcal'),
            'B0FWXQ6NWM': ('energy_kj', 'energy_kcal'),
            'B0FWXCDCYV': ('energy_kj', 'energy_kcal'),
            'B07NZ1K8L3': ('energy_kj', 'energy_kcal'),
            # 7 g of carbohydrate in dry pasta: the macro is wrong, not energy
            'B086K1MFSL': ('carbohydrates_g',),
        }
        for asin, wrong in expected.items():
            with self.subTest(asin=asin):
                values = pasta_nutrition(self.records[asin])
                for key in wrong:
                    self.assertIn(values[key].status, (DISPUTED, UNVERIFIED),
                                  f'{asin}.{key} must not be presented as fact')
                right = [key for key in ('protein_g', 'fat_g')
                         if key in values and key not in wrong]
                self.assertTrue(
                    any(values[key].status == TRUSTED for key in right),
                    f'{asin}: disputing one value must not condemn the rest')

    def test_a_table_header_parsed_as_a_value_is_dropped(self):
        values = pasta_nutrition(self.records['B0BP2QDLPQ'])
        for key in ('fiber_g', 'carbohydrates_g', 'protein_g'):
            self.assertEqual(values[key].status, UNKNOWN)

    def test_a_kcal_figure_in_a_gram_field_is_dropped(self):
        values = generic_nutrition.validate(self.records['B089HJPK5T'])
        self.assertEqual(values['protein_g'].status, UNKNOWN)

    def test_search_results_that_are_not_pasta_are_excluded(self):
        for asin in ('B0CZ473RQT', '3969301173'):
            with self.subTest(asin=asin):
                self.assertEqual(self.cards[asin]['category'].value, 'other')

    def test_every_record_is_classified_one_way_or_the_other(self):
        for asin, card in self.cards.items():
            with self.subTest(asin=asin):
                self.assertIn(card['category'].status, (TRUSTED, UNKNOWN))

    def test_clean_records_produce_a_usable_comparison(self):
        left, right = self.cards['B08WJGD5Z5'], self.cards['B0DQ2N5HRW']
        text = ' '.join(report.compare_text(left, right).split())
        self.assertIn('Differences', text)
        self.assertIn('cheaper per kilogram', text)

    def test_a_disputed_product_refuses_to_be_compared_on_that_axis(self):
        text = report.compare_text(self.cards['B08JLSVW3J'],
                                   self.cards['B08WJGD5Z5'])
        self.assertIn('Cannot be compared', text)
        self.assertIn('Price per kg', text.split('Cannot be compared')[1])

    def test_every_card_renders(self):
        for asin, card in self.cards.items():
            with self.subTest(asin=asin):
                self.assertTrue(report.card_text(card))
                json.dumps(report.card_json(card))


if __name__ == '__main__':
    unittest.main()
