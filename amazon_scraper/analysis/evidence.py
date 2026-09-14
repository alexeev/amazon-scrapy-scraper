"""Values that carry their own provenance, and the search over a record.

The extraction layer answers "what does the page say". This module is the
vocabulary for the layer above it, which answers a harder question: "how much
of that should we believe". Every number and every claim the analysis surfaces
is a :class:`Value`, which is either trusted, disputed, unverified or unknown,
and which names the source text it came from.

A populated field is not a fact. The 195-record validation set contains a
nutrition table Amazon rendered as a structured card -- the highest-confidence
source there is -- stating 87.7 kcal/100 g for dry pasta, and a prose match
that turned the phrase "Ballaststoffe pro 100g" into "100 g of fibre". Neither
is an extraction bug. Both are why status and evidence travel with the value
rather than being reconstructed later.
"""

import re
from dataclasses import dataclass, field

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

#: Statuses a comparison may act on. Everything else is shown, not used.
USABLE = (TRUSTED,)


@dataclass(frozen=True)
class Evidence:
    """One verbatim quote, and the record field it was read from."""

    field: str
    quote: str

    def __str__(self):
        return f'{self.field}: "{self.quote}"'


@dataclass
class Value:
    """A value, its trust status, why, and what it rests on."""

    value: object = None
    status: str = UNKNOWN
    unit: str = ''
    evidence: list = field(default_factory=list)
    notes: list = field(default_factory=list)
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

    This is where category signals actually live. Measured over the 195-record
    validation set: bronze-die claims appear in feature bullets (37), the
    description (34), the title (19) and attribute rows (11) -- and in A+
    content on 6 records, none of which are A+-only. Nothing pasta-specific
    needs to be added to the extractor to find them.
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
