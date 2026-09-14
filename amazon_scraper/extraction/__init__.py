"""Rich, marketplace-aware extraction of Amazon product detail pages.

Layering::

    text.py          locale-agnostic text and number primitives
    marketplaces.py  per-location labels, currency and number format
    blocks.py        generic harvesters for Amazon's page structures
    pdp.py           composes one product record and records provenance

Typical use from a spider::

    from amazon_scraper.extraction import PdpExtractor, for_domain

    extractor = PdpExtractor(for_domain('www.amazon.de'))
    record = extractor.extract(response.selector, response.text, lineage)
"""

from .marketplaces import Marketplace, for_domain, supported_domains
from .pdp import SCHEMA_VERSION, PdpExtractor

__all__ = [
    'Marketplace',
    'PdpExtractor',
    'SCHEMA_VERSION',
    'for_domain',
    'supported_domains',
]
