"""Category analysis of crawled Amazon records.

This package sits strictly downstream of the JSONL the spider writes and of
:mod:`amazon_scraper.validation`. It does not import Scrapy, does not fetch
anything, and does not decide how much of a value to believe -- that question
is already answered by the time a record reaches here::

    records → validation → category knowledge → evidence cards
              (contract)   (categories/)        (report.py)

What a category adds is the part no generic layer can know: what the product
*is*, which of the vendor's statements matter for it, and what "better" means.
Two are shipped. Dry pasta wants the cheapest trustworthy kilogram; tyre
mounting paste wants the *smallest* pack on the shelf and treats a volume
discount as a trap. Neither re-derives a trust rule, and both read the same
contract.
"""

from ..validation import (DISPUTED, NOT_CLAIMED, TRUSTED, UNKNOWN, UNVERIFIED,
                          Value)
from . import categories
from .category import Axis, Category, Claim, get, is_match, known

__all__ = ['Axis', 'Category', 'Claim', 'DISPUTED', 'NOT_CLAIMED', 'TRUSTED',
           'UNKNOWN', 'UNVERIFIED', 'Value', 'categories', 'get', 'is_match',
           'known']
