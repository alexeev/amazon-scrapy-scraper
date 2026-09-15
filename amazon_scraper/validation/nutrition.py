"""Validation of a nutrition declaration, without knowing what the food is.

Every rule here fires on a contradiction that is visible without domain
knowledge: a unit that does not match the field it populated, a number that is
part of the phrase describing it, macronutrients that sum to more than the
food they are in, or an energy figure that disagrees with its own
macronutrients.

The division of labour with a category layer is deliberate and visible in the
energy rule: a generic check can prove that energy and macronutrients
*contradict each other*, but not which of the two is wrong. Naming the wrong
side needs plausibility bands, which are category knowledge and arrive as
data (:class:`~.contract.CategoryProfile`).

This module does nothing at all for a record with no food block, which is most
of Amazon. That is the intended shape: the generic layer is a set of rules
that apply where their evidence exists, not a pipeline every category must
pay for.
"""

import re

from .evidence import (ATTRIBUTES, DERIVED, DISPUTED, STRUCTURED, TEXT,
                       TRUSTED, UNKNOWN, UNVERIFIED, Evidence, Value)
from .quantity import relative_gap

# Atwater factors. Food energy is not an independent measurement: it is
# computed from the macronutrients, so the two must agree on any correct
# label. 35% is loose enough for rounding, fibre and polyols, and tight enough
# that a mistyped kJ column (353 kJ where 1489 belongs) cannot hide.
KCAL_PER_G = {'protein_g': 4.0, 'carbohydrates_g': 4.0, 'fat_g': 9.0}
ATWATER_TOLERANCE = 0.35

# Flags that block a value from being promoted to trusted. They are cleared
# only by a rule that explains them away, never by the passage of time.
UNCONFIRMED_BASIS = 'unconfirmed_basis'
CONTRADICTION = 'energy_macro_contradiction'
UNCORROBORATED = 'uncorroborated'
BLOCKING = (UNCONFIRMED_BASIS, CONTRADICTION, UNCORROBORATED)

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

# How the extractor names the structure a nutrition block came from, mapped
# onto the contract's source vocabulary. `text:*` carries the specific field
# after the colon and is handled by prefix.
BLOCK_SOURCES = {'nutrition_card': STRUCTURED, 'attributes': ATTRIBUTES}

# "Eiweiß pro 100g" as a table *header*: the regex that harvests prose
# nutrition anchors on a label followed by a number and a unit, and the basis
# phrase supplies both. The result is a column heading parsed as its own
# value. Seen on B0BP2QDLPQ, which reported 100 g of fibre, carbohydrate and
# protein in the same 100 g of pasta.
BASIS_PHRASE_RE = re.compile(r'(?:pro|per|/)\s*100\s*(?:g|ml|gramm)\b', re.I)


def block_source(source):
    """The contract source for an extractor ``nutrition.source`` string."""
    if (source or '').startswith('text:'):
        return TEXT
    return BLOCK_SOURCES.get(source, TEXT)


def validate(record):
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

    origin = nutrition.get('source') or ''
    source = block_source(origin)
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
        value = Value(amount, UNVERIFIED, _unit_of(key), evidence, source=source)

        if key in derived:
            value.source = DERIVED
            value.notes.append(
                f'derived from {"energy_kj" if key == "energy_kcal" else "source"}, '
                'not published by the vendor')

        rejection = _reject_row(key, row)
        if rejection:
            values[key] = Value(None, UNKNOWN, _unit_of(key), evidence,
                                [rejection], source=source)
            continue

        if source is TEXT and not (row or {}).get('basis_confirmed'):
            value.flags.add(UNCONFIRMED_BASIS)
            value.notes.append(
                'recovered from prose with no stated per-100 g basis; the '
                'figure may be per serving or per pack')
        values[key] = value

    _check_mass_balance(values)
    _check_energy_balance(values)
    _check_corroboration(values)
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


def _check_corroboration(values):
    """A declaration with one nutrient in it has nothing to check itself against.

    Every rule above works by making two statements on the page disagree:
    macronutrients against the mass they sit in, energy against the
    macronutrients it is computed from. A block carrying a single nutrient
    passes all of them vacuously, and vacuous survival is not confirmation --
    so it may be shown, but never trusted.

    The rule was added after the second category, and the measurement is one
    of the cleaner ones in this repository. Thirteen lone-nutrient blocks
    exist across the two validation sets and **all thirteen are artefacts of
    matching a word**: nine dry-pasta records where a prose match read
    "Protein" off marketing copy (six of them reporting 100 g of protein per
    100 g, one reporting 534), and four tyre-lubricant records where the
    German word for grease, *Fett*, is also the word for fat -- "Fett wird in
    einer 100 g Tube geliefert" became 100 g of fat per 100 g. Two of those
    four state "100 g" close enough to the match to satisfy the per-100 g
    basis test, so nothing else in this module stopped them, and dry pasta's
    plausibility band stopped them only because dry pasta has one.
    """
    checkable = [value for key, value in values.items()
                 if key != 'energy_kj' and value.known]
    if len(checkable) >= 2:
        return
    for value in checkable:
        value.flags.add(UNCORROBORATED)
        value.notes.append(
            'the only nutrient stated on the page, so no other value on it '
            'can confirm or contradict this one')


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
    if not implied or relative_gap(implied, energy.value) <= ATWATER_TOLERANCE:
        return

    note = (f'energy ({energy.value:g} kcal) and macronutrients '
            f'({implied:.0f} kcal implied) contradict each other')
    for value in [energy] + [value for _, value in macros]:
        value.notes.append(note)
        value.flags.add(CONTRADICTION)


def apply_bands(values, bands, what='product'):
    """Reject values outside the range the category is known to fall in.

    The bands are the category's entire contribution to nutrition validation:
    everything else here ran before they arrived, and the promotion below runs
    after. A category with no bands still gets every generic rule; it simply
    cannot name which side of a contradiction is the impossible one.
    """
    for key, value in values.items():
        band = (bands or {}).get(key)
        if not band or not value.known:
            continue
        low, high = band
        if not low <= value.value <= high:
            value.dispute(
                f'{value.value:g} {value.unit} per 100 g is outside the '
                f'{low:g}-{high:g} {value.unit} range every real '
                f'{what} falls in')
    return values


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
        return values
    for value in involved:
        if value.status != DISPUTED:
            value.flags.discard(CONTRADICTION)
            value.notes.append(
                'the contradiction above is explained by the disputed value, '
                'so this one stands')
    return values


def promote(values):
    """Trust what survived: unverified, unflagged, never contradicted, not derived.

    A derived nutrient is excluded because the only derivation here is kcal
    from kJ, which is a unit conversion of a single unchecked number: it
    cannot be more believable than the row it came from. That is specific to
    nutrition and deliberately not a property of ``derived`` in general --
    ``price_per_base`` is derived too, and is trusted when the pack size under
    it was confirmed.
    """
    for value in values.values():
        if (value.status == UNVERIFIED and value.known
                and value.source != DERIVED
                and not any(flag in value.flags for flag in BLOCKING)):
            value.status = TRUSTED
    return values
