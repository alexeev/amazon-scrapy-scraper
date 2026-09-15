"""Basmati rice: the third category, and what it must refuse to conclude.

Three groups of test here, for three different ways this category could go
wrong.

*Classification*, because a rice search returns rice cookers, rice flour and
rice cakes, and one of them outranks real rice on price per kilogram.

*The evidence asymmetry*, because this is the first category with a buyer's
side. A vendor's silence and a reviewer's silence mean different things, a
five-star review saying "klebt überhaupt nicht" must never register as a
stickiness complaint, and a sentence in a feature bullet must never be
reported as something a buyer found.

*The score*, because this module has one and the rest of the platform
deliberately does not. Every test in :class:`Scoring` pins a property that
makes the number defensible rather than merely available: that nothing
unmeasured can win, that an independent laboratory result outweighs any
quantity of vendor adjectives, and that Bio moves the health component not
at all.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon_scraper.analysis import category as cat  # noqa: E402
from amazon_scraper.analysis.categories import basmati_rice as B  # noqa: E402
from amazon_scraper.validation import (  # noqa: E402
    NOT_CLAIMED, TRUSTED, UNKNOWN, UNVERIFIED)

MODULE = pathlib.Path(B.__file__)

HISTOGRAM = {'five_star': 75, 'four_star': 9, 'three_star': 9,
             'two_star': 5, 'one_star': 2}


def review(stars=5, text='', title='', variant='5 kg', country='Deutschland'):
    return {'id': f'R{abs(hash((stars, text, title))) % 10 ** 8}',
            'rating': float(stars), 'rating_text': f'{stars} von 5 Sternen',
            'title': title, 'language': 'de-DE', 'date': '2026-07-06',
            'date_text': f'Bewertet in {country} am 6. Juli 2026',
            'country': country, 'home_marketplace': country == 'Deutschland',
            'variant': variant, 'verified': True, 'helpful_votes': None,
            'text': text}


def record(title='Basmati Reis 5 kg', bullets=(), reviews=None, rating=4.5,
           count=400, histogram=None, origin='Indien', price=15.0,
           grams=5000.0, ingredients='Basmati Reis', breadcrumbs=None,
           brand='Test', **extra):
    block = {}
    if histogram is not False:
        block = {'histogram_percent': dict(histogram or HISTOGRAM),
                 'sample': list(reviews or []),
                 'sample_size': len(reviews or []),
                 'sample_home': len([r for r in (reviews or [])
                                     if r['home_marketplace']]),
                 'rating_count': count, 'sample_source': 'pdp_widget'}
    base = {
        'schema_version': 5, 'asin': 'B000000000', 'title': title,
        'brand': brand,
        'product_url': 'https://www.amazon.de/dp/B000000000',
        'search_query': 'basmati reis', 'marketplace': 'www.amazon.de',
        'breadcrumbs': list(breadcrumbs if breadcrumbs is not None
                            else ['Lebensmittel & Getränke',
                                  'Nudeln, Reis & Hülsenfrüchte', 'Reis']),
        'price': {'amount': price, 'currency': 'EUR'},
        'unit_price': {},
        'rating': {'value': rating, 'count': count,
                   'text': f'{rating} von 5 Sternen'},
        'package': {'total_quantity_base': grams, 'total_quantity_unit': 'g',
                    'item_count': 1, 'total_quantity_source': 'item_weight'},
        'attributes': {'country_of_origin': origin} if origin else {},
        'raw_tables': {'Herkunftsland': origin} if origin else {},
        'content': {'feature_bullets': list(bullets), 'description': '',
                    'important_information': [], 'aplus': {}},
        'food': {'ingredients': {'text': ingredients} if ingredients else {},
                 'allergens': [], 'nutrition': {}},
        'variation': {}, 'reviews': block,
    }
    base.update(extra)
    return base


class Classification(unittest.TestCase):
    """A rice search is mostly not rice."""

    def accepted(self, **kwargs):
        return B.classify(record(**kwargs)).value

    def test_a_bag_of_basmati_is_basmati(self):
        self.assertEqual(self.accepted(title='Tilda Pure Basmati Reis 5 kg'),
                         B.KEY)

    def test_the_german_compound_noun_is_basmati(self):
        """German compounds the noun, and `\\bbasmati\\b` does not match it.

        Measured cost of the boundary the first draft had: **36 of 216**
        listings classified out, among them `AKASH Basmatireis 1 x 10 kg` --
        one of only two basmatis Stiftung Warentest rated "gut" in 5/2026 --
        plus Tilda Pure Original in 5 kg and 10 kg, Alnatura, Spielberger
        demeter and both India Gate sacks. A punctuation-level assumption
        about the marketplace's language removed the best-evidenced product
        on the shelf from the comparison.
        """
        for title in ('AKASH Basmatireis, 1er Pack (1 x 10 kg)',
                      'Tilda Pure Original Basmatireis 5kg',
                      'Alnatura Bio Himalaya Basmatireis weiß, 1kg'):
            self.assertEqual(self.accepted(title=title), B.KEY, title)

    def test_a_rice_cooker_is_not_rice(self):
        """Returned by "basmati reis 5kg" because its copy says both."""
        self.assertEqual(
            self.accepted(title='Reiskocher 5 Liter für Basmati Reis'),
            'other')

    def test_long_grain_that_is_not_basmati_is_rejected(self):
        self.assertEqual(
            self.accepted(title='Langkornreis Spitzenqualität 5 kg',
                          ingredients='Langkornreis'),
            'other')

    def test_rice_flour_and_rice_cakes_are_rejected(self):
        for title in ('Basmati Reismehl 1 kg', 'Reiswaffeln Basmati 100 g',
                      'Basmati Reisnudeln 400 g'):
            self.assertEqual(self.accepted(title=title), 'other', title)

    def test_ready_meals_are_rejected(self):
        for title in ('Express Basmati Reis Becher 250 g',
                      'Basmati Reis fertiggericht Mikrowelle'):
            self.assertEqual(self.accepted(title=title), 'other', title)

    def test_blends_and_gift_sets_are_rejected(self):
        for title in ('Reis Mischung Basmati & Wildreis 1 kg',
                      'Basmati Reis Probierset 6 Sorten'):
            self.assertEqual(self.accepted(title=title), 'other', title)

    def test_a_cooked_pouch_is_caught_by_its_declaration(self):
        """Its title is just "Basmati Reis, 250g"; its contents are a meal."""
        self.assertEqual(
            self.accepted(title='by Amazon Basmati Reis, 250g',
                          ingredients='Gekochter parboiled Basmati Reis (98%) '
                                      '(Wasser, parboiled Basmati Reis), '
                                      'Sonnenblumenöl, Salz'),
            'other')

    def test_the_ingredient_declaration_can_rescue_a_brand_only_title(self):
        card = B.classify(record(title='Kohinoor Extra Long 5 kg',
                                 ingredients='100% Basmati Reis'))
        self.assertEqual(card.value, B.KEY)

    def test_classification_always_decides(self):
        """`unclassified` is not an outcome; every record gets an answer."""
        for title in ('Basmati Reis 1 kg', 'Reiskocher', 'Katzenstreu Reis'):
            self.assertIn(B.classify(record(title=title)).value,
                          (B.KEY, 'other'))


class GrainAndVariety(unittest.TestCase):

    def grain(self, **kwargs):
        from amazon_scraper.validation import validate
        return B.grain_type(validate(record(**kwargs), B.PROFILE))

    def cultivar(self, **kwargs):
        from amazon_scraper.validation import validate
        return B.cultivar(validate(record(**kwargs), B.PROFILE))

    def test_sella_is_detected_as_parboiled(self):
        value = self.grain(title='Basmati Reis Golden Sella 5 kg')
        self.assertEqual(value.value, 'parboiled')
        self.assertEqual(value.status, TRUSTED)

    def test_vollkorn_is_detected_as_brown(self):
        self.assertEqual(
            self.grain(title='Bio Basmati Vollkorn Reis 1 kg').value, 'brown')

    def test_parboiled_wins_over_white(self):
        """A bag can say both; what happened to it is what it is."""
        self.assertEqual(
            self.grain(title='Weißer Basmati Reis Sella parboiled').value,
            'parboiled')

    def test_silence_reads_as_white_but_is_not_trusted(self):
        value = self.grain(title='Basmati Reis 5 kg')
        self.assertEqual(value.value, 'white')
        self.assertEqual(value.status, UNVERIFIED)

    def test_cross_sell_copy_does_not_decide_the_grain_type(self):
        """The error that marked the Stiftung Warentest winner parboiled.

        Tilda's own bullet advertises the rest of its range -- "Neben unseren
        PURE BASMATI Reis haben wir auch bereits vorgekochte ... Steamed
        Coconut & Chili" -- inside the page of a rice that is none of those
        things. Searching every text field made 29 of 53 parboiled verdicts
        wrong; restricting to the fields that describe this bag made it 0.
        """
        value = self.grain(
            title='Tilda Pure Original Basmati Rice, 1er Pack (1x10kg)',
            ingredients='Basmatireis.',
            bullets=['Neben unseren PURE BASMATI Reis haben wir auch bereits '
                     'vorgekochte, besondere Sorten wie Steamed Coconut & '
                     'Chili Basmati Rice und Pilau Basmati Rice'])
        self.assertEqual(value.value, 'white')

    def test_an_aplus_comparison_table_does_not_decide_it_either(self):
        value = self.grain(
            title='INDIA GATE Premium Basmati Reis 5 kg',
            content={'feature_bullets': [], 'description': '',
                     'important_information': [],
                     'aplus': {'text': 'Sorte Premium Sella Classic '
                                       'Golden Sella Rozana'}})
        self.assertEqual(value.value, 'white')

    def test_a_negated_claim_is_not_the_claim(self):
        """"Non-parboiled for authentic basmati" is the opposite."""
        value = self.grain(title='DIBA 1121 Basmati Rice, Non-parboiled, 907 g')
        self.assertNotEqual(value.value, 'parboiled')

    def test_a_real_sella_is_still_caught(self):
        """The restriction must not cost the true positives."""
        self.assertEqual(
            self.grain(title='Laila Golden Sella Basmati Reis 10 kg').value,
            'parboiled')

    def test_a_registered_variety_is_marked_as_such(self):
        value = self.cultivar(title='Taraori Basmati Reis 1 kg')
        self.assertIn('registered_cultivar', value.flags)
        self.assertIn('EU list', ' '.join(value.notes))

    def test_a_trade_grade_is_not_a_registered_variety(self):
        value = self.cultivar(title='Super Kernel Basmati Reis 5 kg')
        self.assertIn('trade_grade', value.flags)
        self.assertNotIn('registered_cultivar', value.flags)

    def test_no_variety_is_not_claimed_rather_than_unknown(self):
        value = self.cultivar(title='Premium Basmati Reis 5 kg')
        self.assertEqual(value.status, NOT_CLAIMED)
        self.assertIsNone(value.value)


class ReviewEvidence(unittest.TestCase):
    """The asymmetry, and the false positive that motivated the split."""

    def signals(self, reviews):
        from amazon_scraper.validation import validate
        return B.review_signals(validate(record(reviews=reviews), B.PROFILE))

    def test_praise_for_not_sticking_is_not_a_stickiness_complaint(self):
        """The commonest false positive in the module, pinned.

        "Die Körner kleben überhaupt nicht" matches the stickiness pattern
        and is a five-star endorsement. Searching negative signals only in
        1- and 2-star reviews is what stops it being read as a defect.
        """
        found = self.signals([review(5, 'Die Körner kleben überhaupt nicht, '
                                        'schön locker.')])
        self.assertEqual(found['sticky'].status, UNKNOWN)
        self.assertIs(found['fluffy'].value, True)

    def test_a_complaint_in_a_one_star_review_is_found(self):
        found = self.signals([review(1, 'Der Reis klebt zu einer Pampe '
                                        'zusammen.')])
        self.assertIs(found['sticky'].value, True)
        self.assertEqual(found['sticky'].status, UNVERIFIED)

    def test_praise_in_a_one_star_review_is_not_counted_as_praise(self):
        found = self.signals([review(1, 'Duftet gut, aber voller Käfer.')])
        self.assertEqual(found['aroma'].status, UNKNOWN)
        self.assertIs(found['insects'].value, True)

    def test_absence_of_a_complaint_is_unknown_not_absence(self):
        found = self.signals([review(5, 'Sehr guter Reis.')])
        self.assertEqual(found['insects'].status, UNKNOWN)
        self.assertTrue(any('not evidence of absence' in n
                            for n in found['insects'].notes))

    def test_generic_praise_is_not_reported_as_aroma(self):
        """Buyers say "schmeckt gut" far more than they say "duftet"."""
        found = self.signals([review(5, 'Schmeckt sehr gut, kaufe ich wieder')])
        self.assertIs(found['taste_praise'].value, True)
        self.assertEqual(found['aroma'].status, UNKNOWN)

    def test_a_review_signal_is_never_trusted(self):
        found = self.signals([review(1, 'Überall Motten drin!')])
        self.assertNotEqual(found['insects'].status, TRUSTED)

    def test_vendor_copy_cannot_produce_a_review_signal(self):
        """A bullet claiming aroma must not come back as a buyer report."""
        from amazon_scraper.validation import validate
        validated = validate(
            record(bullets=['Herrlich aromatischer, duftender Basmati'],
                   reviews=[]), B.PROFILE)
        self.assertEqual(B.review_signals(validated)['aroma'].status, UNKNOWN)


class Scoring(unittest.TestCase):
    """What makes the number defensible."""

    def score(self, **kwargs):
        return B.evaluate(record(**kwargs))['score']

    def test_an_unevidenced_listing_cannot_beat_a_measured_one(self):
        """The bug this term was added for, as a test.

        A claim-stuffed listing with five ratings used to outrank the winner
        of an independent laboratory test.
        """
        stuffed = self.score(
            title='Premium Basmati Reis 10kg Extra Langkorn 1121 Aromatisch',
            bullets=['100% reiner Basmati aus dem Punjab am Himalaya',
                     'EU-schadstoffgeprüft: Arsen unter der Nachweisgrenze'],
            count=5, histogram={'five_star': 100}, price=31.0, grams=10000.0)
        measured = self.score(title='Tilda Pure Original Basmati Reis 5 kg',
                              brand='Tilda', count=400,
                              bullets=['Tilda Pure Basmati Reis wird am Fusse '
                                       'des Himalaya angebaut.'])
        self.assertLess(stuffed['total'], measured['total'])

    def test_the_shrink_pulls_toward_neutral_and_never_below(self):
        bare = self.score(title='Basmati Reis 1 kg', origin=None,
                          ingredients=None, count=2,
                          histogram={'one_star': 100}, rating=1.0)
        self.assertGreaterEqual(bare['total'], 0.0)
        # It is shrunk toward 50, so it sits nearer 50 than the raw score does.
        self.assertLess(abs(bare['total'] - B.NEUTRAL_SCORE),
                        abs(bare['raw'] - B.NEUTRAL_SCORE))

    def test_an_external_failure_dominates_every_vendor_claim(self):
        """Gepa: Bio, Fairtrade, and 20% foreign varieties by DNA."""
        card = B.evaluate(record(
            title='Gepa Bio Basmati Reis fair gehandelt 500 g',
            brand='Gepa',
            bullets=['100% reiner Basmati', 'Bio und fair gehandelt',
                     'Aus dem Himalaya-Vorgebirge'],
            grams=500.0, price=3.5))
        self.assertEqual(card['external_test'].value, 'failed')
        self.assertLessEqual(card['score']['parts']['authenticity'], 0.2)
        self.assertLessEqual(card['score']['parts']['health'], 0.1)

    def test_a_reseller_cannot_inherit_a_lab_result_from_a_title(self):
        """The easiest way to game a score built on external evidence.

        A real listing: "Tilda Pure Original Basmati Reis, 1er Pack (4 x
        2kg)", filed under brand Kajal, manufacturer Kajal GMBH, in a pack
        size Tilda does not sell. Stiftung Warentest tested a Tilda-branded
        bag. The test is still reported -- the reader should know it exists --
        but as `unverified`, and worth half as much.
        """
        genuine = B.evaluate(record(
            title='Tilda Pure Original Basmati Rice, 1er Pack (1x10kg)',
            brand='Tilda', manufacturer='TILDA', grams=10000.0, price=34.95,
            attributes={'country_of_origin': 'Indien',
                        'manufacturer': 'TILDA'}))
        reseller = B.evaluate(record(
            title='Tilda Pure Original Basmati Reis, 1er Pack (4 x 2kg)',
            brand='Kajal', grams=8000.0, price=41.11,
            attributes={'country_of_origin': 'Indien',
                        'manufacturer': 'Kajal GMBH'}))
        self.assertEqual(genuine['external_test'].status, TRUSTED)
        self.assertEqual(reseller['external_test'].status, UNVERIFIED)
        self.assertGreater(genuine['score']['parts']['health'],
                           reseller['score']['parts']['health'])
        self.assertIn('not demonstrably the same',
                      ' '.join(reseller['external_test'].notes))

    def test_a_mostly_unverified_review_set_costs_consistency(self):
        cards = [review(5, 'Toll') for _ in range(4)]
        for c in cards[:3]:
            c['verified'] = False
        weak = self.score(reviews=cards)
        strong = self.score(reviews=[review(5, 'Toll') for _ in range(4)])
        self.assertLess(weak['parts']['consistency'],
                        strong['parts']['consistency'])

    def test_bio_does_not_move_the_health_component(self):
        """The brief's central question, answered mechanically.

        Inorganic arsenic is geogenic. An organic certificate says nothing
        about it, and this asserts that the code agrees.
        """
        plain = self.score(title='Basmati Reis weiß 1 kg', grams=1000.0)
        organic = self.score(title='Bio Basmati Reis weiß 1 kg',
                             bullets=['Bio-zertifiziert, DE-ÖKO-001'],
                             grams=1000.0)
        self.assertEqual(plain['parts']['health'],
                         organic['parts']['health'])

    def test_parboiled_scores_lower_on_health_than_white(self):
        """Öko-Test measured its highest arsenic in parboiled and brown."""
        white = self.score(title='Basmati Reis weiß 5 kg')
        sella = self.score(title='Basmati Reis Golden Sella 5 kg')
        brown = self.score(title='Basmati Vollkorn Reis 5 kg')
        self.assertGreater(white['parts']['health'], sella['parts']['health'])
        self.assertGreater(white['parts']['health'], brown['parts']['health'])

    def test_every_component_is_reported_with_the_total(self):
        detail = self.score()
        self.assertEqual(set(detail['parts']), set(B.WEIGHTS))
        self.assertIn('unknown', detail)
        self.assertIn('evidence', detail)

    def test_a_missing_input_scores_neutral_not_zero(self):
        """Absence of data must not be an adverse finding."""
        detail = self.score(title='Basmati Reis 1 kg', reviews=[],
                            grams=1000.0)
        self.assertEqual(detail['parts']['taste'], 0.5)

    def test_broken_rice_is_capped_on_grain_quality(self):
        detail = self.score(title='Basmati Bruchreis 5 kg')
        self.assertLessEqual(detail['parts']['grain'], 0.1)


class Contract(unittest.TestCase):
    """The category stays downstream of the contract, as R2 requires."""

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
        """Including the review rules: they are the contract's, not ours."""
        extra = self.imported_from_validation() - self.ALLOWED
        self.assertFalse(extra, extra)

    def test_review_evidence_arrives_through_the_validated_record(self):
        card = B.evaluate(record(reviews=[review(5, 'Sehr aromatisch')]))
        validated = card['validated']
        self.assertIs(card['axes']['review_rating'], validated.review_rating)
        self.assertIs(card['axes']['review_negative_share'],
                      validated.review_negative_share)

    def test_a_non_basmati_still_gets_a_card(self):
        card = B.evaluate(record(title='Reiskocher 1.8 L'))
        self.assertFalse(cat.is_match(card))
        self.assertEqual(card['axes'], {})


if __name__ == '__main__':
    unittest.main()
