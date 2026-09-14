"""Category-neutral validation of extracted values.

Nothing here knows what pasta is. Every rule fires on a contradiction that is
visible without domain knowledge: a unit that does not match the field it
populated, a number that is part of the phrase describing it, macronutrients
that sum to more than the food they are in, an energy figure that disagrees
with its own macronutrients, or two structures on one page stating different
pack sizes.

These rules are written to be promoted into a shared validation layer (R2)
once a second category confirms which of them generalise. They are here, next
to their first consumer, rather than in a framework with no consumer -- which
is how the extractor ended up with a ``confidence`` field that ranks Amazon's
structured nutrition card above prose while the card fails plausibility more
often (5/45 versus 2/40 on the validation set).

The division of labour with a category layer is deliberate and visible in the
nutrition rules: a generic check can prove that energy and macronutrients
*contradict each other*, but not which of the two is wrong. Naming the wrong
side needs plausibility bands, which are category knowledge.
"""

import re

from ..extraction.text import parse_number
from .evidence import DISPUTED, TRUSTED, UNKNOWN, UNVERIFIED, Evidence, Value

# Atwater factors. Food energy is not an independent measurement: it is
# computed from the macronutrients, so the two must agree on any correct
# label. 35% is loose enough for rounding, fibre and polyols, and tight enough
# that a mistyped kJ column (353 kJ where 1489 belongs) cannot hide.
KCAL_PER_G = {'protein_g': 4.0, 'carbohydrates_g': 4.0, 'fat_g': 9.0}
ATWATER_TOLERANCE = 0.35

# Two sources on one page stating quantities this far apart are not rounding.
QUANTITY_TOLERANCE = 0.15
# Amazon's own price-per-unit versus one derived from price and pack size.
PRICE_COHERENCE_TOLERANCE = 0.12
# A package that weighs a third of its contents is a contradiction, not
# packaging overhead. Used only for the weak package-weight hint.
EXTREME_RATIO = 3.0

# Flags that block a value from being promoted to trusted. They are cleared
# only by a rule that explains them away, never by the passage of time.
DERIVED = 'derived'
UNCONFIRMED_BASIS = 'unconfirmed_basis'
CONTRADICTION = 'energy_macro_contradiction'
BLOCKING = (DERIVED, UNCONFIRMED_BASIS, CONTRADICTION)

MASS_FIELDS = ('protein_g', 'carbohydrates_g', 'fat_g', 'saturated_fat_g',
               'sugars_g', 'fiber_g', 'salt_g')
MACRO_FIELDS = ('protein_g', 'carbohydrates_g', 'fat_g')

# The unit a canonical nutrient key is defined in. A row matched with any
# other unit did not measure this quantity, whatever its label said.
FIELD_UNITS = {
    'energy_kcal': {'kcal'},
    'energy_kj': {'kj'},
    'sodium_mg': {'mg', 'g'},
    **{key: {'g', 'mg'} for key in MASS_FIELDS},
}

# "Eiweiß pro 100g" as a table *header*: the regex that harvests prose
# nutrition anchors on a label followed by a number and a unit, and the basis
# phrase supplies both. The result is a column heading parsed as its own
# value. Seen on B0BP2QDLPQ, which reported 100 g of fibre, carbohydrate and
# protein in the same 100 g of pasta.
BASIS_PHRASE_RE = re.compile(r'(?:pro|per|/)\s*100\s*(?:g|ml|gramm)\b', re.I)


def _relative_gap(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1e-9)


# ---------------------------------------------------------------------------
# Nutrition
# ---------------------------------------------------------------------------

