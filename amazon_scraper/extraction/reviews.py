"""The review block: the sample Amazon renders, and the distribution behind it.

Two structures, and the difference between them is the whole point.

The **histogram** is a statement about *every* rating the listing has ever
received: five percentages, one per star. It is cheap, it is complete, and it
is the only review evidence on the page that is not a sample of anything.

The **sample** is the handful of reviews Amazon chose to render into the PDP --
eight to thirteen of them, selected by Amazon's own "most helpful" and
"most recent" logic, out of a total that is frequently in the thousands. It is
where the words are, and the words are the only place a reader learns that the
grains arrive broken or the bag smelled of nothing.

The sample is not a random draw and this module does not pretend otherwise; it
records how many were rendered against how many exist, and the layer above
refuses to compute a rate from it. What the sample *can* carry is the presence
of a complaint, which is a different and weaker claim than its frequency.

Three things the widget states that a naive read merges and should not:

``variant``
    "Größe: 5 kg (1er Pack)". Amazon pools reviews across every pack size and
    sometimes across unrelated flavours of one parent ASIN, so a review on the
    page may be about a product the reader is not looking at. The format strip
    says which, when it is present.

``home``
    A dateline reading "Bewertet in Italien" came from the *other countries*
    section: a different marketplace's listing, machine-translated. Real
    evidence, different product-market, flagged rather than dropped.

``verified``
    Whether Amazon could tie the review to a purchase it processed.

Nothing here knows what the product is, and nothing here decides whether a
review should be believed. Extraction stays faithful to the page; see
:mod:`amazon_scraper.validation.reviews` for what survives checking.
"""

import re

from .text import clean

# The review card and its parts. Amazon has two generations of this widget in
# the wild: the older one puts the body in `span[data-hook=review-body]`, the
# current amazon.de one in `div[data-hook=reviewText]`. Both are matched, in
# preference order, because the corpus contains pages of each shape.
REVIEW_CSS = 'div[data-hook=review], div[data-hook=cmps-review]'
BODY_CSS = ('span[data-hook=review-body]', 'div[data-hook=reviewText]',
            'span[data-hook=review-collapsed]')

#: The star rating sits in the icon's alt text: "5 von 5 Sternen".
STARS_RE = re.compile(r'(\d+(?:[.,]\d+)?)')

#: Bars of the ratings histogram, each an anchor whose aria-label spells out
#: the share: "71 Prozent der Bewertungen haben 5 Sterne".
HISTOGRAM_CSS = ('#histogramTable a[aria-label], '
                 '.cr-widget-TitleRatingsHistogram a[aria-label], '
                 '#cm_cr_dp_d_rating_histogram a[aria-label]')

STAR_KEYS = {5: 'five_star', 4: 'four_star', 3: 'three_star',
             2: 'two_star', 1: 'one_star'}


def histogram(selector, marketplace):
    """Share of ratings at each star level, as whole percents.

    Returns ``{}`` when the page renders no histogram. The percentages are
    Amazon's own and are rounded, so they need not sum to exactly 100 -- the
    caller is given them as published rather than normalised, and
    :mod:`amazon_scraper.validation.reviews` is where that is checked.
    """
    shares = {}
    for anchor in selector.css(HISTOGRAM_CSS):
        parsed = marketplace.histogram_share(anchor.attrib.get('aria-label'))
        if not parsed:
            continue
        stars, percent = parsed
        key = STAR_KEYS.get(stars)
        # One bar per star level; Amazon renders the block twice on some
        # layouts (desktop and a hidden mobile copy) and the duplicate must
        # not overwrite a value with a different rounding.
        if key and key not in shares:
            shares[key] = percent
    return shares


