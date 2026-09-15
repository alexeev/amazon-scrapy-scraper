"""Reviews: the histogram, the sample, and the difference between them.

Every rule under test is category-neutral -- nothing here knows what the
product is. What is being pinned is mostly a set of *refusals*: that a sample
Amazon chose is never promoted to trusted, that absence from it is `unknown`
rather than `not_claimed`, and that a rate is only ever computed from the
histogram, which is complete.

The parsing tests run against real markup shapes taken from live amazon.de
pages, including the three artefacts that a naive read gets wrong: the
screen-reader boilerplate Amazon renders inside every review body, the
singular "Eine Person fand..." helpful-vote form that spells the number out,
and the "reviews from other countries" section, which is 30% of the corpus's
review cards and is not evidence about this marketplace's product.
"""

import pathlib
import sys
import unittest

from parsel import Selector

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon_scraper.extraction import reviews as extract_reviews  # noqa: E402
from amazon_scraper.extraction.marketplaces import for_domain  # noqa: E402
from amazon_scraper.validation import (  # noqa: E402
    DISPUTED, STRUCTURED, TRUSTED, UNKNOWN, UNVERIFIED, reviews, validate)

DE = for_domain('www.amazon.de')

# One review card, in the shape amazon.de actually serves it. The two
# `a-teaser-describedby-*` divs are the screen-reader strings that leak into
# every naive text dump.
CARD = '''
<div id="{id}" data-hook="review" class="a-section">
  <i data-hook="review-star-rating" class="a-icon a-icon-star a-star-{stars}">
    <span class="a-icon-alt">{stars} von 5 Sternen</span></i>
  <h5 data-hook="reviewTitle" lang="de-DE">{title}</h5>
  <div data-hook="review-by-line">
    <span data-hook="review-date">Bewertet in {country} am {date}</span></div>
  <div data-hook="product-variation-attributes">
    <a data-hook="format-strip"><span>Größe: {variant}</span></a></div>
  <div data-hook="review-badges">
    <span data-hook="avp-badge">{badge}</span></div>
  <div data-hook="reviewText">
    <div class="a-teaser-describedby-collapsed a-hidden">Brief content
      visible, double tap to read full content.</div>
    <div class="a-teaser-describedby-expanded a-hidden">Full content visible,
      double tap to read brief content.</div>
    <span>{text}</span></div>
  <span data-hook="helpful-vote-statement">{helpful}</span>
</div>'''

HISTOGRAM = '''
<span class="cr-widget-TitleRatingsHistogram">
  <a aria-label="{five} Prozent der Bewertungen haben 5 Sterne" href="#"></a>
  <a aria-label="{four} Prozent der Bewertungen haben 4 Sterne" href="#"></a>
  <a aria-label="{three} Prozent der Bewertungen haben 3 Sterne" href="#"></a>
  <a aria-label="{two} Prozent der Bewertungen haben 2 Sterne" href="#"></a>
  <a aria-label="{one} Prozent der Bewertungen haben 1 Sterne" href="#"></a>
</span>'''


def card(id='R1', stars=5, title='Super Reis', country='Deutschland',
         date='6. Juli 2026', variant='5 kg (1er Pack)',
         badge='Verifizierter Kauf', text='Toller Duft, lange Körner.',
         helpful=''):
    return CARD.format(id=id, stars=stars, title=title, country=country,
                       date=date, variant=variant, badge=badge, text=text,
                       helpful=helpful)


def histogram(five=71, four=13, three=5, two=4, one=7):
    return HISTOGRAM.format(five=five, four=four, three=three, two=two, one=one)


def page(*parts):
    return Selector(f'<html><body>{"".join(parts)}</body></html>')


def record(rating=4.3, count=714, html=None, **overrides):
    """A minimal record carrying an extracted review block."""
    block = extract_reviews.extract(
        page(html if html is not None else histogram() + card()), DE, count)
    base = {
        'schema_version': 5,
        'asin': 'B000000000',
        'title': 'Basmati Reis 5 kg',
        'brand': 'Test',
        'product_url': 'https://www.amazon.de/dp/B000000000',
        'price': {'amount': 10.0, 'currency': 'EUR'},
        'unit_price': {},
        'rating': {'value': rating, 'count': count,
                   'text': f'{rating} von 5 Sternen'},
        'package': {}, 'attributes': {}, 'raw_tables': {},
        'content': {'feature_bullets': [], 'description': '',
                    'important_information': [], 'aplus': {}},
        'food': {'ingredients': {}, 'allergens': [], 'nutrition': {}},
        'variation': {}, 'reviews': block,
    }
    base.update(overrides)
    return base


