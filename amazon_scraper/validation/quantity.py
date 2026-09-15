"""How much is in the pack, reconciled against everything else the page says.

Amazon's quantity attributes are routinely wrong, and wrong in a way that
survives into every derived figure: a vendor files ``Anzahl der Einheiten:
500 gramm`` on a sixteen-pack, the extractor faithfully reports 500 g, and the
listing is presented at 62.56 EUR/kg instead of 3.91. Amazon's own price per
kilogram agrees, because it is computed from the same row.

So the pack size is never taken on trust. It is compared against every
*independent* statement of it on the page -- the variation matrix's size
dimension, the title, the pack-size name -- and a value that no other source
confirms is reported as unverified rather than as fact.

Nothing here knows what the product is. The rules were written against dry
pasta and then run unchanged over tyre mounting paste, a non-food category
with no nutrition, different pack units and a different idea of what a good
pack size is; the second category found no rule that needed to know.
"""

import re

from ..extraction.text import parse_number
from . import variation
from .evidence import ATTRIBUTES, TRUSTED, UNVERIFIED, Evidence, Value

# Two sources on one page stating quantities this far apart are not rounding.
QUANTITY_TOLERANCE = 0.15

_UNIT_GRAMS = {'g': 1.0, 'gr': 1.0, 'gramm': 1.0, 'kg': 1000.0,
               'ml': 1.0, 'l': 1000.0}
# Which dimension each unit measures. `_UNIT_GRAMS` deliberately maps
# millilitres onto grams so one arithmetic path serves both, and for a *total*
# that is harmless -- the unit travels beside the number. For a corroboration
# it is not: "50 ml" in a bullet does not confirm a 50 g attribute row unless
# the density happens to be 1, and the comparison layer already refuses to set
# a gram pack against a millilitre one. So a statement may only ever confirm a
# total measured in its own dimension.
_UNIT_DIMENSION = {'g': 'mass', 'gr': 'mass', 'gramm': 'mass', 'kg': 'mass',
                   'ml': 'volume', 'l': 'volume'}
_UNIT_RE = '|'.join(sorted(_UNIT_GRAMS, key=len, reverse=True))
# Anchoring a count: "\b" alone is not enough, because the engine happily
# backtracks "500" down to "50" to satisfy a following lookahead, which turned
# "Packung mit 500g" into a fifty-pack and a 25 kg listing.
_WHOLE_COUNT = r'(\d{1,3})(?![\d,.])'
_NOT_A_UNIT = r'(?!\s*(?:%s)\b)' % _UNIT_RE

# "6 x 500 g", "3x500g", "16 x 500 g"
_N_TIMES_W = re.compile(
    r'%s\s*[x×]\s*(\d[\d.,]*)\s*(%s)\b' % (_WHOLE_COUNT, _UNIT_RE), re.I)
# "500 g (16er Pack)", "125g (4er Pack)", "1000 g (Pack of 1)"
_W_THEN_PACK = re.compile(
    r'(\d[\d.,]*)\s*(%s)\b[^()]{0,12}\(\s*(?:%s\s*er[- ]?Pack|Pack\s+of\s+%s)'
    r'\s*\)?'          # quoted back to the user as evidence, so close the paren
    % (_UNIT_RE, _WHOLE_COUNT, _WHOLE_COUNT), re.I)
# "16 Packungen mit 500 g", "6 Stück à 250 g"
_N_PACKS_OF_W = re.compile(
    r'%s\s*(?:packung(?:en)?|packs?|stück)\s*(?:mit|à|a|of|von)?\s*'
    r'(\d[\d.,]*)\s*(%s)\b' % (_WHOLE_COUNT, _UNIT_RE), re.I)
