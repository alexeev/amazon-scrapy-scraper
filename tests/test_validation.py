"""Tests for the generic validation layer -- the published contract.

Nothing here knows what the product is. Every rule under test fires on a
contradiction visible without domain knowledge, and the tests are written so
that a category cannot be what makes them pass: where a rule needs category
input, the test supplies a :class:`CategoryProfile` explicitly, and there is
a test that the *absence* of one leaves values unpromoted rather than trusted.

Two kinds of test, for two kinds of bug. The unit tests build the smallest
record that exercises one rule. The real-record tests in ``test_analysis.py``
and ``test_mounting_paste.py`` run the same rules over pages Amazon actually
served, which is where every one of them came from.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon_scraper.validation import (  # noqa: E402
    ATTRIBUTES, CONTRACT_VERSION, CategoryProfile, DERIVED, DISPUTED,
    PUBLISHED, STRUCTURED, TEXT, TRUSTED, UNKNOWN, UNVERIFIED, nutrition,
    pricing, quantity, validate)

PASTA_BANDS = {'protein_g': (4.0, 30.0), 'energy_kcal': (280.0, 420.0),
               'energy_kj': (1150.0, 1800.0), 'carbohydrates_g': (35.0, 90.0),
               'fat_g': (0.0, 15.0)}
PASTA = CategoryProfile(key='dry_pasta', label='dry pasta',
                        nutrition_bands=PASTA_BANDS, price_band=(0.80, 40.00))
# A non-food with no bands at all, which is what a new category starts as.
BARE = CategoryProfile(key='thing', label='thing')


def record(**overrides):
    base = {
        'schema_version': 4,
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


def food(per_100g, rows=(), source='nutrition_card', derived=()):
    return {'ingredients': {}, 'allergens': [],
            'nutrition': nutrition_block(per_100g, rows, source, derived)}


class Nutrition(unittest.TestCase):
    """Rules that need no idea what the product is."""

    def test_unit_that_cannot_measure_the_field_is_rejected(self):
        # "Protein Kalorien 534kcal" matched the protein alias and carried a
        # kcal unit into a field defined in grams.
        values = nutrition.validate(record(food=food(
            {'protein_g': 534.0},
            [{'key': 'protein_g', 'label': 'protein', 'amount': 534.0,
              'unit': 'kcal', 'value_text': 'Protein Kalorien 534kcal'}],
            source='text:aplus')))
        self.assertEqual(values['protein_g'].status, UNKNOWN)
        self.assertIsNone(values['protein_g'].value)
        self.assertIn('does not measure', values['protein_g'].notes[0])

    def test_number_lifted_out_of_the_basis_phrase_is_rejected(self):
        values = nutrition.validate(record(food=food(
            {'fiber_g': 100.0},
            [{'key': 'fiber_g', 'label': 'ballaststoffe', 'amount': 100.0,
              'unit': 'g', 'value_text': 'Ballaststoffe pro 100g'}],
            source='text:description')))
        self.assertEqual(values['fiber_g'].status, UNKNOWN)
        self.assertIn('basis phrase', values['fiber_g'].notes[0])

    def test_a_real_100_g_value_survives(self):
        # The guard must not reject "Kohlenhydrate: 100 g pro 100 g Nudeln"
        # style rows purely for containing the number 100 twice.
        values = nutrition.validate(record(food=food(
            {'carbohydrates_g': 70.0, 'protein_g': 12.0},
            [{'key': 'carbohydrates_g', 'label': 'kohlenhydrate',
              'amount': 70.0, 'unit': 'g', 'value_text': '70 g pro 100 g'}])))
        self.assertNotEqual(values['carbohydrates_g'].status, UNKNOWN)

    def test_macronutrients_cannot_outweigh_the_food(self):
        values = nutrition.validate(record(food=food(
            {'protein_g': 60.0, 'carbohydrates_g': 60.0, 'fat_g': 10.0})))
        self.assertEqual(values['protein_g'].status, DISPUTED)
        self.assertIn('more than the food itself', values['protein_g'].notes[0])

    def test_energy_and_macronutrients_must_agree(self):
        values = nutrition.validate(record(food=food(
            {'energy_kcal': 84.0, 'protein_g': 15.0,
             'carbohydrates_g': 65.0, 'fat_g': 2.0})))
        self.assertIn(nutrition.CONTRADICTION, values['energy_kcal'].flags)
        self.assertIn(nutrition.CONTRADICTION, values['protein_g'].flags)

    def test_a_generic_check_cannot_name_the_wrong_side(self):
        """Without plausibility bands nothing may be promoted to trusted."""
        validated = validate(record(food=food(
            {'energy_kcal': 84.0, 'protein_g': 15.0,
             'carbohydrates_g': 65.0, 'fat_g': 2.0})), BARE)
        self.assertNotIn(TRUSTED,
                         {v.status for v in validated.nutrition.values()})

    def test_bands_name_it_and_the_rest_is_released(self):
        """The same record, with a category's bands, resolves cleanly."""
        validated = validate(record(food=food(
            {'energy_kcal': 84.0, 'protein_g': 15.0,
             'carbohydrates_g': 65.0, 'fat_g': 2.0})), PASTA)
        self.assertEqual(validated.nutrition['energy_kcal'].status, DISPUTED)
        self.assertEqual(validated.nutrition['protein_g'].status, TRUSTED)

    def test_prose_without_a_stated_basis_is_never_trusted(self):
        validated = validate(record(food=food(
            {'protein_g': 13.0, 'fat_g': 2.0},
            [{'key': 'protein_g', 'label': 'protein', 'amount': 13.0,
              'unit': 'g', 'value_text': 'Protein 13 g',
              'basis_confirmed': False}],
            source='text:description')), PASTA)
        self.assertEqual(validated.nutrition['protein_g'].status, UNVERIFIED)
        self.assertIn('per serving', validated.nutrition['protein_g'].notes[0])

    def test_a_lone_nutrient_has_nothing_to_confirm_it(self):
        """All thirteen lone-nutrient blocks measured were artefacts.

        The one that forced the rule: "Fett wird in einer 100 g Tube
        geliefert" on a tube of bicycle grease, which states a per-100 g basis
        close enough to satisfy every other check and would otherwise have
        been trusted as 100 g of fat per 100 g.
        """
        validated = validate(record(
            title='Nabenfett Tube 100 g',
            food=food({'fat_g': 100.0},
                      [{'key': 'fat_g', 'label': 'fett', 'amount': 100.0,
                        'unit': 'g', 'value_text': 'Fett wird in einer 100 g',
                        'basis_confirmed': True}],
                      source='text:feature_bullets')), BARE)
        value = validated.nutrition['fat_g']
        self.assertEqual(value.status, UNVERIFIED)
        self.assertIn(nutrition.UNCORROBORATED, value.flags)

    def test_two_nutrients_can_confirm_each_other(self):
        validated = validate(record(food=food(
            {'protein_g': 13.0, 'fat_g': 1.5})), PASTA)
        self.assertEqual(validated.nutrition['protein_g'].status, TRUSTED)