class Extraction(unittest.TestCase):
    """What the page says, read faithfully."""

    def test_histogram_is_read_as_whole_percents(self):
        block = extract_reviews.extract(page(histogram()), DE, 714)
        self.assertEqual(block['histogram_percent'],
                         {'five_star': 71, 'four_star': 13, 'three_star': 5,
                          'two_star': 4, 'one_star': 7})

    def test_screen_reader_boilerplate_is_not_review_text(self):
        """The two `a-teaser-describedby` strings are on every single card.

        They are English even on amazon.de, so a locale-keyed noise list
        would not catch them; they are excluded by structure instead.
        """
        block = extract_reviews.extract(page(card(text='Sehr gute Ware')), DE)
        self.assertEqual(block['sample'][0]['text'], 'Sehr gute Ware')

    def test_ui_affordances_are_stripped_from_the_body(self):
        block = extract_reviews.extract(
            page(card(text='Guter Reis Mehr erfahren Weniger anzeigen')), DE)
        self.assertEqual(block['sample'][0]['text'], 'Guter Reis')

    def test_german_dateline_yields_an_iso_date(self):
        block = extract_reviews.extract(page(card(date='6. Juli 2026')), DE)
        self.assertEqual(block['sample'][0]['date'], '2026-07-06')

    def test_a_foreign_dateline_is_flagged_not_dropped(self):
        """30% of the corpus's review cards come from another marketplace."""
        block = extract_reviews.extract(
            page(card(country='Deutschland'),
                 card(id='R2', country='Italien')), DE)
        self.assertEqual(block['sample_size'], 2)
        self.assertEqual(block['sample_home'], 1)
        self.assertIs(block['sample'][0]['home_marketplace'], True)
        self.assertIs(block['sample'][1]['home_marketplace'], False)
        self.assertEqual(block['sample'][1]['country'], 'Italien')

    def test_singular_helpful_vote_counts_as_one(self):
        """"Eine Person fand..." spells the number out; \\d+ finds nothing."""
        plural = extract_reviews.extract(
            page(card(helpful='9 Personen fanden dies hilfreich')), DE)
        singular = extract_reviews.extract(
            page(card(helpful='Eine Person fand diese Informationen hilfreich')), DE)
        none = extract_reviews.extract(page(card()), DE)
        self.assertEqual(plural['sample'][0]['helpful_votes'], 9)
        self.assertEqual(singular['sample'][0]['helpful_votes'], 1)
        self.assertIsNone(none['sample'][0]['helpful_votes'])

    def test_variant_label_drops_its_locale_prefix(self):
        block = extract_reviews.extract(page(card(variant='5 kg (1er Pack)')), DE)
        self.assertEqual(block['sample'][0]['variant'], '5 kg (1er Pack)')

    def test_a_page_with_no_review_widget_yields_no_block(self):
        self.assertEqual(extract_reviews.extract(page('<div></div>'), DE), {})

    def test_the_sample_is_named_as_a_sample(self):
        block = extract_reviews.extract(page(histogram() + card()), DE, 714)
        self.assertEqual(block['sample_source'], 'pdp_widget')
        self.assertEqual(block['rating_count'], 714)


class Rating(unittest.TestCase):
    """The average, and what is allowed to promote it."""

    def test_histogram_agreement_promotes_the_average(self):
        value = reviews.rating(record(rating=4.3, count=714))
        self.assertEqual(value.status, TRUSTED)
        self.assertEqual(value.value, 4.3)
        self.assertTrue(any('independently implies' in n for n in value.notes))

    def test_histogram_disagreement_disputes_the_average(self):
        """A 4.8 claimed over a distribution that implies 2.4."""
        value = reviews.rating(
            record(rating=4.8, count=500,
                   html=histogram(five=10, four=10, three=20, two=20, one=40)))
        self.assertEqual(value.status, DISPUTED)
        self.assertEqual(value.value, 4.8)
        self.assertTrue(any('disagree' in n for n in value.notes))

    def test_no_histogram_leaves_the_average_unverified(self):
        value = reviews.rating(record(html=card()))
        self.assertEqual(value.status, UNVERIFIED)
        self.assertTrue(any('nothing independent' in n for n in value.notes))

    def test_a_thin_rating_count_is_never_promoted(self):
        """Five ratings that agree with their own histogram are still five."""
        value = reviews.rating(
            record(rating=5.0, count=3, html=histogram(100, 0, 0, 0, 0)))
        self.assertEqual(value.status, UNVERIFIED)
        self.assertTrue(any('too\nfew' in n or 'too few' in n
                            for n in value.notes))

    def test_an_incomplete_histogram_is_disputed(self):
        value = reviews.rating(
            record(html=histogram(five=40, four=10, three=5, two=4, one=7)))
        self.assertEqual(value.status, DISPUTED)

    def test_no_rating_at_all_is_unknown(self):
        value = reviews.rating(record(rating=None, count=None))
        self.assertEqual(value.status, UNKNOWN)


class NegativeShare(unittest.TestCase):
    """The one review rate that may be computed, and where it comes from."""

    def test_share_is_one_and_two_star_from_the_histogram(self):
        value = reviews.negative_share(record(count=714))
        self.assertEqual(value.value, 11)          # 7% one-star + 4% two-star
        self.assertEqual(value.status, TRUSTED)
        self.assertEqual(value.source, STRUCTURED)

    def test_share_over_a_thin_count_is_not_trusted(self):
        value = reviews.negative_share(record(count=8))
        self.assertEqual(value.status, UNVERIFIED)
        self.assertTrue(any('percentage points' in n for n in value.notes))

    def test_no_histogram_means_unknown_not_zero(self):
        """The trap: no histogram is not "no negative reviews"."""
        value = reviews.negative_share(record(html=card()))
        self.assertEqual(value.status, UNKNOWN)
        self.assertIsNone(value.value)