def validate_nutrition(record):
    """Per-nutrient :class:`Value` map for one record.

    Rejects outright (``unknown``) the values that cannot mean anything:
    a unit that contradicts the field, and a number lifted out of the phrase
    that describes the basis. Flags -- but keeps -- values that are merely
    mutually inconsistent, because a generic rule cannot tell which side of an
    inconsistency is the wrong one.
    """
    nutrition = (record.get('food') or {}).get('nutrition') or {}
    per_100g = nutrition.get('per_100g') or {}
    if not per_100g:
        return {}

    source = nutrition.get('source') or ''
    derived = set(nutrition.get('derived') or ())
    rows_by_key = {}
    for row in nutrition.get('rows') or []:
        rows_by_key.setdefault(row.get('key'), row)

    values = {}
    for key, amount in per_100g.items():
        row = rows_by_key.get(key)
        quote = (row or {}).get('value_text') or ''
        evidence = [Evidence(f'food.nutrition[{key}]', f'{(row or {}).get("label", key)}'
                             f': {quote}' if quote else str(amount))]
        value = Value(amount, UNVERIFIED, _unit_of(key), evidence)

        if key in derived:
            value.flags.add(DERIVED)
            value.notes.append(
                f'derived from {"energy_kj" if key == "energy_kcal" else "source"}, '
                'not published by the vendor')

        rejection = _reject_row(key, row)
        if rejection:
            values[key] = Value(None, UNKNOWN, _unit_of(key), evidence, [rejection])
            continue

        if source.startswith('text:') and not (row or {}).get('basis_confirmed'):
            value.flags.add(UNCONFIRMED_BASIS)
            value.notes.append(
                'recovered from prose with no stated per-100 g basis; the '
                'figure may be per serving or per pack')
        values[key] = value

    _check_mass_balance(values)
    _check_energy_balance(values)
    return values


def _unit_of(key):
    if key == 'energy_kcal':
        return 'kcal'
    if key == 'energy_kj':
        return 'kJ'
    return 'mg' if key.endswith('_mg') else 'g'


def _reject_row(key, row):
    """A reason this row cannot be this nutrient at all, or None."""
    if not row:
        return None
    unit = (row.get('unit') or '').lower()
    allowed = FIELD_UNITS.get(key)
    if unit and allowed and unit not in allowed:
        return (f'matched with unit {unit!r}, which does not measure '
                f'{key}: {row.get("value_text", "")!r}')
    value_text = row.get('value_text') or ''
    if BASIS_PHRASE_RE.search(value_text) and _is_basis_number(row, value_text):
        return (f'the number was read out of the basis phrase itself: '
                f'{value_text!r}')
    return None


def _is_basis_number(row, value_text):
    """True when the matched amount is the "100" of "per 100 g"."""
    if row.get('amount') != 100:
        return False
    # If the text carries another number, the 100 may have been incidental.
    numbers = re.findall(r'\d[\d.,]*', value_text)
    return len(set(numbers)) <= 1


def _check_mass_balance(values):
    """Macronutrients cannot outweigh the 100 g they are measured in."""
    present = [(key, values[key]) for key in MACRO_FIELDS
               if values.get(key) and values[key].known]
    total = sum(value.value for _, value in present)
    if total <= 105:
        return
    note = (f'protein + carbohydrate + fat = {total:.0f} g per 100 g, which '
            f'is more than the food itself')
    for _, value in present:
        value.dispute(note)


def _check_energy_balance(values):
    """Energy must agree with the macronutrients it is computed from.

    A generic rule can only report that the two disagree. Which side is wrong
    is a question for a category layer: on B0C3WCFKHT the macronutrients are
    right and the vendor's energy column is mistyped, while on B086K1MFSL the
    energy is right and the carbohydrate row reads 7 g for dry pasta.
    """
    energy = values.get('energy_kcal')
    macros = [(key, values[key]) for key in MACRO_FIELDS
              if values.get(key) and values[key].known]
    if not (energy and energy.known and macros):
        return

    implied = sum(KCAL_PER_G[key] * value.value for key, value in macros)
    if not implied or _relative_gap(implied, energy.value) <= ATWATER_TOLERANCE:
        return

    note = (f'energy ({energy.value:g} kcal) and macronutrients '
            f'({implied:.0f} kcal implied) contradict each other')
    for value in [energy] + [value for _, value in macros]:
        value.notes.append(note)
        value.flags.add(CONTRADICTION)


