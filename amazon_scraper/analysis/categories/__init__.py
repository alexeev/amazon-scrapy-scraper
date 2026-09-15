"""Built-in category analyzers.

Adding a category means adding one module here. It costs no change to the
crawler, the extractor or the validation layer -- which is the claim R2 was
built to test, and tyre mounting paste is the test: a non-food, classified
from its title rather than its breadcrumbs, sold in units dry pasta never
uses, and ranked on an axis dry pasta would consider backwards.
"""

from . import dry_pasta, mounting_paste  # noqa: F401  (registration side effect)
from ..category import get, known, REGISTRY

__all__ = ['REGISTRY', 'dry_pasta', 'get', 'known', 'mounting_paste']