#: Amazon renders two screen-reader strings inside every review body -- "Brief
#: content visible, double tap to read full content." and its opposite. They
#: are `a-hidden`, they are in English even on amazon.de, and a naive text dump
#: puts them at the front of every single review. Excluded by structure rather
#: than by matching the sentence, which would be a locale guess.
_VISIBLE_TEXT = ('.//text()['
                 'not(ancestor::*[contains(@class, "a-teaser-describedby")])'
                 ' and not(ancestor::script) and not(ancestor::style)]')


def _body(review, marketplace):
    for css in BODY_CSS:
        node = review.css(css)
        if node:
            text = marketplace.strip_review_noise(
                ' '.join(node.xpath(_VISIBLE_TEXT).getall()))
            if text:
                return text
    return ''


def _stars(review, marketplace):
    text = clean(review.css('i[data-hook=review-star-rating] span::text').get()
                 or review.css('[data-hook=review-star-rating] .a-icon-alt::text').get()
                 or review.css('[data-hook=cmps-review-star-rating] .a-icon-alt::text').get())
    if not text:
        return None, ''
    match = STARS_RE.search(text)
    if not match:
        return None, text
    return marketplace.number(match.group(1)), text


def _variant(review):
    """Amazon's own label for which variant this review is about, if stated."""
    text = clean(' '.join(
        review.css('a[data-hook=format-strip] span::text').getall()
        or review.css('a[data-hook=format-strip]::text').getall()
        or review.css('[data-hook=format-strip-linkless]::text').getall()))
    # "Größe: 5 kg (1er Pack)" -- the label is locale text, the value is not,
    # so the prefix is dropped by position rather than by vocabulary.
    return text.split(':', 1)[1].strip() if ':' in text else text


def one_review(review, marketplace):
    """One review card, verbatim, with its provenance resolved."""
    value, stars_text = _stars(review, marketplace)
    dateline = clean(review.css('span[data-hook=review-date]::text').get())
    country, date, home = marketplace.review_dateline(dateline)
    title_node = review.css('h5[data-hook=reviewTitle], '
                            'a[data-hook=review-title], '
                            'span[data-hook=review-title]')
    # The title node sometimes wraps the star icon too, so its own text is
    # taken rather than all descendant text; on the current amazon.de widget
    # the `lang` attribute states what language the reviewer wrote in.
    title = clean(' '.join(t for t in title_node.css('::text').getall()
                           if 'Sternen' not in t and 'out of 5' not in t))
    return {
        'id': review.attrib.get('id', ''),
        'rating': value,
        'rating_text': stars_text,
        'title': title,
        'language': title_node.attrib.get('lang', ''),
        'date': date,
        'date_text': dateline,
        'country': country,
        'home_marketplace': home,
        'variant': _variant(review),
        'verified': marketplace.is_verified_purchase(
            clean(review.css('span[data-hook=avp-badge]::text').get())),
        'helpful_votes': marketplace.helpful_votes(
            clean(review.css('span[data-hook=helpful-vote-statement]::text').get())),
        'text': _body(review, marketplace),
    }


def extract(selector, marketplace, rating_count=None):
    """The whole review block for one PDP.

    ``rating_count`` is the listing's total rating count, passed in rather
    than re-parsed so the block can state its own sampling fraction. It is the
    number that stops a reader treating "three of eight reviews mention broken
    grain" as 37% of anything.
    """
    sample = [one_review(node, marketplace)
              for node in selector.css(REVIEW_CSS)]
    # A card with neither a rating nor any text is a rendering artefact, not
    # a review; keep anything that carries either.
    sample = [r for r in sample if r['rating'] is not None or r['text']]
    shares = histogram(selector, marketplace)
    if not sample and not shares:
        return {}
    home = [r for r in sample if r['home_marketplace'] is not False]
    return {
        'histogram_percent': shares,
        'sample': sample,
        'sample_size': len(sample),
        'sample_home': len(home),
        'rating_count': rating_count,
        # Named so no caller can mistake it for a complete set. The PDP
        # widget is the only review source reachable without an account:
        # /product-reviews/<ASIN> redirects to sign-in.
        'sample_source': 'pdp_widget',
    }
