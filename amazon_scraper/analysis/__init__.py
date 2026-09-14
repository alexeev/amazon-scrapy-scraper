"""Offline analysis of crawled Amazon records.

This package sits strictly downstream of the JSONL the spider writes. It does
not import Scrapy, does not fetch anything, and never touches the extraction
layer's decisions -- it reads what was extracted and decides how much of it is
believable.

    records  →  generic checks  →  category knowledge  →  evidence cards
                (checks.py)        (pasta.py)            (report.py)

The layering is the point. ``checks`` knows nothing about pasta; ``pasta``
knows nothing about Amazon's HTML. Adding a second category means adding a
second module beside ``pasta``, with no change to the crawler, the extractor,
or ``checks``.
"""

from .evidence import DISPUTED, NOT_CLAIMED, TRUSTED, UNKNOWN, UNVERIFIED, Value
from .pasta import evaluate, is_pasta

__all__ = ['DISPUTED', 'NOT_CLAIMED', 'TRUSTED', 'UNKNOWN', 'UNVERIFIED',
           'Value', 'evaluate', 'is_pasta']