def resolve_contradictions(values):
    """Settle energy/macronutrient contradictions after category bands ran.

    If plausibility already disputed one side, that side is the explanation:
    the contradiction is accounted for, and the values on the other side are
    released. If neither side is implausible, nothing here can name the
    culprit, so the flag stays and nothing involved can become trusted.
    """
    involved = [value for value in values.values()
                if CONTRADICTION in value.flags]
    if not any(value.status == DISPUTED for value in involved):
        return
    for value in involved:
        if value.status != DISPUTED:
            value.flags.discard(CONTRADICTION)
            value.notes.append(
                'the contradiction above is explained by the disputed value, '
                'so this one stands')


def promote(values):
    """Trust what survived: unverified, unflagged, and never contradicted."""
    for value in values.values():
        if (value.status == UNVERIFIED and value.known
                and not any(flag in value.flags for flag in BLOCKING)):
            value.status = TRUSTED
    return values


# ---------------------------------------------------------------------------
# Package quantity
# ---------------------------------------------------------------------------

_UNIT_GRAMS = {'g': 1.0, 'gr': 1.0, 'gramm': 1.0, 'kg': 1000.0,
               'ml': 1.0, 'l': 1000.0}
_UNIT_RE = '|'.join(sorted(_UNIT_GRAMS, key=len, reverse=True))
# Anchoring a count: "\b" alone is not enough, because the engine happily
# backtracks "500" down to "50" to satisfy a following lookahead, which turned
# "Packung mit 500g" into a fifty-pack and a 25 kg listing.
_WHOLE_COUNT = r'(\d{1,3})(?![\d,.])'
_NOT_A_UNIT = r'(?!\s*(?:%s)\b)' % _UNIT_RE

# "6 x 500 g", "3x500g", "16 x 500 g"
_N_TIMES_W = re.compile(
    r'%s\s*[x×]\s*(\d[\d.,]*)\s*(%s)\b' % (_WHOLE_COUNT, _UNIT_RE), re.I)
# "500 g (16er Pack)", "125g (4er Pack)"
_W_THEN_PACK = re.compile(
    r'(\d[\d.,]*)\s*(%s)\b[^()]{0,12}\(\s*%s\s*er[- ]?Pack'
    % (_UNIT_RE, _WHOLE_COUNT), re.I)