class Sources(unittest.TestCase):
    """`source` says how a value was obtained and never implies it is good."""

    def test_the_structured_card_is_a_source_not_a_confidence(self):
        validated = validate(record(food=food(
            {'protein_g': 534.0, 'fat_g': 2.0})), PASTA)
        value = validated.nutrition['protein_g']
        self.assertEqual(value.source, STRUCTURED)
        self.assertEqual(value.status, DISPUTED)

    def test_prose_carries_the_text_source(self):
        validated = validate(record(food=food(
            {'protein_g': 13.0, 'fat_g': 2.0}, source='text:description')),
            PASTA)
        self.assertEqual(validated.nutrition['protein_g'].source, TEXT)

    def test_a_derived_nutrient_says_so_and_is_never_trusted(self):
        """kcal from kJ converts a single unchecked number and adds nothing."""
        validated = validate(record(food=food(
            {'energy_kj': 1500.0, 'energy_kcal': 358.5, 'protein_g': 13.0},
            derived=('energy_kcal',))), PASTA)
        value = validated.nutrition['energy_kcal']
        self.assertEqual(value.source, DERIVED)
        self.assertNotEqual(value.status, TRUSTED)

    def test_a_derived_price_is_trusted_when_its_inputs_were(self):
        """`derived` is not a blanket disqualification, and must not become one.

        The price per base unit is derived from price and pack size. When the
        pack size was confirmed by an independent statement on the page, the
        quotient is as good as its inputs.
        """
        data = record(title='Reifenmontagepaste 5 kg',
                      price={'amount': 20.0, 'currency': 'EUR'},
                      package={'total_quantity_base': 5000.0,
                               'total_quantity_unit': 'g',
                               'total_quantity_source': 'item_weight'})
        value = validate(data, BARE).price_per_base
        self.assertEqual(value.source, DERIVED)
        self.assertEqual(value.status, TRUSTED)

    def test_the_pack_quantity_comes_from_the_attribute_table(self):
        validated = validate(record(package={
            'total_quantity_base': 500.0, 'total_quantity_unit': 'g',
            'total_quantity_source': 'unit_count'}), BARE)
        self.assertEqual(validated.quantity.source, ATTRIBUTES)

    def test_the_price_is_amazons_own_figure(self):
        self.assertEqual(validate(record(), BARE).price.source, PUBLISHED)


