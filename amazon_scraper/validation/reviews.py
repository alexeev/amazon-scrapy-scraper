"""What survives checking in the review block, and what a sample may not say.

Reviews arrive as two things of very different evidential weight, and the
central job of this module is to stop them being used as though they were the
same.

**The histogram is complete.** Five percentages covering every rating the
listing ever received. Measured across the 38 corpus pages that carry one, it
sums to exactly 100 on every single record and reconstructs Amazon's published
average to within 0.08 stars -- which is what rounding to whole percent
predicts and nothing worse. So it is an *independent* statement of the same
fact the average asserts, from a different structure, and under this layer's
existing rule that is what promotes a value from unverified to trusted.

**The sample is a sample, and a biased one.** Amazon renders eight to thirteen
review cards into a PDP out of a total that is often in the thousands, chosen
by its own relevance logic. Three consequences this module enforces rather
than documents:

1. *No rate may be computed from it.* "Three of nine reviews mention broken
   grain" is not 33% of anything. A complaint found in the sample establishes
   **presence**, never frequency, and the Value that carries it says so.
2. *Absence proves nothing at all.* Nine cards not mentioning a problem is
   consistent with a hundred reviews that do. The correct status for "not
   found in the sample" is ``unknown``, not ``not_claimed`` -- which is the
   opposite of how the same question is answered for a *vendor* claim, where
   the vendor controls the whole page and silence is informative.
3. *The negative share comes from the histogram, never from the sample.* The
   one-and-two-star percentage is a complete statistic and is the honest way
   to ask "how often does this go wrong".

Two pooling problems the page hides and this module surfaces:

``pooled across variants``
    Amazon shows every review of a parent ASIN's whole family. A five-kilogram
    bag and a one-kilogram bag of different rice share a review set. The
    format strip names the variant per card, so the pooling is *measurable*
    rather than merely suspected.

``pooled across marketplaces``
    A dateline reading "Bewertet in Italien" is a review of a different
    marketplace's listing, machine-translated onto this page. Across the
    corpus, **82 of 277 cards (30%)** are foreign. They are kept -- a
    complaint about a smell is a complaint about a smell -- but they are
    counted apart, because the batch, the importer and sometimes the product
    differ.

Nothing here knows what the product is. Which *words* are worth hunting for in
review prose is category knowledge, and lives in a category module; this layer
supplies :func:`search` so it can be done against the right text with the
right provenance attached.
"""

import re

from .evidence import (Evidence, PUBLISHED, STRUCTURED, TEXT, TRUSTED,
                       UNKNOWN, UNVERIFIED, Value, quote_around)

#: Star level -> its weight, for reconstructing an average from the histogram.
STAR_WEIGHT = {'five_star': 5, 'four_star': 4, 'three_star': 3,
               'two_star': 2, 'one_star': 1}

#: How far the histogram's reconstructed average may sit from the published
#: one before the two are treated as contradicting each other. The histogram
#: is published as whole percents, so a disagreement of up to ~0.1 star is
#: pure rounding. Measured maximum over the corpus: 0.08. A quarter of a star
#: leaves that alone and still catches a real mismatch.
AVERAGE_TOLERANCE = 0.25

#: Below this many ratings, an average is arithmetic rather than evidence: a
#: single disappointed buyer moves a five-rating product by most of a star.
#: Such an average is still shown -- it is not wrong -- but it is never
#: promoted to trusted, however well the histogram corroborates it.
THIN_EVIDENCE = 20


def _reconstruct(histogram):
    """(average, total percent) implied by the histogram, or (None, 0)."""
    total = sum(histogram.values())
    if not total:
        return None, 0
    weighted = sum(share * STAR_WEIGHT[key]
                   for key, share in histogram.items() if key in STAR_WEIGHT)
    return weighted / total, total


def rating(record):
    """The average star rating, checked against the histogram behind it.

    Amazon publishes the average; the histogram is a second, independently
    rendered statement of the same distribution. Agreement promotes, silence
    leaves it unverified, and disagreement disputes it -- the same shape as
    every other corroboration rule in this layer.
    """
    stars = (record.get('rating') or {}).get('value')
    count = (record.get('rating') or {}).get('count')
    if stars is None:
        return Value.unknown('the listing publishes no average rating')

    value = Value(stars, UNVERIFIED, unit='stars', source=PUBLISHED,
                  evidence=[Evidence('rating.text',
                                     (record.get('rating') or {}).get('text') or '')])

    histogram = ((record.get('reviews') or {}).get('histogram_percent')) or {}
    implied, total = _reconstruct(histogram)
    if implied is None:
        value.notes.append('no ratings histogram on the page, so nothing '
                           'independent confirms this average')
        return value

    if total < 98 or total > 102:
        value.dispute(
            f'the histogram covers {total}% of ratings, not 100%, so the '
            f'distribution behind this average is incomplete')
        return value

    if abs(implied - stars) > AVERAGE_TOLERANCE:
        value.dispute(
            f'the histogram implies an average of {implied:.2f} stars, not '
            f'{stars:g} — the two statements on this page disagree',
            Evidence('reviews.histogram_percent', _render(histogram)))
        return value

    if count is not None and count < THIN_EVIDENCE:
        value.notes.append(
            f'the histogram agrees ({implied:.2f}), but {count} ratings is too '
            f'few for the average to mean much: one unhappy buyer moves it by '
            f'most of a star')
        return value

    value.status = TRUSTED
    value.evidence.append(Evidence('reviews.histogram_percent',
                                   _render(histogram)))
    value.notes.append(f'the ratings histogram independently implies '
                       f'{implied:.2f} stars')
    return value


