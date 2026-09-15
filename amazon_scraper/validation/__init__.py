"""The generic validation layer: everything true of an Amazon record as such.

This package sits between extraction and category analysis and belongs to
neither. It does not know what the product is, and it does not know what the
page looked like::

    extraction  ->  validation  ->  category analysis  ->  report
    (what the       (how much of    (what it means for     (evidence
     page says)      that holds)     this product)          cards)

Its output is the published contract: :func:`validate` turns one extraction
record into a :class:`~.contract.Validated` record whose every value carries
its own ``source`` (how it was obtained) and ``status`` (whether it survived
checking). See CONTRACT.md for the schema, the vocabularies and what a
version bump means.

The rules here earned promotion rather than being designed. Each one was
written next to its first consumer, against a real Amazon page that produced
a confidently wrong number, and moved here only once a *second* category --
tyre mounting paste, a non-food sold in tubs, tubes and aerosols -- had run
over the same code and shown which parts needed to know what the product was.
The answer was: the plausibility bands, and nothing else.
"""

from . import nutrition, pricing, quantity, reviews, variation
from .contract import (CONTRACT_VERSION, CategoryProfile, Validated, validate)
from .evidence import (ATTRIBUTES, DERIVED, DISPUTED, Evidence, NOT_CLAIMED,
                       PUBLISHED, SOURCES, STATUSES, STRUCTURED, TEXT, TRUSTED,
                       UNKNOWN, UNVERIFIED, Value, search)

__all__ = [
    'ATTRIBUTES', 'CONTRACT_VERSION', 'CategoryProfile', 'DERIVED', 'DISPUTED',
    'Evidence', 'NOT_CLAIMED', 'PUBLISHED', 'SOURCES', 'STATUSES',
    'STRUCTURED', 'TEXT', 'TRUSTED', 'UNKNOWN', 'UNVERIFIED', 'Validated',
    'Value', 'nutrition', 'pricing', 'quantity', 'reviews', 'search',
    'validate', 'variation',
]
