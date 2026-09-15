"""Values that carry their own provenance, and the search over a record.

The extraction layer answers "what does the page say". This module is the
vocabulary for the layer above it, which answers a harder question: "how much
of that should we believe". Every number and every claim the platform surfaces
is a :class:`Value`, which names two independent things:

``source``
    *How the value was obtained* -- a structure Amazon renders as data, a
    key/value attribute row, prose written by the vendor, a figure Amazon
    itself computed, or something this layer derived.

``status``
    *Whether it survived validation* -- trusted, disputed, unverified or
    unknown.

Keeping them apart is the whole point, and it is a correction rather than a
refinement. The extractor used to publish a single ``confidence`` that mixed
them, ranking Amazon's structured nutrition card above prose; measured over
the 195-record validation set, ``high``-confidence records failed plausibility
*more* often than ``medium`` ones (5/45 versus 2/40). A well-rendered table is
evidence about the vendor's care in filling a form, not about the number.

A populated field is not a fact. The same validation set contains a structured
nutrition card stating 87.7 kcal/100 g for dry pasta, and a prose match that
turned the phrase "Ballaststoffe pro 100g" into "100 g of fibre". Neither is
an extraction bug. Both are why status, source and evidence travel with the
value rather than being reconstructed later.
"""

import re
from dataclasses import dataclass, field

# -- status: did it survive validation? -------------------------------------

# A value that survived every check that applies to it.
TRUSTED = 'trusted'
# Sources on the page contradict each other, or the value failed a check.
# The value is kept and shown with the contradiction, never silently used.
DISPUTED = 'disputed'
# Nothing contradicts it, but nothing independent confirms it either.
UNVERIFIED = 'unverified'
# We do not know. Distinct from "the page does not say" (absent) and from
# "we looked and found no claim" (see NOT_CLAIMED).
UNKNOWN = 'unknown'

# Only used by claims: we searched every text field and the claim is not made.
# "Not claimed" is not "false" -- a producer may use a bronze die and never
# mention it -- and the distinction has to survive into the output.
NOT_CLAIMED = 'not_claimed'

STATUSES = (TRUSTED, DISPUTED, UNVERIFIED, UNKNOWN, NOT_CLAIMED)

#: Statuses a comparison may act on. Everything else is shown, not used.
USABLE = (TRUSTED,)

# -- source: how was it obtained? -------------------------------------------

# A structure Amazon renders as data: the nutrition card, the twister matrix.
STRUCTURED = 'structured'
# A row of a product-detail key/value table, filed by the vendor.
ATTRIBUTES = 'attributes'
# Prose: the title, a feature bullet, the description, A+ copy.
TEXT = 'text'
# A figure Amazon computed and published, e.g. its own price per unit.
PUBLISHED = 'published'
# Computed here, from other values on the same record.
DERIVED = 'derived'

SOURCES = (STRUCTURED, ATTRIBUTES, TEXT, PUBLISHED, DERIVED)

# A note on ``derived``, because it is the one source whose bearing on status
# is not uniform. A derived value is exactly as good as its inputs, so whether
# it can be trusted depends on whether *they* were validated:
#
# * ``price_per_base`` is derived from price and pack size. When the pack size
#   was confirmed by an independent statement on the page, the quotient is as
#   solid as its inputs and is trusted.
# * a derived *nutrient* -- kcal computed from kJ -- is a unit conversion of a
#   single unchecked number. It adds no evidence about that number, so it can
#   never be more believable than the row it came from, and the nutrition
#   rules refuse to promote it.
#
# Which is why this is a comment and not a constant: a blanket rule here would
# be wrong in one of the two directions, and it was, in the first draft.


@dataclass(frozen=True)
class Evidence:
    """One verbatim quote, and the record field it was read from."""

    field: str
    quote: str

    def __str__(self):
        return f'{self.field}: "{self.quote}"'