def _render(histogram):
    return ' · '.join(f'{stars}★ {histogram[key]}%'
                      for key, stars in (('five_star', 5), ('four_star', 4),
                                         ('three_star', 3), ('two_star', 2),
                                         ('one_star', 1))
                      if key in histogram)


def negative_share(record):
    """Percentage of all ratings at one or two stars.

    From the histogram, which is complete, and never from the rendered
    sample, which is not. This is the only "how often does this go wrong"
    number on the page that is entitled to be read as a rate.
    """
    histogram = ((record.get('reviews') or {}).get('histogram_percent')) or {}
    if not histogram:
        return Value.unknown('no ratings histogram on the page')
    total = sum(histogram.values())
    if total < 98 or total > 102:
        return Value(None, UNKNOWN,
                     notes=[f'the histogram covers {total}% of ratings, so a '
                            f'share computed from it would be wrong'])

    share = histogram.get('one_star', 0) + histogram.get('two_star', 0)
    count = (record.get('rating') or {}).get('count')
    value = Value(share, TRUSTED, unit='%', source=STRUCTURED,
                  evidence=[Evidence('reviews.histogram_percent',
                                     _render(histogram))])
    if count is not None and count < THIN_EVIDENCE:
        value.status = UNVERIFIED
        value.notes.append(f'computed over only {count} ratings, so one review '
                           f'is worth {100 / count:.0f} percentage points')
    return value


def sample(record):
    """The rendered review cards, with everything that limits their reading.

    The Value's payload is the list of cards. Its status is never better than
    ``unverified``: a set Amazon chose cannot corroborate itself, no matter how
    many cards are in it.
    """
    block = (record.get('reviews') or {})
    cards = block.get('sample') or []
    if not cards:
        return Value(None, UNKNOWN,
                     notes=['the page renders no review text at all'])

    count = (record.get('rating') or {}).get('count')
    value = Value(cards, UNVERIFIED, unit='reviews', source=STRUCTURED)

    foreign = [c for c in cards if c.get('home_marketplace') is False]
    variants = sorted({c.get('variant') for c in cards if c.get('variant')})

    if count:
        value.notes.append(
            f'{len(cards)} of {count} ratings are rendered as text, chosen by '
            f'Amazon rather than sampled — enough to show that a complaint '
            f'exists, never enough to say how common it is')
    else:
        value.notes.append(
            f'{len(cards)} review cards, chosen by Amazon rather than sampled')

    if foreign:
        value.notes.append(
            f'{len(foreign)} of {len(cards)} were written on another '
            f'marketplace ({", ".join(sorted({c["country"] for c in foreign}))}) '
            f'and machine-translated onto this page: a different batch, and '
            f'sometimes a different product')

    if len(variants) > 1:
        value.notes.append(
            f'these reviews are pooled across {len(variants)} variants '
            f'({"; ".join(variants[:4])}), so a card may describe a pack or a '
            f'product other than this one')
        value.flags.add('pooled_variants')

    unverified_buys = [c for c in cards if not c.get('verified')]
    if unverified_buys:
        value.notes.append(f'{len(unverified_buys)} of {len(cards)} are not '
                           f'marked as a verified purchase')
    return value


def summary(record):
    """Every review Value for one record, as a dict."""
    return {'rating': rating(record),
            'negative_share': negative_share(record),
            'sample': sample(record)}


# ---------------------------------------------------------------------------
# Searching review prose
# ---------------------------------------------------------------------------

def search(record, pattern, limit=3, home_only=False, max_stars=None,
           min_stars=None):
    """Evidence for `pattern` in review text, as buyers wrote it.

    Deliberately *not* folded into
    :func:`amazon_scraper.validation.evidence.search`, which walks the
    vendor's own words. A sentence in a feature bullet and the same sentence
    in a review are different kinds of evidence about the world, and a claim
    hunter that could not tell them apart would let a producer's marketing
    copy be corroborated by its own marketing copy.

    ``max_stars`` / ``min_stars`` restrict the search to critical or to
    favourable reviews -- the two questions ("what goes wrong with this rice"
    and "what is it praised for") want different halves of the set.
    """
    regex = re.compile(pattern, re.I) if isinstance(pattern, str) else pattern
    found = []
    for index, card in enumerate((record.get('reviews') or {}).get('sample') or []):
        if home_only and card.get('home_marketplace') is False:
            continue
        stars = card.get('rating')
        if max_stars is not None and (stars is None or stars > max_stars):
            continue
        if min_stars is not None and (stars is None or stars < min_stars):
            continue
        text = f'{card.get("title") or ""}. {card.get("text") or ""}'.strip()
        match = regex.search(text)
        if not match:
            continue
        label = f'reviews.sample[{index}]'
        if stars is not None:
            label += f' ({stars:g}★)'
        found.append(Evidence(label,
                              quote_around(text, match.start(), match.end())))
        if len(found) >= limit:
            break
    return found


def signal(record, pattern, label, **kwargs):
    """A review signal as a Value: found, or honestly unknown.

    The asymmetry here is the point, and it is the opposite of the one that
    applies to a vendor claim. A vendor controls the whole page, so a claim
    absent from it is ``not_claimed`` -- weak evidence, but evidence. Buyers
    control nothing: Amazon picked which nine of four hundred reviews to show.
    So absence from the sample is ``unknown``, full stop.
    """
    hits = search(record, pattern, **kwargs)
    if hits:
        return Value(True, UNVERIFIED, source=TEXT, evidence=hits,
                     notes=[f'{label}: reported by at least '
                            f'{len(hits)} of the reviews Amazon rendered. '
                            f'Whether it is typical cannot be read off this '
                            f'page.'])
    return Value(None, UNKNOWN,
                 notes=[f'{label}: not mentioned in the review sample, which '
                        f'Amazon selected — that is not evidence of absence'])
