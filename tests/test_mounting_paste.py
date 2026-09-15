"""Tests for the tyre mounting paste category -- and for the contract it uses.

This suite has a second job the pasta one does not. R2's completion criterion
is that *a second category analyzer consumes the contract without re-deriving
trust rules*, so the tests below assert that as directly as they can: the
axes on a card are the very objects the validation layer produced, the module
never names a status for a measured value, and nothing in it imports a rule.

The cases are 29 records taken verbatim from a 90-record Amazon.de crawl for
"reifenmontagepaste", "montagepaste reifen motorrad" and "reifen montagepaste
fahrrad". The same searches return carbon assembly paste (a *friction* paste),
anti-seize, bearing grease, tubeless sealant, wheel weights and a tyre-pressure
gauge, so classification carries as much weight here as it does for pasta --
and it cannot use breadcrumbs, which scatter the category across four
unrelated Amazon departments.
"""

import gzip
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon_scraper.analysis import report  # noqa: E402
from amazon_scraper.analysis.categories.mounting_paste import (  # noqa: E402
    CATEGORY, KEY, classify, evaluate)
from amazon_scraper.validation import (  # noqa: E402
    NOT_CLAIMED, TRUSTED, UNKNOWN, UNVERIFIED, nutrition)

CASES = pathlib.Path(__file__).resolve().parent / 'cases' / 'mounting_paste_v1.jsonl.gz'
MODULE = (pathlib.Path(__file__).resolve().parent.parent / 'amazon_scraper' /
          'analysis' / 'categories' / 'mounting_paste.py')


def load_cases():
    with gzip.open(CASES, 'rt', encoding='utf-8') as handle:
        return {record['asin']: record for record in map(json.loads, handle)}


class Classification(unittest.TestCase):
    """Decided on the title, because the breadcrumbs cannot do it.

    Measured over the 90-record crawl: the pastes are filed under "Auto &
    Motorrad" (49), "Sport & Freizeit" (31) and "Baumarkt" (9), and so is
    everything the searches return that is not a paste -- including one
    filed under "Reifendichtmittel", the product class it most needs to be
    told apart from.
    """

    def name(self, title):
        return classify({'title': title}).value

    def test_a_plain_mounting_paste_is_one(self):
        self.assertEqual(self.name('KS Tools Reifenmontagepaste 5 kg, gelb'), KEY)

    def test_a_mounting_fluid_is_the_same_product_class(self):
        self.assertEqual(
            self.name('Schwalbe Easy Fit Montageflüssigkeit – 50 ml'), KEY)

    def test_carbon_assembly_paste_is_the_opposite_product(self):
        """It is sold to *increase* friction between seatpost and frame."""
        self.assertEqual(
            self.name("Peaty's Max Grip Carbon Montagepaste - Carbon Paste"),
            'other')

    def test_anti_seize_is_designed_never_to_dry(self):
        self.assertEqual(
            self.name('WEICON Anti-Seize Montagepaste 120 g'), 'other')

    def test_a_kit_is_still_paste_when_the_tools_come_after_it(self):
        self.assertEqual(self.name(
            'HASKYY 5kg Reifenmontagepaste Montagepaste Schwarz Reifenmontage '
            'Set inkl. Ventildreher, Profi Auswuchtzange'), KEY)

    def test_an_accessory_named_before_the_paste_is_an_accessory(self):
        self.assertEqual(
            self.name('HASKYY 1 Pinsel Reifenmontagepaste Montagepaste 22 cm'),
            'other')

    def test_for_makes_the_following_noun_the_purpose_not_the_product(self):
        self.assertEqual(
            self.name('BGS 4803 | Rundpinsel für Reifenmontagepaste'), 'other')
        self.assertEqual(
            self.name('BGS 8901-1 | Montagepaste für Reifen-Reparaturstopfen'),
            'other')

    def test_a_listing_with_no_title_is_unclassified_not_excluded(self):
        self.assertEqual(classify({'title': ''}).status, UNKNOWN)