class Sample(unittest.TestCase):
    """The refusals. This class is the reason the module exists."""

    def test_the_sample_is_never_trusted(self):
        value = reviews.sample(record(count=714))
        self.assertEqual(value.status, UNVERIFIED)

    def test_the_sample_states_its_own_sampling_fraction(self):
        value = reviews.sample(record(count=714))
        self.assertTrue(any('of 714 ratings are rendered' in n
                            for n in value.notes))
        self.assertTrue(any('never enough to say how common' in n
                            for n in value.notes))

    def test_pooling_across_variants_is_flagged(self):
        value = reviews.sample(record(
            html=card(variant='5 kg (1er Pack)') +
                 card(id='R2', variant='1 kg (10er Pack)')))
        self.assertIn('pooled_variants', value.flags)
        self.assertTrue(any('pooled across 2 variants' in n
                            for n in value.notes))

    def test_a_single_variant_is_not_flagged(self):
        value = reviews.sample(record())
        self.assertNotIn('pooled_variants', value.flags)

    def test_foreign_reviews_are_counted_apart(self):
        value = reviews.sample(record(
            html=card() + card(id='R2', country='Italien')))
        self.assertTrue(any('written on another marketplace' in n
                            for n in value.notes))

    def test_no_review_text_is_unknown(self):
        value = reviews.sample(record(html=histogram()))
        self.assertEqual(value.status, UNKNOWN)


class Signals(unittest.TestCase):
    """Searching what buyers wrote, and the asymmetry with vendor claims."""

    def test_a_signal_found_in_the_sample_is_only_unverified(self):
        value = reviews.signal(
            record(html=card(text='Die Körner sind viel zu oft gebrochen.')),
            r'gebrochen', 'broken grain')
        self.assertEqual(value.status, UNVERIFIED)
        self.assertIs(value.value, True)
        self.assertTrue(any('cannot be read off this page' in n
                            for n in value.notes))

    def test_absence_from_the_sample_is_unknown_not_not_claimed(self):
        """A vendor's silence is evidence. Amazon's selection is not."""
        value = reviews.signal(record(), r'Schaben|Insekten', 'insects')
        self.assertEqual(value.status, UNKNOWN)
        self.assertTrue(any('not evidence of absence' in n
                            for n in value.notes))

    def test_search_can_be_restricted_to_critical_reviews(self):
        rec = record(html=card(stars=5, text='Kein Geruch von Schaben hier') +
                          card(id='R2', stars=1, text='Riecht nach Schaben'))
        critical = reviews.search(rec, r'Schaben', max_stars=2)
        self.assertEqual(len(critical), 1)
        self.assertIn('1★', critical[0].field)

    def test_search_can_exclude_other_marketplaces(self):
        """Foreign reviews count by default; excluding them is opt-in.

        A complaint about a smell is a complaint about a smell whichever
        marketplace it was written on, so the default keeps them. What differs
        is the batch and the importer, which matters for a question like
        "is this seller's stock fresh" -- and that question passes
        ``home_only``.
        """
        rec = record(html=card(country='Italien', text='Ottimo riso profumato'))
        self.assertEqual(len(reviews.search(rec, r'profumato')), 1)
        self.assertEqual(reviews.search(rec, r'profumato', home_only=True), [])

    def test_review_evidence_is_labelled_as_a_review(self):
        """A quote must never be mistakable for the vendor's own words."""
        hits = reviews.search(record(html=card(text='Sehr aromatisch')),
                              r'aromatisch')
        self.assertTrue(hits[0].field.startswith('reviews.sample['))

    def test_vendor_search_does_not_reach_review_text(self):
        """The separation that stops marketing copy corroborating itself."""
        from amazon_scraper.validation import search as vendor_search
        rec = record(html=card(text='Absolut aromatischer Basmati'))
        self.assertEqual(vendor_search(rec, r'aromatischer'), [])


class Contract(unittest.TestCase):
    """Reviews travel on the validated record, for every category."""

    def test_validate_carries_the_review_values(self):
        validated = validate(record(count=714))
        self.assertEqual(validated.review_rating.status, TRUSTED)
        self.assertEqual(validated.review_negative_share.value, 11)
        self.assertEqual(validated.review_sample.status, UNVERIFIED)

    def test_serialised_sample_is_a_count_not_the_cards(self):
        payload = validate(record(count=714)).as_dict()
        self.assertEqual(payload['review_sample']['value'], 1)
        self.assertEqual(payload['review_rating']['value'], 4.3)

    def test_a_record_with_no_reviews_validates_cleanly(self):
        """Every pre-schema-5 record must still validate."""
        validated = validate(record(rating=None, count=None, reviews={}))
        self.assertEqual(validated.review_rating.status, UNKNOWN)
        self.assertEqual(validated.review_sample.status, UNKNOWN)
        self.assertEqual(validated.review_negative_share.status, UNKNOWN)


if __name__ == '__main__':
    unittest.main()