# A leading multiplier with the weight stated later: "16x Garofalo ... mit 500g"
_LEADING_N = re.compile(r'^\s*%s\s*[x×]\s*(?=\D)' % _WHOLE_COUNT, re.I)
# A bare pack count: "(Packung mit 5)", "6er Pack", "pack of 4"
_PACK_COUNT = re.compile(
    r'(?:packung\s+mit\s+%(c)s%(u)s'
    r'|%(c)s\s*er[- ]?pack'
    r'|pack(?:ung)?\s+of\s+%(c)s%(u)s)' % {'c': _WHOLE_COUNT, 'u': _NOT_A_UNIT},
    re.I)
# Any single weight in a string, used as the per-unit weight for a bare count.
_ANY_WEIGHT = re.compile(r'(\d[\d.,]*)\s*(%s)\b' % _UNIT_RE, re.I)


def relative_gap(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1e-9)


def _grams(amount_text, unit):
    # Titles are written in the marketplace's number format ("1,5 kg"), which
    # the extraction layer already knows how to read.
    amount = parse_number(amount_text, decimal_sep=',')
    return None if amount is None else amount * _UNIT_GRAMS[unit.lower()]


def size_label_quantity(label):
    """Grams stated by a twister size label, or None.

    The size dimension *is* the pack content, which is what makes a bare
    weight readable here and not in a title: ``"5 L"`` as a size label means
    the pack holds five litres, while ``"5 L"`` somewhere in a title could be
    anything. A label carrying a pack phrase is left to the general parser,
    which already multiplies it out.
    """
    if not label:
        return None
    for pattern in (_N_TIMES_W, _W_THEN_PACK, _N_PACKS_OF_W):
        if pattern.search(label):
            return None            # a counted phrase: the general rules apply
    match = _ANY_WEIGHT.search(label)
    if not match:
        return None                # "Roségold" is not a quantity
    return _grams(match.group(1), match.group(2))


def pack_hints(record):
    """Independent statements of total pack content, as (grams, Evidence).

    Three sources: the variation matrix's size dimension, the title, and the
    pack-size name. "Independent" means none of them is the attribute row the
    extractor already used for the total. The same vendor who mis-files the
    attribute row also writes a title, through a different channel, so when
    the two disagree that is real information rather than noise.

    A count is therefore only combined with a weight stated in the *same*
    string. Multiplying a title's pack count by the attribute table's item
    weight looks appealing and is circular: whether that weight is per item or
    per pack is precisely the question under dispute.
    """
    title = record.get('title') or ''
    size_name = (record.get('package') or {}).get('size_name') or ''
    variation_label = variation.size_label(record)
    hints = []

    # The twister label is the only one of the three that comes from a
    # different page structure than the attribute rows under dispute, so it is
    # the strongest of them -- and it is present on pages where the attribute
    # table states no pack size at all.
    if variation_label:
        grams = size_label_quantity(variation_label)
        if grams:
            hints.append((grams, Evidence('variation.size_name',
                                          variation_label)))

    for source, text in (('variation.size_name', variation_label),
                         ('title', title),
                         ('package.size_name', size_name)):
        if not text:
            continue

        for match in _N_TIMES_W.finditer(text):
            grams = _grams(match.group(2), match.group(3))
            if grams:
                hints.append((int(match.group(1)) * grams,
                              Evidence(source, match.group(0))))

        for match in _W_THEN_PACK.finditer(text):
            grams = _grams(match.group(1), match.group(2))
            count = match.group(3) or match.group(4)
            if grams and count:
                hints.append((int(count) * grams,
                              Evidence(source, match.group(0))))

        for match in _N_PACKS_OF_W.finditer(text):
            grams = _grams(match.group(2), match.group(3))
            if grams:
                hints.append((int(match.group(1)) * grams,
                              Evidence(source, match.group(0))))

        # A bare count needs a per-unit weight from the same string. A count of
        # one ("1er Pack") says the listing is a single unit, not how much is
        # in it, so it is no evidence about the total at all.
        counts = [int(group) for match in _PACK_COUNT.finditer(text)
                  for group in match.groups() if group]
        leading = _LEADING_N.match(text)
        if leading:
            counts.append(int(leading.group(1)))
        stated = _ANY_WEIGHT.search(text)
        per_unit = _grams(stated.group(1), stated.group(2)) if stated else None
        if per_unit:
            for count in counts:
                if count > 1:
                    hints.append((count * per_unit, Evidence(
                        source, f'{count} x {per_unit:g} g')))

    return hints


