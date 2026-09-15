"""What a category analyzer is, and the little it has to declare.

A category is the only place in the platform that is allowed to know what the
product is. It declares four things and implements one:

``profile``
    The plausibility data the generic layer needs -- nutrition bands, a price
    band -- and nothing procedural. See
    :class:`~amazon_scraper.validation.CategoryProfile`.

``axes``
    What it is worth comparing two of these products on, in order, and which
    direction is better. This is a *product* decision and it is not the same
    for every category: cheaper per kilogram is the point of dry pasta, and
    actively misleading for tyre mounting paste, where a five-kilogram tub is
    the worst buy on the page for somebody with one scooter tyre to fit.

``claims``
    The statements worth hunting for in the vendor's own text, each with the
    reason it matters. A claim may be *adverse* -- finding it is bad news.

``evaluate``
    ``record -> card``. Classification, the axes filled in, and the claims
    searched for. Everything it needs about trust it gets from
    :func:`amazon_scraper.validation.validate`; it must not re-derive any of
    it, and there is a test that asserts exactly that.
"""

from dataclasses import dataclass

REGISTRY = {}


@dataclass(frozen=True)
class Axis:
    """One thing two products of this category can be compared on."""

    key: str
    label: str
    #: ``'lower'``, ``'higher'``, or ``''`` for an axis that can differ
    #: without one side being better -- raw material, for instance.
    better: str = ''
    #: Sentence fragment appended when this axis decides a comparison, e.g.
    #: "which for durum pasta tracks semolina quality".
    why: str = ''
    #: How to name the winner in a comparison: "A is 1.6x <comparative>".
    comparative: str = ''
    #: Renders the value for display. Defaults to "%g unit".
    render: object = None
    #: Smallest difference worth reporting. Below it the two are the same.
    tolerance: float = 0.0
    #: Shown on the card under the value, when there is something the number
    #: alone would mislead about.
    caveat: str = ''


@dataclass(frozen=True)
class Claim:
    """A statement to look for in the vendor's own words."""

    key: str
    label: str
    pattern: str
    #: Why a buyer should care. Printed on the card beside the quote.
    why: str = ''
    #: True when finding this counts against the product.
    adverse: bool = False
    #: Restrict the search to these record fields, when a claim is only
    #: meaningful in one of them.
    fields: tuple = None


@dataclass(frozen=True)
class Category:
    """A registered category analyzer."""

    key: str
    label: str
    profile: object
    axes: tuple
    claims: tuple
    evaluate: object
    #: Which axis ``rank`` uses when the user names none.
    default_axis: str = ''
    #: One or two sentences the reports open with, stating what this category
    #: can and cannot be judged on from an Amazon product page.
    blurb: str = ''
    #: ``card -> [line]``, for a section only this category has. Optional.
    render_extra: object = None

    def axis(self, key):
        for axis in self.axes:
            if axis.key == key:
                return axis
        return None

    @property
    def axis_keys(self):
        return tuple(axis.key for axis in self.axes)

    @property
    def claim_keys(self):
        return tuple(claim.key for claim in self.claims)

    def claim(self, key):
        for claim in self.claims:
            if claim.key == key:
                return claim
        return None


def register(category):
    REGISTRY[category.key] = category
    return category


def get(key):
    if key not in REGISTRY:
        raise KeyError(f'{key}: unknown category. Known: {", ".join(sorted(REGISTRY))}')
    return REGISTRY[key]


def known():
    return sorted(REGISTRY)


def card(record, validated, category, classification, axes, claims):
    """The shape every category's ``evaluate`` returns, and the report reads."""
    return {
        'category_key': category.key,
        'asin': validated.asin,
        'title': validated.title,
        'brand': validated.brand,
        'url': validated.url,
        'query': validated.query,
        'category': classification,
        'axes': axes,
        'claims': claims,
        'validated': validated,
        # Lifted out of the validated record because grouping and rendering
        # read them on every card, including ones this category rejected.
        'offer': validated.offer,
        'size_label': validated.size_label,
        'siblings': validated.siblings,
        'variation': validated.variation,
    }


def is_match(card):
    """True when the card's category accepted the record as one of its own."""
    return card['category'].value == card['category_key']