class PackQuantity(unittest.TestCase):

    def test_title_multipack_contradicting_the_attribute_table(self):
        value = quantity.reconcile(record(
            title='16x Garofalo Fusilli Packung mit 500g',
            package={'total_quantity_base': 500.0, 'total_quantity_unit': 'g',
                     'total_quantity_source': 'unit_count'}))
        self.assertEqual(value.status, DISPUTED)
        self.assertTrue(any('8000' in e.quote for e in value.evidence))

    def test_pack_size_name_confirming_the_attribute_table(self):
        value = quantity.reconcile(record(
            title='Barilla Penne',
            package={'size_name': '500 g (5er Pack)',
                     'total_quantity_base': 2500.0, 'total_quantity_unit': 'g',
                     'total_quantity_source': 'unit_count'}))
        self.assertEqual(value.status, TRUSTED)

    def test_one_agreeing_hint_outweighs_a_disagreeing_one(self):
        # "(1 x 500 g) (Packung mit 5)": the first phrase describes a unit,
        # the second the pack. Both are hints; only one is about the total.
        value = quantity.reconcile(record(
            title='Barilla Penne Rigate (1 x 500 g) (Packung mit 5)',
            package={'total_quantity_base': 2500.0, 'total_quantity_unit': 'g',
                     'total_quantity_source': 'unit_count'}))
        self.assertEqual(value.status, TRUSTED)

    def test_a_weight_is_not_a_pack_count(self):
        """"Packung mit 500g" states a weight; reading 500 as a count made a
        16-pack into 250 kg of pasta."""
        hints = quantity.pack_hints(record(
            title='Garofalo Ditali Packung mit 500g', package={}))
        self.assertEqual(hints, [])

    def test_a_single_unit_pack_says_nothing_about_the_total(self):
        hints = quantity.pack_hints(record(
            title='Pasta Mix 250 g', package={'size_name': '1er Pack'}))
        self.assertEqual(hints, [])

    def test_a_count_is_not_multiplied_by_the_attribute_item_weight(self):
        """Whether the attribute weight is per item or per pack is the very
        question under dispute, so it cannot be used to settle it."""
        hints = quantity.pack_hints(record(
            title='Afeltra Linguine',
            package={'size_name': '12er Pack', 'item_weight_base': 6000.0}))
        self.assertEqual(hints, [])

    def test_an_item_heavier_than_its_own_package(self):
        value = quantity.reconcile(record(
            title='Paccheri Box 12 Stück',
            package={'item_weight_base': 10000.0, 'package_weight_base': 500.0,
                     'total_quantity_base': 120000.0, 'total_quantity_unit': 'g',
                     'total_quantity_source': 'item_weight_x_count'}))
        self.assertEqual(value.status, DISPUTED)

    def test_no_independent_statement_leaves_it_unverified(self):
        value = quantity.reconcile(record(
            title='Spaghetti', package={'total_quantity_base': 500.0,
                                        'total_quantity_unit': 'g',
                                        'total_quantity_source': 'unit_count'}))
        self.assertEqual(value.status, UNVERIFIED)

    def test_a_bare_weight_confirms_a_listing_that_claims_one_unit(self):
        """The rule the second category needed: "Reifenmontagepaste 5 kg"."""
        value = quantity.reconcile(record(
            title='HASKYY Reifenmontagepaste 5 kg Weiß',
            package={'total_quantity_base': 5000.0, 'total_quantity_unit': 'g',
                     'total_quantity_source': 'item_weight'}))
        self.assertEqual(value.status, TRUSTED)

    def test_a_bare_weight_is_ignored_when_anything_claims_a_multipack(self):
        self.assertEqual(quantity.single_unit_weights(record(
            title='Garofalo Fusilli 500g', package={'size_name': '16er Pack'})),
            [])

    def test_a_bare_weight_may_confirm_but_never_contradict(self):
        """A kit whose shipping weight is not its paste content stays
        unverified rather than becoming disputed."""
        value = quantity.reconcile(record(
            title='Stix ZW10 Reifenmontage Set 7-TLG mit 5 kg Montagepaste',
            package={'total_quantity_base': 9000.0, 'total_quantity_unit': 'g',
                     'total_quantity_source': 'item_weight'}))
        self.assertEqual(value.status, UNVERIFIED)


