"""What it costs, and what it costs per unit of content.

Two figures, and the difference between them is the whole of this module.

The **price** is an observation of the offer. Amazon computes it, we read it,
and there is nothing on the page to check it against. The one failure mode
ever measured was an extraction bug -- an unscoped selector picking a
neighbouring product's price out of a carousel -- and it was fixed where it
belonged, by reading only from a real price container.

The **price per unit of content** is a derivation, and derivations are where
this repository's worst numbers came from. It rests on the pack size, which
is a vendor-filed attribute that is wrong often enough to have driven a whole
milestone. So it is cross-checked against Amazon's own published figure, and
when the two disagree the value says so instead of picking a winner.

The base unit follows the pack, not the category: grams reconcile to a price
per kilogram, millilitres to a price per litre. That generalisation was forced
by the second category rather than designed for it -- dry pasta is sold by
weight and every pack in the validation set reconciled to EUR/kg, while tyre
mounting paste and its neighbours on the same search page are sold in tubs,
tubes, bottles and aerosols, and Amazon prices a third of them per litre.
"""

import re

from .evidence import (DERIVED, DISPUTED, PUBLISHED, TRUSTED, UNVERIFIED,
                       Evidence, Value)
from .quantity import relative_gap

# Amazon's own price-per-unit versus one derived from price and pack size.
PRICE_COHERENCE_TOLERANCE = 0.12

# The base unit a pack measured in `g` / `ml` is priced in. Everything the
# platform compares on is per kilogram or per litre; nothing is compared per
# gram, because no marketplace quotes it that way.
BASE_UNIT = {'g': 'kg', 'ml': 'l'}
BASE_DIVISOR = {'g': 1000.0, 'ml': 1000.0}

# How to read the unit Amazon appends to its own published per-unit price.
# Each entry maps the unit text to (dimension, factor onto the base unit):
# a price quoted "pro 100 ml" is ten times smaller than the same price per
# litre, so the factor is 10.
_PUBLISHED_UNITS = {
    'kg': ('kg', 1.0), 'kilogramm': ('kg', 1.0), 'kilogram': ('kg', 1.0),
    'g': ('kg', 1000.0), 'gramm': ('kg', 1000.0), 'gram': ('kg', 1000.0),
    '100 g': ('kg', 10.0), '100 gramm': ('kg', 10.0), '100 gram': ('kg', 10.0),
    'l': ('l', 1.0), 'liter': ('l', 1.0), 'litre': ('l', 1.0),
    'ml': ('l', 1000.0), 'milliliter': ('l', 1000.0),
    '100 ml': ('l', 10.0), '100 milliliter': ('l', 10.0),
}

# Units that measure something other than content. A price "pro Stück" on a
# multipack is the price of one piece, which says nothing about how much is
# in the pack -- and reading it as a content price is exactly the error that
# showed a Barilla listing at 38.56 EUR/kg. Listed rather than inferred, so
# an unrecognised unit is ignored rather than guessed at.
_COUNT_UNITS = ('stück', 'stueck', 'stk', 'st', 'einheit', 'count', 'piece',
                'item', 'blatt', 'sheet', 'waschgang', 'stk.')


def _normalise_unit(text):
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


def published_per_base(unit_price, base_unit):
    """Amazon's own per-unit price, converted onto `base_unit`.

    Returns ``(amount, note)``: the amount when the published unit measures
    the same dimension as the pack, otherwise ``None`` and a note saying why
    the cross-check could not be made. A unit we do not recognise is *never*
    guessed at -- an unchecked value is better than a wrongly checked one.
    """
    amount = (unit_price or {}).get('amount')
    if amount is None or not base_unit:
        return None, ''
    unit = _normalise_unit(unit_price.get('unit'))
    if not unit:
        return None, ''
    known = _PUBLISHED_UNITS.get(unit)
    if not known:
        if any(unit.startswith(count) for count in _COUNT_UNITS):
            return None, (f'Amazon quotes its own unit price per {unit}, which '
                          f'counts pieces rather than content, so it cannot '
                          f'confirm a price per {base_unit}')
        return None, (f'Amazon quotes its own unit price per {unit}, which '
                      f'this layer does not know how to convert')
    dimension, factor = known
    if dimension != base_unit:
        return None, (f'Amazon quotes its own unit price per {unit} while the '
                      f'pack is measured in {"grams" if base_unit == "kg" else "millilitres"}; '
                      f'converting between the two needs a density nobody '
                      f'published')
    return amount * factor, ''