# "16 Packungen mit 500 g", "6 Stück à 250 g"
_N_PACKS_OF_W = re.compile(
    r'%s\s*(?:packung(?:en)?|packs?|st\u00fcck)\s*(?:mit|\u00e0|a|of|von)?\s*'
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


def _grams(amount_text, unit):
    # Titles are written in the marketplace's number format ("1,5 kg"), which
    # the extraction layer already knows how to read.
    amount = parse_number(amount_text, decimal_sep=',')
    return None if amount is None else amount * _UNIT_GRAMS[unit.lower()]


def pack_hints(record):
    """Independent statements of total pack content, as (grams, Evidence).

    "Independent" means: written in the title or the pack-size name, not read
    out of the attribute rows the extractor already used. Amazon's quantity
    attributes are routinely wrong -- a vendor files
    ``Anzahl der Einheiten: 500 gramm`` on a sixteen-pack -- and the extractor
    faithfully reports what it was given. The same vendor also writes a title,
    through a different channel, so when the two disagree that is real
    information rather than noise.

    A count is therefore only combined with a weight stated in the *same*
    string. Multiplying a title's pack count by the attribute table's item
    weight looks appealing and is circular: whether that weight is per item or
    per pack is precisely the question under dispute.
    """
    title = record.get('title') or ''
    size_name = (record.get('package') or {}).get('size_name') or ''
    hints = []

    for source, text in (('title', title), ('package.size_name', size_name)):
        if not text:
            continue

        for match in _N_TIMES_W.finditer(text):
            grams = _grams(match.group(2), match.group(3))
            if grams:
                hints.append((int(match.group(1)) * grams,
                              Evidence(source, match.group(0))))

        for match in _W_THEN_PACK.finditer(text):
            grams = _grams(match.group(1), match.group(2))
            if grams:
                hints.append((int(match.group(3)) * grams,
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


def reconcile_quantity(record):
    """Total pack content in grams, reconciled against independent evidence."""
    package = record.get('package') or {}
    total = package.get('total_quantity_base')
    source = package.get('total_quantity_source') or 'unknown'
    unit = package.get('total_quantity_unit') or 'g'

    if not total:
        return Value.unknown('Amazon publishes no usable pack quantity')

    stated = Evidence(f'package.total_quantity_base ({source})',
                      f'{total:g} {unit}')
    value = Value(total, UNVERIFIED, unit, [stated])

    contradiction = weight_contradiction(record)
    if contradiction and source in ('item_weight_x_count', 'item_weight'):
        return value.dispute(
            'the pack quantity was computed from an item weight the page '
            'itself contradicts', contradiction)

    hints = pack_hints(record)
    if not hints:
        value.notes.append('no independent statement of pack size on the page')
        return value

    agreeing = [(grams, evidence) for grams, evidence in hints
                if _relative_gap(grams, total) <= QUANTITY_TOLERANCE]
    if agreeing:
        value.status = TRUSTED
        value.evidence.append(agreeing[0][1])
        return value

    value.dispute(
        'the pack size Amazon files in its attribute table disagrees with '
        'every other statement of it on the page')
    for grams, evidence in hints[:3]:
        value.evidence.append(
            Evidence(evidence.field, f'{evidence.quote} -> {grams:g} {unit}'))
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
                    if _relative_gap(other, grams) <= QUANTITY_TOLERANCE)
        if votes > best_votes:
            best, best_votes = grams, votes
    return best


def price_per_kg(record, quantity):
    """Price per kilogram, cross-checked against Amazon's own unit price."""
    price = (record.get('price') or {}).get('amount')
    unit_price = record.get('unit_price') or {}
    amazon = unit_price.get('amount') if unit_price.get('unit') == 'kg' else None
    currency = (record.get('price') or {}).get('currency') or ''

    derived = None
    if price and quantity.known and quantity.value:
        derived = price / (quantity.value / 1000.0)

    if derived is None and amazon is None:
        return Value.unknown('no price per kilogram, and none derivable')

    evidence = []
    if amazon is not None:
        evidence.append(Evidence('unit_price', unit_price.get('text') or
                                 f'{amazon:g} {currency}/kg'))
    if derived is not None:
        evidence.append(Evidence(
            'price ÷ package.total_quantity_base',
            f'{price:g} {currency} ÷ {quantity.value:g} g'))

    value = Value(round(derived if derived is not None else amazon, 2),
                  UNVERIFIED, f'{currency}/kg', evidence)

    if quantity.status == DISPUTED:
        value.dispute('derived from a pack size the page contradicts',
                      *quantity.evidence[1:])
        alternative = consensus_hint(record)
        if alternative and price:
            implied = price / (alternative / 1000.0)
            value.notes.append(
                f'if the pack size stated on the page is right, this is '
                f'{implied:.2f} {currency}/kg')
        return value

    if amazon is not None and derived is not None:
        if _relative_gap(amazon, derived) > PRICE_COHERENCE_TOLERANCE:
            if quantity.status == TRUSTED:
                # The pack size was confirmed by the page's own text, so the
                # figure derived from it is the better of the two. Amazon
                # computes its price per unit from the same attribute rows the
                # extractor reads, and on B0G6D354JV -- "Pasta Set 20x500g",
                # 20 items, 500 g each, 10 kg package weight -- Amazon's own
                # per-kilo figure is the one that does not fit.
                value.status = TRUSTED
                value.notes.append(
                    f"Amazon publishes {amazon:g} {value.unit}, which does not "
                    f'fit the pack size stated on the page; the figure above is '
                    f'derived from the pack size instead')
                return value
            return value.dispute(
                f"Amazon's own price per kilogram ({amazon:g}) and the one "
                f'implied by price and pack size ({derived:.2f}) disagree')
        value.status = TRUSTED
        value.notes.append("agrees with Amazon's published price per kilogram")
    elif quantity.status == TRUSTED:
        value.status = TRUSTED
    elif amazon is not None and derived is None:
        value.notes.append(
            'taken from Amazon, with no pack size to check it against')

    return value