class Pricing(unittest.TestCase):

    def test_a_price_range_is_unknown_and_says_what_it_saw(self):
        """Neither end of a range is what this ASIN costs.

        Reported by a reader who opened the recommended listing and found
        that no size selection produced the price the report quoted. The
        extractor now hands the range over intact; this layer must refuse to
        rank on it without throwing away the one figure the page does state.
        """
        data = record(title='Montagefluid Easy Fit',
                      price={'currency': 'EUR', 'text': '5,63€ - 26,15€',
                             'range': [5.63, 26.15]})
        value = validate(data, PASTA).price
        self.assertEqual(value.status, UNKNOWN)
        self.assertFalse(value.usable)
        self.assertTrue(any('5.63-26.15' in note for note in value.notes),
                        'the range itself should survive into the note')
        self.assertEqual(value.evidence[0].quote, '5,63€ - 26,15€')

    def test_a_range_leaves_no_price_per_kilogram_behind(self):
        """The derivation must not quietly use an end of the range."""
        data = record(title='Montagefluid Easy Fit 50 ml',
                      price={'currency': 'EUR', 'text': '5,63€ - 26,15€',
                             'range': [5.63, 26.15]},
                      package={'total_quantity_base': 50.0,
                               'total_quantity_unit': 'ml',
                               'total_quantity_source': 'unit_count'})
        self.assertIsNone(validate(data, PASTA).price_per_base.value)

    def test_disputed_quantity_disputes_the_price(self):
        data = record(title='16x Garofalo Fusilli Packung mit 500g',
                      price={'amount': 31.28, 'currency': 'EUR'},
                      unit_price={'amount': 62.56, 'unit': 'kg',
                                  'text': '62,56 € pro kg'},
                      package={'total_quantity_base': 500.0,
                               'total_quantity_unit': 'g',
                               'total_quantity_source': 'unit_count'})
        value = validate(data, PASTA).price_per_base
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
        value = validate(data, PASTA).price_per_base
        self.assertEqual(value.status, TRUSTED)
        self.assertAlmostEqual(value.value, 3.63, places=2)

    def test_two_sources_disagreeing_with_nothing_to_break_the_tie(self):
        data = record(price={'amount': 10.0, 'currency': 'EUR'},
                      unit_price={'amount': 40.0, 'unit': 'kg'},
                      package={'total_quantity_base': 1000.0,
                               'total_quantity_unit': 'g',
                               'total_quantity_source': 'unit_count'})
        self.assertEqual(validate(data, PASTA).price_per_base.status, DISPUTED)

    def test_a_pack_in_millilitres_reconciles_to_a_price_per_litre(self):
        """The one generalisation the second category forced."""
        data = record(title='Schwalbe Easy Fit 50 ml',
                      price={'amount': 7.49, 'currency': 'EUR'},
                      unit_price={'amount': 149.8, 'unit': 'l',
                                  'text': '149,80 € pro l'},
                      package={'total_quantity_base': 50.0,
                               'total_quantity_unit': 'ml',
                               'total_quantity_source': 'volume'})
        value = validate(data, BARE).price_per_base
        self.assertEqual(value.unit, 'EUR/l')
        self.assertEqual(value.status, TRUSTED)

    def test_a_published_price_per_100_ml_is_converted_not_ignored(self):
        amount, note = pricing.published_per_base(
            {'amount': 1.5, 'unit': '100 ml'}, 'l')
        self.assertEqual(amount, 15.0)
        self.assertEqual(note, '')

    def test_a_price_per_piece_is_refused_rather_than_misread(self):
        """Reading a per-piece figure as content priced a Barilla listing at
        38.56 EUR/kg."""
        amount, note = pricing.published_per_base(
            {'amount': 3.86, 'unit': 'stück'}, 'kg')
        self.assertIsNone(amount)
        self.assertIn('counts pieces', note)

    def test_a_volume_price_cannot_check_a_mass_pack(self):
        amount, note = pricing.published_per_base({'amount': 10.0, 'unit': 'l'},
                                                  'kg')
        self.assertIsNone(amount)
        self.assertIn('density', note)

    def test_an_unrecognised_unit_is_never_guessed_at(self):
        amount, note = pricing.published_per_base(
            {'amount': 2.0, 'unit': 'waschgang'}, 'kg')
        self.assertIsNone(amount)

    def test_the_price_band_is_category_data_not_a_built_in(self):
        data = record(title='Geschenkkorb Pasta 200 g',
                      price={'amount': 89.0, 'currency': 'EUR'},
                      package={'total_quantity_base': 200.0,
                               'total_quantity_unit': 'g',
                               'total_quantity_source': 'unit_count'})
        self.assertEqual(validate(data, PASTA).price_per_base.status, DISPUTED)
        self.assertNotEqual(validate(data, BARE).price_per_base.status, DISPUTED)


