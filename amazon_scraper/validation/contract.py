"""The contract between extraction and category analysis.

One call, :func:`validate`, turns an extraction record into a
:class:`Validated` record: the same facts, each carrying how it was obtained
and whether it survived checking. A category analyzer starts there and adds
only what it alone knows -- what the product *is*, which claims matter, and
which numbers are plausible for it. It never re-derives a trust rule, and it
never has to know the order the generic rules run in.

That order is the part worth having in one place. It is not obvious and it was
learned the expensive way::

    detect  ->  category bands  ->  resolve contradictions  ->  promote

A generic check can prove that an energy figure and its own macronutrients
contradict each other, but not which side is wrong; a plausibility band can
say which value is impossible, but only for a named category. So the bands
have to run in the middle, and *nothing* may be promoted to trusted until both
have spoken. When this sequence lived in the pasta module, the pasta module
was the specification, and a second category would have had to copy four lines
of ordering it had no way to know were load-bearing.

What a category supplies is data, not procedure: a :class:`CategoryProfile`
of plausibility bands. Two categories now share this layer -- dry pasta
(food, sold by weight, cheaper per kilogram is better) and tyre mounting
paste (non-food, no nutrition at all, sold in tubs and tubes, where a *small*
pack is the advantage and price per kilogram is actively misleading). What
survived contact with the second one is recorded in CONTRACT.md.
"""

from dataclasses import dataclass, field

from . import nutrition as _nutrition
from . import pricing, quantity, variation
from . import reviews as _reviews
from .evidence import DISPUTED, Value, search

#: Version of the validated-record shape below. Independent of the extraction
#: ``SCHEMA_VERSION``: the two change for different reasons and are consumed
#: by different code. CONTRACT.md states what each may and may not change
#: within a version.
CONTRACT_VERSION = 1


@dataclass(frozen=True)
class CategoryProfile:
    """Everything the generic layer accepts from a category, and no more.

    Deliberately data-only. A profile cannot add a rule, reorder the pipeline
    or override a status; it can only tell the generic rules what range of
    values the category is known to produce, which is the one thing they
    cannot work out for themselves.
    """

    #: Machine key, e.g. ``'dry_pasta'``.
    key: str = 'product'
    #: Human label used in validation messages: "... every real dry pasta".
    label: str = 'product'
    #: ``{nutrient key: (low, high)}`` per 100 g. Empty for a non-food.
    nutrition_bands: dict = field(default_factory=dict)
    #: ``(low, high)`` for the price per kilogram / per litre, or ``None``
    #: when the category has no defensible range -- which is an honest answer
    #: and not a gap. Mounting paste spans tubes and buckets priced two orders
    #: of magnitude apart per kilogram, so it states no band.
    price_band: tuple = None


NEUTRAL = CategoryProfile()