def _states_a_pack_count(record, texts):
    """True when anything on the page says the listing holds more than one unit.

    The question this answers is narrow: may a bare weight in the title be
    read as the *total*? Only when nothing claims there is more than one of
    them. A count of one is not a count.
    """
    if ((record.get('package') or {}).get('item_count') or 0) > 1:
        return True
    for text in texts:
        if not text:
            continue
        for match in _PACK_COUNT.finditer(text):
            if any(int(group) > 1 for group in match.groups() if group):
                return True
        leading = _LEADING_N.match(text)
        if leading and int(leading.group(1)) > 1:
            return True
        for pattern in (_N_TIMES_W, _N_PACKS_OF_W):
            for match in pattern.finditer(text):
                if int(match.group(1)) > 1:
                    return True
        for match in _W_THEN_PACK.finditer(text):
            count = match.group(3) or match.group(4)
            if count and int(count) > 1:
                return True
    return False


def single_unit_weights(record):
    """Bare weights the listing states about itself, as (grams, Evidence).

    A bare weight in a title is ambiguous *because of multipacks*: "Garofalo
    Fusilli 500g" on a sixteen-pack states the weight of one box, not of the
    listing, which is why R0 refused to multiply one by a count found
    elsewhere. Take the multipack away and the ambiguity goes with it. When
    nothing anywhere on the page claims more than one unit, the title's weight
    and the attribute table's total are two independent statements of the same
    quantity, written through different channels by the same vendor.

    These hints may only ever **confirm**. A disagreement between a bare
    weight and a total is not evidence of an error -- the weight may still be
    per unit, per tube in a twin-pack, or the shipping weight of a kit -- and
    :func:`reconcile` never disputes on them. The asymmetry is the point, and
    it is what makes the rule safe to apply to a category that was not there
    when it was written: on the dry-pasta validation set it changes no
    disputed value and no trusted one.

    Measured: without it, 2 of 43 tyre mounting pastes had a confirmable pack
    size, because the category simply does not use multipack phrasing -- it
    writes "Reifenmontagepaste 5 kg" and means it.

    The **feature bullets and the description** are read for the same reason,
    and the case that forced it is the sharpest this category has produced. A
    5 g tube of bicycle mounting gel -- the smallest pack in a 127-record
    corpus, on a shelf of five-kilogram tubs, for a user who needs a few grams
    every two years -- states its size in a bullet ("5 g Tube") and in the
    description, and nowhere else: its title is "Tip Top REMAXX Bike Montage
    Fluid Schwarz Einheitsgröße" and its size field says "Einheitsgröße". So
    the one product the ranking existed to surface was the one product the
    ranking dropped, and it was dropped for lacking a second statement that
    was on the page twice.

    Prose is noisier than a size field, which is why the asymmetry above is
    load-bearing rather than incidental: a bullet may only ever confirm a
    total the attribute table already states, never contradict one and never
    supply one on its own. Measured over 127 mounting-paste and 25 dry-pasta
    records, reading them promotes 6 quantities from unverified to trusted,
    changes no value, disputes nothing, and leaves dry pasta untouched.
    """
    texts = [('title', record.get('title') or ''),
             ('package.size_name',
              (record.get('package') or {}).get('size_name') or ''),
             ('variation.size_name', variation.size_label(record))]
    content = record.get('content') or {}
    texts.extend((f'content.feature_bullets[{index}]', bullet)
                 for index, bullet in enumerate(
                     content.get('feature_bullets') or []))
    texts.append(('content.description', content.get('description') or ''))
    if _states_a_pack_count(record, [text for _, text in texts]):
        return []

    wanted = _UNIT_DIMENSION.get(
        ((record.get('package') or {}).get('total_quantity_unit') or '').lower())
    found = []
    for source, text in texts:
        for match in _ANY_WEIGHT.finditer(text or ''):
            if wanted and _UNIT_DIMENSION.get(match.group(2).lower()) != wanted:
                continue
            grams = _grams(match.group(1), match.group(2))
            if grams:
                found.append((grams, Evidence(source, match.group(0))))
    return found