class Contract(unittest.TestCase):

    def test_a_record_with_no_food_block_gets_no_nutrition(self):
        validated = validate(record(title='Reifenmontagepaste 5 kg',
                                    food={}), BARE)
        self.assertEqual(validated.nutrition, {})

    def test_the_validated_record_serialises(self):
        import json
        data = validate(record(package={'total_quantity_base': 500.0,
                                        'total_quantity_unit': 'g',
                                        'total_quantity_source': 'unit_count'}),
                        PASTA).as_dict()
        self.assertEqual(data['contract_version'], CONTRACT_VERSION)
        self.assertEqual(data['category_profile'], 'dry_pasta')
        self.assertEqual(data['quantity']['source'], ATTRIBUTES)
        json.dumps(data)

    def test_every_value_names_a_status_from_the_vocabulary(self):
        from amazon_scraper.validation import STATUSES
        validated = validate(record(food=food({'protein_g': 13.0,
                                               'fat_g': 2.0})), PASTA)
        for value in ([validated.quantity, validated.price,
                       validated.price_per_base]
                      + list(validated.nutrition.values())):
            self.assertIn(value.status, STATUSES)

    def test_a_profile_cannot_reach_into_the_pipeline(self):
        """A profile is data. Everything on it is a band or a label."""
        import dataclasses
        fields = {f.name for f in dataclasses.fields(CategoryProfile)}
        self.assertEqual(fields, {'key', 'label', 'nutrition_bands',
                                  'price_band'})


if __name__ == '__main__':
    unittest.main()