class ContractUse(unittest.TestCase):
    """The criterion R2 is finished against."""

    def setUp(self):
        self.card = evaluate(load_cases()['B0GNMRKPGQ'])

    def test_every_axis_is_a_value_the_validation_layer_produced(self):
        validated = self.card['validated']
        self.assertIs(self.card['axes']['quantity'], validated.quantity)
        self.assertIs(self.card['axes']['price'], validated.price)
        self.assertIs(self.card['axes']['price_per_base'],
                      validated.price_per_base)

    # Everything a category may take from the validation layer: the entry
    # point, the shapes it returns, and the words for talking about them.
    ALLOWED = {'CategoryProfile', 'Validated', 'Value', 'Evidence', 'validate',
               'search', 'TRUSTED', 'DISPUTED', 'UNVERIFIED', 'UNKNOWN',
               'NOT_CLAIMED', 'STRUCTURED', 'ATTRIBUTES', 'TEXT', 'PUBLISHED',
               'DERIVED', 'CONTRACT_VERSION'}

    def imported_from_validation(self):
        import ast
        tree = ast.parse(MODULE.read_text(encoding='utf-8'))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and 'validation' in (node.module or ''):
                names.update(alias.name for alias in node.names)
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names
                             if 'validation' in alias.name)
        return names

    def test_the_category_imports_the_contract_and_no_rule(self):
        """It may import the contract and the vocabulary; nothing else.

        Importing ``validation.quantity`` or ``validation.nutrition`` would
        mean the category had reached past the contract into the rules, which
        is the thing R2 exists to make unnecessary.
        """
        self.assertTrue(self.imported_from_validation() <= self.ALLOWED,
                        self.imported_from_validation() - self.ALLOWED)

    def test_the_category_never_settles_a_numeric_value_itself(self):
        source = MODULE.read_text(encoding='utf-8')
        # `.dispute(` appears once, inside the claim-consistency check, which
        # acts on a claim and not on a measurement.
        before_claims = source.split('def check_claim_consistency')[0]
        self.assertNotIn('.dispute(', before_claims)

    def test_its_profile_carries_no_nutrition_bands_and_no_price_band(self):
        self.assertEqual(CATEGORY.profile.nutrition_bands, {})
        self.assertIsNone(CATEGORY.profile.price_band)


class RealCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = load_cases()
        cls.cards = {asin: evaluate(rec) for asin, rec in cls.records.items()}

    PASTES = ('B01M25SBQ5', 'B000RW5FVA', 'B00295ER76', 'B0GNMRKPGQ',
              'B0GNMSWB7D', 'B0DHS9JHLJ', 'B01LB62GQ2', 'B01LB4QIEU',
              'B071JNV24H', 'B001NYY87I', 'B0FSRM9TBK', 'B0055Y6M7Q',
              'B076HTCT4J')
    NOT_PASTES = ('B097C8JJY4', 'B0D1RJ1HLC', 'B00CSRY8OC', 'B0FJG6YJ2X',
                  'B08VNDJJS6', 'B01MXXA922', 'B01M6WXE0X', 'B07V48PZY5',
                  'B0CRTZ5ZJN', 'B0C1GHMX8V', 'B0068ICY70', 'B07J2W1S6Q',
                  'B0DGPV9TWZ', 'B0F4PQ7NMM', 'B0D6N5HYKB', 'B007MFMN9W')

    def test_classification_holds_on_the_real_titles(self):
        for asin in self.PASTES:
            with self.subTest(asin=asin, expect='paste'):
                self.assertEqual(self.cards[asin]['category'].value, KEY)
        for asin in self.NOT_PASTES:
            with self.subTest(asin=asin, expect='other'):
                self.assertEqual(self.cards[asin]['category'].value, 'other')

    def test_a_grease_pack_size_is_never_reported_as_a_fat_content(self):
        """German "Fett" is both grease and fat.

        Four listings state a pack size next to the word, which the food
        parser reads as a nutrition declaration -- twice with a per-100 g
        basis close enough to satisfy every other check. Nothing may present
        them as fact.
        """
        for asin in ('B0068ICY70', 'B07J2W1S6Q', 'B0DGPV9TWZ', 'B0F4PQ7NMM'):
            with self.subTest(asin=asin):
                values = self.cards[asin]['validated'].nutrition
                self.assertTrue(values, f'{asin} should still carry the value')
                for key, value in values.items():
                    self.assertNotEqual(value.status, TRUSTED)
                    self.assertIn(nutrition.UNCORROBORATED, value.flags)

    def test_a_bare_title_weight_confirms_a_single_unit_pack(self):
        quantity = self.cards['B01M25SBQ5']['axes']['quantity']
        self.assertEqual(quantity.status, TRUSTED)
        self.assertEqual(quantity.value, 5000.0)

    def test_a_kits_shipping_weight_is_not_its_paste_content(self):
        """9 kg filed against "5 kg Montagepaste" in the title.

        Unverified, not disputed: a bare weight may confirm a total and may
        never contradict one.
        """
        quantity = self.cards['B0FSRM9TBK']['axes']['quantity']
        self.assertEqual(quantity.status, UNVERIFIED)

    def test_a_pack_in_millilitres_is_priced_per_litre(self):
        card = self.cards['B00295ER76']
        self.assertEqual(card['axes']['quantity'].unit, 'ml')
        self.assertEqual(card['axes']['price_per_base'].unit, 'EUR/l')

    def test_a_declared_mineral_oil_base_is_surfaced_as_adverse(self):
        claims = self.cards['B071JNV24H']['claims']
        self.assertEqual(claims['mineral_oil_base'].status, TRUSTED)
        self.assertIn('Mineralöl', claims['mineral_oil_base'].evidence[0].quote)

    def test_the_drying_claim_carries_the_sentence_it_came_from(self):
        claim = self.cards['B0GNMRKPGQ']['claims']['dries_out']
        self.assertEqual(claim.status, TRUSTED)
        self.assertIn('trocknet', claim.evidence[0].quote.lower())

    def test_an_unstated_criterion_is_not_claimed_rather_than_false(self):
        claims = self.cards['B01M25SBQ5']['claims']
        self.assertEqual(claims['dries_out'].status, NOT_CLAIMED)
        self.assertIn('not the same as it being untrue',
                      claims['dries_out'].notes[0])

    def test_a_kit_says_a_quoted_claim_may_be_about_another_item(self):
        claims = self.cards['B0DHS9JHLJ']['claims']
        stated = [value for value in claims.values() if value.status == TRUSTED]
        self.assertTrue(stated)
        for value in stated:
            self.assertTrue(any('kit' in note for note in value.notes))

    def test_ranking_prefers_the_smallest_pack(self):
        cards = [self.cards[asin] for asin in self.PASTES]
        text = report.rank_text(cards)
        self.assertIn('ranked by pack size (lower first)', text)
        first = [line for line in text.splitlines()
                 if line.strip().startswith('1.')][0]
        self.assertIn('B000RW5FVA', first)

    def test_price_per_kilogram_is_shown_and_refused_as_a_ranking(self):
        axis = CATEGORY.axis('price_per_base')
        self.assertEqual(axis.better, '')
        self.assertIn('not ranked', axis.caveat)
        text = report.card_text(self.cards['B01M25SBQ5'])
        self.assertIn('Price per kg / l', text)

    def test_every_card_renders(self):
        for asin, card in self.cards.items():
            with self.subTest(asin=asin):
                self.assertTrue(report.card_text(card))
                json.dumps(report.card_json(card))

    def test_the_summary_renders(self):
        self.assertIn('tyre mounting paste',
                      report.summary_text(list(self.cards.values())))

    def test_two_pastes_compare_on_the_categorys_own_axes(self):
        """Smaller wins, which is the opposite of what dry pasta wants."""
        text = ' '.join(report.compare_text(self.cards['B0GNMRKPGQ'],
                                            self.cards['B01M25SBQ5']).split())
        self.assertIn('Differences', text)
        self.assertIn('Pack size', text)
        self.assertIn('A is 5.0× smaller', text)

    def test_a_gram_pack_is_not_set_against_a_millilitre_one(self):
        """Grams and millilitres are one axis only if you have a density."""
        text = ' '.join(report.compare_text(self.cards['B000RW5FVA'],
                                            self.cards['B01M25SBQ5']).split())
        self.assertIn('measured in different units (ml and g)', text)
        self.assertNotIn('smaller', text)


if __name__ == '__main__':
    unittest.main()