def weight_contradiction(record):
    """A single item that outweighs its own package, as Evidence or None.

    Not a quantity hint -- it states no total -- but proof that the attribute
    table is internally wrong. B0173KFFIG files a 500 g box of pasta as
    ``Artikelgewicht: 10 Kilogramm``, which the extractor then multiplied by
    the twelve-piece count into 120 kg of pasta for 38,80 euro.
    """
    package = record.get('package') or {}
    item = package.get('item_weight_base')
    pack = package.get('package_weight_base')
    if not (item and pack) or item <= pack:
        return None
    return Evidence(
        'raw_tables (Artikelgewicht vs Paketgewicht)',
        f'a single item is filed as {item:g} g while the whole package is '
        f'{pack:g} g')


def reconcile(record):
    """Total pack content, reconciled against independent evidence."""
    package = record.get('package') or {}
    total = package.get('total_quantity_base')
    origin = package.get('total_quantity_source') or 'unknown'
    unit = package.get('total_quantity_unit') or 'g'

    if not total:
        return Value.unknown('Amazon publishes no usable pack quantity')

    stated = Evidence(f'package.total_quantity_base ({origin})',
                      f'{total:g} {unit}')
    value = Value(total, UNVERIFIED, unit, [stated], source=ATTRIBUTES)

    contradiction = weight_contradiction(record)
    if contradiction and origin in ('item_weight_x_count', 'item_weight'):
        return value.dispute(
            'the pack quantity was computed from an item weight the page '
            'itself contradicts', contradiction)

    hints = pack_hints(record)
    agreeing = [(grams, evidence) for grams, evidence in hints
                if relative_gap(grams, total) <= QUANTITY_TOLERANCE]
    if agreeing:
        value.status = TRUSTED
        value.evidence.append(agreeing[0][1])
        return value

    if not hints:
        return _confirm_from_bare_weight(record, value, total)

    value.dispute(
        'the pack size Amazon files in its attribute table disagrees with '
        'every other statement of it on the page')
    for grams, evidence in hints[:3]:
        value.evidence.append(
            Evidence(evidence.field, f'{evidence.quote} -> {grams:g} {unit}'))
    return value


def _confirm_from_bare_weight(record, value, total):
    """Promote a total that a bare, uncounted weight on the page agrees with."""
    for grams, evidence in single_unit_weights(record):
        if relative_gap(grams, total) <= QUANTITY_TOLERANCE:
            value.status = TRUSTED
            value.evidence.append(evidence)
            value.notes.append(
                'the listing states this weight in its own text and claims no '
                'more than one unit, so the two agree')
            return value
    value.notes.append('no independent statement of pack size on the page')
    return value


def consensus_hint(record):
    """The pack size the page's own text agrees on most, or None.

    Used to say what the price *would* be if the attribute table is the thing
    that is wrong. This is a suggestion attached to a disputed value, never a
    silent correction: the page contradicts itself and we do not get to pick a
    winner on the user's behalf.
    """
    hints = pack_hints(record)
    if not hints:
        return None
    best, best_votes = None, 0
    for grams, _ in hints:
        votes = sum(1 for other, _ in hints
                    if relative_gap(other, grams) <= QUANTITY_TOLERANCE)
        if votes > best_votes:
            best, best_votes = grams, votes
    return best