@dataclass
class Validated:
    """One record, validated. The unit of exchange between the two layers."""

    contract_version: int
    schema_version: object
    category_profile: str

    asin: str
    title: str
    brand: str
    url: str
    marketplace: str
    query: str
    run_id: str
    locale: str

    #: Identity of "this product, in whatever pack size", or None.
    offer: object
    #: Amazon's own label for this pack, e.g. ``"500 g (5er Pack)"``.
    size_label: str
    #: Every ASIN Amazon lists in the same family, including this one.
    siblings: list
    #: The raw variation matrix, kept so a set of records can be re-grouped
    #: using every matrix in the set rather than only the ones each carries.
    variation: dict

    #: Total pack content, in grams or millilitres.
    quantity: Value
    #: What the listing costs.
    price: Value
    #: Price per kilogram or per litre, following the pack's own unit.
    price_per_base: Value
    #: ``{nutrient key: Value}`` per 100 g; empty for anything that is not food.
    nutrition: dict

    #: The average star rating, promoted only when the histogram agrees.
    review_rating: Value
    #: Share of all ratings at one or two stars, from the complete histogram.
    review_negative_share: Value
    #: The rendered review cards, never better than unverified. See
    #: :mod:`amazon_scraper.validation.reviews` for why a sample of Amazon's
    #: choosing cannot support a frequency claim.
    review_sample: Value

    #: The extraction record this was built from. Category layers search its
    #: text for claims; nothing generic reads it after validation.
    record: dict = field(default_factory=dict, repr=False)

    def search(self, pattern, limit=3, fields=None):
        """Evidence for `pattern` in this record's text, best source first."""
        return search(self.record, pattern, limit=limit, fields=fields)

    def search_reviews(self, pattern, **kwargs):
        """Evidence for `pattern` in what *buyers* wrote, not the vendor.

        Kept separate from :meth:`search` on purpose: a producer's claim and a
        reader's experience of it are different kinds of evidence, and a
        hunter that merged them would let marketing copy corroborate itself.
        """
        return _reviews.search(self.record, pattern, **kwargs)

    def review_signal(self, pattern, label, **kwargs):
        """A review signal as a Value: found, or explicitly unknown."""
        return _reviews.signal(self.record, pattern, label, **kwargs)

    def as_dict(self):
        return {
            'contract_version': self.contract_version,
            'schema_version': self.schema_version,
            'category_profile': self.category_profile,
            'asin': self.asin, 'title': self.title, 'brand': self.brand,
            'url': self.url, 'marketplace': self.marketplace,
            'query': self.query, 'run_id': self.run_id, 'locale': self.locale,
            'offer': ([self.offer[0], list(self.offer[1])]
                      if self.offer else None),
            'size_label': self.size_label,
            'siblings': list(self.siblings),
            'quantity': self.quantity.as_dict(),
            'price': self.price.as_dict(),
            'price_per_base': self.price_per_base.as_dict(),
            'nutrition': {key: value.as_dict()
                          for key, value in sorted(self.nutrition.items())},
            'review_rating': self.review_rating.as_dict(),
            'review_negative_share': self.review_negative_share.as_dict(),
            # The cards themselves are not serialised -- they are the
            # record's own text, already on it, and copying them here would
            # double the size of every validated line for no new fact. What
            # is serialised is how many there were, and every caveat that
            # limits reading them.
            'review_sample': dict(
                self.review_sample.as_dict(),
                value=(len(self.review_sample.value)
                       if self.review_sample.value is not None else None)),
        }


def validate(record, profile=NEUTRAL):
    """Validate one extraction record against a category's plausibility data.

    Runs every generic rule whose evidence is present on the record, in the
    one order that lets category knowledge participate without owning the
    pipeline. Safe to call with no profile at all: the result is then what the
    page supports with nothing assumed about the product, which is exactly
    what the corpus regression test pins.
    """
    pack = quantity.reconcile(record)

    per_base = pricing.per_base_unit(record, pack)
    pricing.apply_band(per_base, profile.price_band, profile.label)
    if per_base.status == DISPUTED:
        pricing.alternative_price(record, per_base,
                                  quantity.consensus_hint(record))

    review = _reviews.summary(record)

    values = _nutrition.validate(record)
    if values:
        # Order matters; see the module docstring. The bands name which side
        # of a contradiction is impossible, so they run before it is resolved,
        # and nothing is promoted until both have had their say.
        _nutrition.apply_bands(values, profile.nutrition_bands, profile.label)
        _nutrition.resolve_contradictions(values)
        _nutrition.promote(values)

    return Validated(
        contract_version=CONTRACT_VERSION,
        schema_version=record.get('schema_version'),
        category_profile=profile.key,
        asin=record.get('asin') or '',
        title=record.get('title') or '',
        brand=record.get('brand') or '',
        url=record.get('product_url') or '',
        marketplace=record.get('marketplace') or '',
        query=record.get('search_query') or '',
        run_id=record.get('run_id') or '',
        locale=record.get('locale') or '',
        offer=variation.offer_key(record),
        size_label=variation.size_label(record),
        siblings=variation.siblings(record),
        variation=record.get('variation') or {},
        quantity=pack,
        price=pricing.price(record),
        price_per_base=per_base,
        nutrition=values,
        review_rating=review['rating'],
        review_negative_share=review['negative_share'],
        review_sample=review['sample'],
        record=record,
    )