@dataclass
class Value:
    """A value, how it was obtained, whether it survived, and what it rests on."""

    value: object = None
    status: str = UNKNOWN
    unit: str = ''
    evidence: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    #: One of :data:`SOURCES`, or ``''`` when there is no value to source.
    source: str = ''
    #: Machine-readable markers for rules that run in two passes, e.g. a
    #: contradiction a generic check found but only a category layer can
    #: attribute. Not shown to the user; ``notes`` carries the wording.
    flags: set = field(default_factory=set)

    @classmethod
    def unknown(cls, *notes):
        return cls(None, UNKNOWN, notes=list(notes))

    @property
    def usable(self):
        """True when a comparison may rank or assert on this value."""
        return self.status in USABLE and self.value is not None

    @property
    def known(self):
        return self.value is not None and self.status != UNKNOWN

    def dispute(self, note, *evidence):
        """Downgrade to disputed, keeping the value and adding the reason."""
        self.status = DISPUTED
        self.notes.append(note)
        self.evidence.extend(evidence)
        return self

    def as_dict(self):
        return {
            'value': self.value,
            'status': self.status,
            'source': self.source,
            'unit': self.unit,
            'notes': list(self.notes),
            'evidence': [{'field': e.field, 'quote': e.quote}
                         for e in self.evidence],
        }


# ---------------------------------------------------------------------------
# Searching a record
# ---------------------------------------------------------------------------

# Ordered most- to least-authoritative. The ingredient declaration is a legal
# statement; a marketing bullet is not. Callers that want the strongest
# evidence for a claim take the first hit.
def text_fields(record):
    """Every free-text field of a record, as ``(field_path, text)`` pairs.

    This is where category signals actually live, in both categories measured
    so far. Dry pasta: bronze-die claims appear in feature bullets (37), the
    description (34), the title (19) and attribute rows (11). Tyre mounting
    paste: the drying claim that decides the whole category appears in feature
    bullets and the description, and nowhere structured at all. Nothing
    category-specific needs to be added to the extractor to find either.
    """
    food = record.get('food') or {}
    content = record.get('content') or {}

    ingredients = (food.get('ingredients') or {}).get('text') or ''
    if ingredients:
        yield 'food.ingredients', ingredients

    if record.get('title'):
        yield 'title', record['title']

    for index, bullet in enumerate(content.get('feature_bullets') or []):
        yield f'content.feature_bullets[{index}]', bullet

    if content.get('description'):
        yield 'content.description', content['description']

    for label, value in (record.get('raw_tables') or {}).items():
        yield f'raw_tables.{label}', f'{label}: {value}'

    for index, section in enumerate(content.get('important_information') or []):
        heading = section.get('heading') or ''
        body = section.get('text') or ''
        yield (f'content.important_information[{index}]',
               f'{heading}: {body}' if heading else body)

    aplus = (content.get('aplus') or {}).get('text') or ''
    if aplus:
        yield 'content.aplus', aplus


_SENTENCE_SPLIT = re.compile(r'(?<=[.!?;])\s+')
QUOTE_MAX = 180


def quote_around(text, start, end):
    """The smallest readable span of `text` that contains [start, end).

    A claim is only credible if the user can read the sentence it came from,
    and a 2 kB A+ blob is not readable. Prefer the sentence; fall back to a
    character window when the "sentence" is a wall of marketing copy.
    """
    left = text.rfind('. ', 0, start) + 1
    for mark in ('! ', '? ', '; ', ' | ', ' - '):
        left = max(left, text.rfind(mark, 0, start) + 1)
    match = _SENTENCE_SPLIT.search(text, end)
    right = match.start() if match else len(text)

    if right - left > QUOTE_MAX:
        left = max(left, start - QUOTE_MAX // 2)
        right = min(right, end + QUOTE_MAX // 2)
    quote = text[left:right].strip()
    prefix = '…' if left > 0 and not text[:left].isspace() else ''
    suffix = '…' if right < len(text) else ''
    return f'{prefix}{quote}{suffix}' if len(quote) < len(text) else quote


def search(record, pattern, limit=3, fields=None):
    """Evidence for `pattern` across a record's text, best source first.

    `fields`, when given, restricts the search -- a claim that is only
    meaningful in the ingredient declaration should not be satisfied by a
    marketing bullet.
    """
    regex = re.compile(pattern, re.I) if isinstance(pattern, str) else pattern
    found = []
    for name, text in text_fields(record):
        if fields is not None and not any(
                name == f or name.startswith(f + '[') or name.startswith(f + '.')
                for f in fields):
            continue
        match = regex.search(text)
        if not match:
            continue
        found.append(Evidence(name, quote_around(text, match.start(), match.end())))
        if len(found) >= limit:
            break
    return found