def price(record):
    """What the listing costs, as a :class:`Value`.

    Trusted when present. This is the one number on the page Amazon states
    about itself rather than accepting from a vendor, and unlike every
    quantity attribute it has no measured error rate in this repository. An
    absent price is ``unknown``, and is common: on the R3 verification crawl
    141 of 195 records had one, because the other 54 had no purchasable offer
    at the time.
    """
    block = record.get('price') or {}
    amount = block.get('amount')
    if amount is None:
        return Value.unknown('Amazon published no price for this listing when '
                             'it was crawled')
    currency = block.get('currency') or ''
    return Value(amount, TRUSTED, currency,
                 [Evidence('price', block.get('text') or f'{amount:g} {currency}')],
                 source=PUBLISHED)


def per_base_unit(record, quantity):
    """Price per kilogram or per litre, cross-checked against Amazon's own.

    The unit follows the pack: a pack measured in grams yields a price per
    kilogram, one measured in millilitres a price per litre.
    """
    amount = (record.get('price') or {}).get('amount')
    currency = (record.get('price') or {}).get('currency') or ''
    unit_price = record.get('unit_price') or {}

    pack_unit = quantity.unit if quantity.known else (
        (record.get('package') or {}).get('total_quantity_unit') or '')
    base_unit = BASE_UNIT.get(pack_unit, '')
    published, conversion_note = published_per_base(unit_price, base_unit)

    derived = None
    if amount and quantity.known and quantity.value and base_unit:
        derived = amount / (quantity.value / BASE_DIVISOR[pack_unit])

    if derived is None and published is None:
        return Value.unknown(
            conversion_note or
            f'no price per {base_unit or "unit of content"}, and none derivable')

    evidence = []
    if published is not None:
        evidence.append(Evidence('unit_price', unit_price.get('text') or
                                 f'{published:g} {currency}/{base_unit}'))
    if derived is not None:
        evidence.append(Evidence(
            'price ÷ package.total_quantity_base',
            f'{amount:g} {currency} ÷ {quantity.value:g} {pack_unit}'))

    value = Value(round(derived if derived is not None else published, 2),
                  UNVERIFIED, f'{currency}/{base_unit}', evidence,
                  source=DERIVED if derived is not None else PUBLISHED)
    if conversion_note:
        value.notes.append(conversion_note)

    if quantity.status == DISPUTED:
        value.dispute('derived from a pack size the page contradicts',
                      *quantity.evidence[1:])
        return value

    if published is not None and derived is not None:
        if relative_gap(published, derived) > PRICE_COHERENCE_TOLERANCE:
            if quantity.status == TRUSTED:
                # The pack size was confirmed by the page's own text, so the
                # figure derived from it is the better of the two. Amazon
                # computes its price per unit from the same attribute rows the
                # extractor reads, and on B0G6D354JV -- "Pasta Set 20x500g",
                # 20 items, 500 g each, 10 kg package weight -- Amazon's own
                # per-kilo figure is the one that does not fit.
                value.status = TRUSTED
                value.notes.append(
                    f'Amazon publishes {published:g} {value.unit}, which does '
                    f'not fit the pack size stated on the page; the figure '
                    f'above is derived from the pack size instead')
                return value
            return value.dispute(
                f"Amazon's own price per {base_unit} ({published:g}) and the "
                f'one implied by price and pack size ({derived:.2f}) disagree')
        value.status = TRUSTED
        value.notes.append(f"agrees with Amazon's published price per {base_unit}")
    elif quantity.status == TRUSTED:
        value.status = TRUSTED
    elif published is not None and derived is None:
        value.notes.append(
            'taken from Amazon, with no pack size to check it against')

    return value


def apply_band(value, band, what):
    """Dispute a per-unit price outside the range the category sells in.

    A price far below the floor is not a bargain, it is a pack size that is
    too large by a factor; far above the ceiling and the listing is not the
    product the search was for. Which range that is, is category knowledge,
    so the band arrives as data and this function never guesses one.
    """
    if not band or not value.known or value.status == DISPUTED:
        return value
    low, high = band
    if not low <= value.value <= high:
        value.dispute(
            f'{value.value:g} {value.unit} is outside the {low:g}-{high:g} '
            f'range {what} sells in, so the pack size behind it is probably '
            f'wrong')
    return value


def alternative_price(record, value, consensus):
    """Attach "if the page is right, it would be X" to a disputed price.

    Only when the page's own pack size actually implies a *different* figure.
    A price can be disputed for reasons that have nothing to do with the pack
    size -- a category band, for instance -- and in that case the text on the
    page agrees with the attribute table, so offering it as an alternative
    would print the same number twice and read as a correction that is not one.
    """
    amount = (record.get('price') or {}).get('amount')
    pack_unit = (record.get('package') or {}).get('total_quantity_unit') or 'g'
    if not (amount and consensus and value.status == DISPUTED):
        return value
    implied = amount / (consensus / BASE_DIVISOR.get(pack_unit, 1000.0))
    if value.known and relative_gap(implied, value.value) <= PRICE_COHERENCE_TOLERANCE:
        return value
    value.notes.append(
        f'if the pack size stated on the page is right, this is '
        f'{implied:.2f} {value.unit}')
    return value
