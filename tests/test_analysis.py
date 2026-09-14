"""Tests for the pasta analysis layer.

Two kinds, for two kinds of bug.

The unit tests build the smallest record that exercises one rule. They pin
down behaviour we designed on purpose.

The case tests run every rule over real records from the validation crawl,
kept in ``cases/pasta_v1.jsonl.gz``. They exist because the rules were not
designed in the abstract: each one was written after a real Amazon page
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

from amazon_scraper.analysis import checks, report  # noqa: E402
from amazon_scraper.analysis.evidence import (  # noqa: E402
    DISPUTED, NOT_CLAIMED, TRUSTED, UNKNOWN, UNVERIFIED, search)
from amazon_scraper.analysis.pasta import evaluate, nutrition  # noqa: E402

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


def nutrition_block(per_100g, rows=(), source='nutrition_card', derived=()):
    return {'source': source, 'per_100g': dict(per_100g),
            'rows': list(rows), 'derived': list(derived)}


class GenericChecks(unittest.TestCase):
    """Rules that need no idea what the product is."""

    def test_unit_that_cannot_measure_the_field_is_rejected(self):
        # "Protein Kalorien 534kcal" matched the protein alias and carried a
        # kcal unit into a field defined in grams.
        values = checks.validate_nutrition(record(food={
            'ingredients': {}, 'allergens': [],
            'nutrition': nutrition_block(
                {'protein_g': 534.0},
                [{'key': 'protein_g', 'label': 'protein', 'amount': 534.0,
                  'unit': 'kcal', 'value_text': 'Protein Kalorien 534kcal'}],
                source='text:aplus')}))
        self.assertEqual(values['protein_g'].status, UNKNOWN)
        self.assertIsNone(values['protein_g'].value)
        self.assertIn('does not measure', values['protein_g'].notes[0])

    def test_number_lifted_out_of_the_basis_phrase_is_rejected(self):
        values = checks.validate_nutrition(record(food={
            'ingredients': {}, 'allergens': [],
            'nutrition': nutrition_block(
                {'fiber_g': 100.0},
                [{'key': 'fiber_g', 'label': 'ballaststoffe', 'amount': 100.0,
                  'unit': 'g', 'value_text': 'Ballaststoffe pro 100g'}],
                source='text:description')}))
        self.assertEqual(values['fiber_g'].status, UNKNOWN)
        self.assertIn('basis phrase', values['fiber_g'].notes[0])

    def test_a_real_100_g_value_survives(self):
        # The guard must not reject "Kohlenhydrate: 100 g pro 100 g Nudeln"
        # style rows purely for containing the number 100 twice.
        values = checks.validate_nutrition(record(food={
            'ingredients': {}, 'allergens': [],
            'nutrition': nutrition_block(
                {'carbohydrates_g': 70.0},
                [{'key': 'carbohydrates_g', 'label': 'kohlenhydrate',
                  'amount': 70.0, 'unit': 'g',
                  'value_text': '70 g pro 100 g'}])}))
        self.assertNotEqual(values['carbohydrates_g'].status, UNKNOWN)

    def test_macronutrients_cannot_outweigh_the_food(self):
        values = checks.validate_nutrition(record(food={
            'ingredients': {}, 'allergens': [],
            'nutrition': nutrition_block(
                {'protein_g': 60.0, 'carbohydrates_g': 60.0, 'fat_g': 10.0})}))
        self.assertEqual(values['protein_g'].status, DISPUTED)
        self.assertIn('more than the food itself', values['protein_g'].notes[0])

    def test_energy_and_macronutrients_must_agree(self):
        values = checks.validate_nutrition(record(food={
            'ingredients': {}, 'allergens': [],
            'nutrition': nutrition_block(
                {'energy_kcal': 84.0, 'protein_g': 15.0,
                 'carbohydrates_g': 65.0, 'fat_g': 2.0})}))
        self.assertIn(checks.CONTRADICTION, values['energy_kcal'].flags)
        self.assertIn(checks.CONTRADICTION, values['protein_g'].flags)

    def test_a_generic_check_cannot_name_the_wrong_side(self):
        """Without plausibility bands nothing may be promoted to trusted."""
        values = checks.validate_nutrition(record(food={
            'ingredients': {}, 'allergens': [],
            'nutrition': nutrition_block(
                {'energy_kcal': 84.0, 'protein_g': 15.0,
                 'carbohydrates_g': 65.0, 'fat_g': 2.0})}))
        checks.resolve_contradictions(values)
        checks.promote(values)
        self.assertNotIn(TRUSTED, {value.status for value in values.values()})

    def test_prose_without_a_stated_basis_is_never_trusted(self):
        values = checks.validate_nutrition(record(food={
            'ingredients': {}, 'allergens': [],
            'nutrition': nutrition_block(
                {'protein_g': 13.0},
                [{'key': 'protein_g', 'label': 'protein', 'amount': 13.0,
                  'unit': 'g', 'value_text': 'Protein 13 g',
                  'basis_confirmed': False}],
                source='text:description')}))
        checks.promote(values)
        self.assertEqual(values['protein_g'].status, UNVERIFIED)
        self.assertIn('per serving', values['protein_g'].notes[0])


class PackQuantity(unittest.TestCase):

    def test_title_multipack_contradicting_the_attribute_table(self):
        value = checks.reconcile_quantity(record(
            title='16x Garofalo Fusilli Packung mit 500g',
            package={'total_quantity_base': 500.0, 'total_quantity_unit': 'g',
                     'total_quantity_source': 'unit_count'}))
        self.assertEqual(value.status, DISPUTED)
        self.assertTrue(any('8000' in e.quote for e in value.evidence))

    def test_pack_size_name_confirming_the_attribute_table(self):
        value = checks.reconcile_quantity(record(
            title='Barilla Penne',
            package={'size_name': '500 g (5er Pack)',
                     'total_quantity_base': 2500.0, 'total_quantity_unit': 'g',
                     'total_quantity_source': 'unit_count'}))
        self.assertEqual(value.status, TRUSTED)

    def test_one_agreeing_hint_outweighs_a_disagreeing_one(self):
        # "(1 x 500 g) (Packung mit 5)": the first phrase describes a unit,
        # the second the pack. Both are hints; only one is about the total.
        value = checks.reconcile_quantity(record(
            title='Barilla Penne Rigate (1 x 500 g) (Packung mit 5)',
            package={'total_quantity_base': 2500.0, 'total_quantity_unit': 'g',
                     'total_quantity_source': 'unit_count'}))
        self.assertEqual(value.status, TRUSTED)

    def test_a_weight_is_not_a_pack_count(self):
        """"Packung mit 500g" states a weight; reading 500 as a count made a
        16-pack into 250 kg of pasta."""
        hints = checks.pack_hints(record(
            title='Garofalo Ditali Packung mit 500g', package={}))
        self.assertEqual(hints, [])

    def test_a_single_unit_pack_says_nothing_about_the_total(self):
        hints = checks.pack_hints(record(
            title='Pasta Mix 250 g', package={'size_name': '1er Pack'}))
        self.assertEqual(hints, [])

    def test_a_count_is_not_multiplied_by_the_attribute_item_weight(self):
        """Whether the attribute weight is per item or per pack is the very
        question under dispute, so it cannot be used to settle it."""
        hints = checks.pack_hints(record(
            title='Afeltra Linguine',
            package={'size_name': '12er Pack', 'item_weight_base': 6000.0}))
        self.assertEqual(hints, [])

    def test_an_item_heavier_than_its_own_package(self):
        value = checks.reconcile_quantity(record(
            title='Paccheri Box 12 Stück',
            package={'item_weight_base': 10000.0, 'package_weight_base': 500.0,
                     'total_quantity_base': 120000.0, 'total_quantity_unit': 'g',
                     'total_quantity_source': 'item_weight_x_count'}))
        self.assertEqual(value.status, DISPUTED)

    def test_no_independent_statement_leaves_it_unverified(self):
        value = checks.reconcile_quantity(record(
            title='Spaghetti', package={'total_quantity_base': 500.0,
                                        'total_quantity_unit': 'g',
                                        'total_quantity_source': 'unit_count'}))
        self.assertEqual(value.status, UNVERIFIED)


class PricePerKg(unittest.TestCase):

    def test_disputed_quantity_disputes_the_price(self):
        data = record(title='16x Garofalo Fusilli Packung mit 500g',
                      price={'amount': 31.28, 'currency': 'EUR'},
                      unit_price={'amount': 62.56, 'unit': 'kg',
                                  'text': '62,56 € pro kg'},
                      package={'total_quantity_base': 500.0,
                               'total_quantity_unit': 'g',
                               'total_quantity_source': 'unit_count'})
        value = checks.price_per_kg(data, checks.reconcile_quantity(data))
        self.assertEqual(value.status, DISPUTED)
        self.assertFalse(value.usable)
        self.assertTrue(any('3.91' in note for note in value.notes),
                        'the price implied by the page itself should be offered')

    def test_a_confirmed_pack_size_beats_amazons_own_unit_price(self):
        data = record(title='Pasta Set 20×500g',
                      price={'amount': 36.31, 'currency': 'EUR'},
                      unit_price={'amount': 36.31, 'unit': 'kg'},
                      package={'total_quantity_base': 10000.0,
                               'total_quantity_unit': 'g',
                               'total_quantity_source': 'item_weight_x_count'})
        value = checks.price_per_kg(data, checks.reconcile_quantity(data))
        self.assertEqual(value.status, TRUSTED)
        self.assertAlmostEqual(value.value, 3.63, places=2)

    def test_two_sources_disagreeing_with_nothing_to_break_the_tie(self):
        data = record(price={'amount': 10.0, 'currency': 'EUR'},
                      unit_price={'amount': 40.0, 'unit': 'kg'},
                      package={'total_quantity_base': 1000.0,
                               'total_quantity_unit': 'g',
                               'total_quantity_source': 'unit_count'})
        value = checks.price_per_kg(data, checks.reconcile_quantity(data))
        self.assertEqual(value.status, DISPUTED)


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
        self.assertEqual(card['raw_materials'].status, TRUSTED)
        self.assertIn('durum_wheat', card['raw_materials'].value)

    def test_raw_material_from_marketing_text_is_unverified(self):
        card = evaluate(record(title='Spaghetti aus Hartweizengrieß'))
        self.assertEqual(card['raw_materials'].status, UNVERIFIED)


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

    def test_known_bad_pack_quantities_are_never_ranked(self):
        for asin in self.DISPUTED_QUANTITY:
            with self.subTest(asin=asin):
                card = self.cards[asin]
                self.assertEqual(card['price_per_kg'].status, DISPUTED)
                self.assertFalse(card['price_per_kg'].usable)
                self.assertTrue(card['price_per_kg'].evidence,
                                'a disputed value must show what contradicts it')

    def test_correct_pack_quantities_are_not_disputed(self):
        for asin in self.CORROBORATED:
            with self.subTest(asin=asin):
                self.assertNotEqual(self.cards[asin]['price_per_kg'].status,
                                    DISPUTED)

    def test_the_garofalo_sixteen_pack_offers_the_right_price(self):
        card = self.cards['B08JLSVW3J']
        self.assertTrue(any('3.91' in note for note in card['price_per_kg'].notes))

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
                values = self.cards[asin]['nutrition']
                for key in wrong:
                    self.assertIn(values[key].status, (DISPUTED, UNVERIFIED),
                                  f'{asin}.{key} must not be presented as fact')
                right = [key for key in ('protein_g', 'fat_g')
                         if key in values and key not in wrong]
                self.assertTrue(
                    any(values[key].status == TRUSTED for key in right),
                    f'{asin}: disputing one value must not condemn the rest')

    def test_a_table_header_parsed_as_a_value_is_dropped(self):
        values = nutrition(self.records['B0BP2QDLPQ'])
        for key in ('fiber_g', 'carbohydrates_g', 'protein_g'):
            self.assertEqual(values[key].status, UNKNOWN)

    def test_a_kcal_figure_in_a_gram_field_is_dropped(self):
        values = checks.validate_nutrition(self.records['B089HJPK5T'])
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
        text = report.compare_text(left, right)
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
