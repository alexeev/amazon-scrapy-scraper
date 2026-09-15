"""Reading Amazon's variation matrix: which ASINs are the same product.

The crawler stores the twister blob verbatim and interprets nothing (R1). This
is the interpretation, and it is deliberately thin: identify the family an ASIN
belongs to, and pull out the one dimension value that means a pack size.

Two things make that worth doing, and the first is smaller than it looks.

**Comparison.** When search returns two listings of one product in different
boxes, ranking them as rivals is wrong twice over: it doubles a producer's
apparent presence, and it implies a quality difference where only the pack
differs. Measured on a three-query Amazon.de crawl this is uncommon -- a
handful of offers out of a couple of hundred listings -- because most families
surface once. It is worth handling anyway, because when it does happen the
answer is interesting: the same pasta turned up in two listings priced 29%
apart per kilo, and a five-pack that costs *more* per kilo than the single box
beside it.

**Quantity.** The more reliable payoff. The size dimension is an independent
statement of what is in the pack, from a different structure than the
attribute table that gets pack sizes wrong -- and it is sometimes the only
pack size on the page, because ``Paketgröße - Name`` is empty.

Note that the extraction corpus overstates how common the matrix is. Those
pages were chosen for layout diversity, so 24 of 34 carry one; on records from
an ordinary search crawl it is closer to one in five.

What it does *not* do is guess. The matrix names its own dimensions, so the
size dimension is looked up rather than inferred: a product whose only
dimension is ``color_name`` yields no quantity, and "Roségold" is never parsed
as a weight.
"""

import re

# The dimension that means "how much is in the pack". Amazon names its own
# dimensions, so this is a lookup, not a heuristic. Other dimensions seen on
# the corpus -- flavor_name, color_name, style_name -- say nothing about
# quantity and are left alone.
SIZE_DIMENSIONS = ('size_name', 'size')


def matrix(record):
    """The decoded variation matrix, or ``{}`` for a record without one.

    Records crawled before schema v3 have no ``variation`` key at all; they
    degrade to "this product has no known family", which is true.
    """
    data = record.get('variation') or {}
    return data if data.get('values_by_asin') else {}


def dimension_value(data, asin, wanted=SIZE_DIMENSIONS):
    """The value of one named dimension for one ASIN in the matrix.

    ``dimensions`` and each member's value list are positional and always the
    same length, so the dimension name indexes straight into the values.
    """
    dimensions = data.get('dimensions') or []
    values = (data.get('values_by_asin') or {}).get(asin) or []
    if len(dimensions) != len(values):
        return ''
    for index, dimension in enumerate(dimensions):
        if dimension in wanted:
            return values[index]
    return ''


def size_label(record):
    """This record's own pack-size label, e.g. ``"500 g (5er Pack)"``."""
    data = matrix(record)
    if not data:
        return ''
    return dimension_value(data, record.get('asin'))


def family_key(record):
    """A stable identity for the product family, or None.

    Amazon's ``parentAsin`` is the family's own id and is never one of the
    buyable members -- it was present and distinct on all 24 corpus pages that
    have a matrix -- which makes it exactly the key we want.
    """
    data = matrix(record)
    if not data:
        return None
    parent = data.get('parent_asin')
    if parent:
        return parent
    # No parent: the member set still identifies the family uniquely.
    members = sorted(data.get('values_by_asin') or {})
    return f'set:{",".join(members)}' if len(members) > 1 else None


def siblings(record):
    """Every ASIN Amazon lists in this record's family, including its own."""
    return sorted((matrix(record).get('values_by_asin') or {}))


# A pack phrase at the end of a *non-size* dimension value: the size dimension
# leaking into the style label, as in "Penne Rigate Integrale, 6x500g" beside
# a plain "Penne Rigate Integrale". Stripping it is narrow on purpose -- what
# is removed is a quantity, which is the size dimension's job to state.
_PACK_SUFFIX_RE = re.compile(
    r'[,;]?\s*\(?\s*\d{1,3}\s*[x\u00d7]\s*\d[\d.,]*\s*'
    r'(?:g|gr|gramm|kg|ml|l)\b\s*\)?\s*$', re.I)


def variant_signature(data, asin):
    """What distinguishes this ASIN from its siblings *apart from* pack size.

    A family is not one product. ``B088419TTP``'s family holds spaghetti,
    penne and fusilli under one parent, and collapsing all of it into a single
    comparison row would hide a difference a cook cares about while fixing one
    they do not. So only the size dimension is collapsed, and everything else
    is kept as the identity of the offer.
    """
    dimensions = data.get('dimensions') or []
    values = (data.get('values_by_asin') or {}).get(asin) or []
    if len(dimensions) != len(values):
        return ()
    return tuple(
        _PACK_SUFFIX_RE.sub('', value).strip().casefold()
        for dimension, value in zip(dimensions, values)
        if dimension not in SIZE_DIMENSIONS)


def offer_key(record):
    """Identity of "this product, in whatever pack size", or None.

    ``None`` means the record cannot be grouped -- no matrix, or a family
    Amazon lists only one member of -- and it is then its own offer.
    """
    data = matrix(record)
    if not data:
        return None
    family = family_key(record)
    if not family:
        return None
    return (family, variant_signature(data, record.get('asin')))


def offer_index(records, asin_of=lambda record: record.get('asin')):
    """``{asin: offer key}`` pooled from every matrix in a set of records.

    A matrix describes the whole family, not just the ASIN whose page it came
    from, so one record's matrix can place a sibling that has no matrix of its
    own -- Amazon does not render the twister on every member. Pooling the
    claims first is therefore strictly better than asking each record about
    itself, and it is free: the evidence is already in hand.
    """
    index = {}
    for record in records:
        data = matrix(record)
        if not data:
            continue
        family = family_key(record)
        if not family:
            continue
        for asin in (data.get('values_by_asin') or {}):
            index.setdefault(asin, (family, variant_signature(data, asin)))
    return index


def group_offers(records, key=None, asin_of=lambda record: record.get('asin')):
    """Group records by offer: same product, different pack sizes.

    Returns ``[(key, [record, ...]), ...]``, biggest group first. A record we
    cannot place is its own group, which is the honest answer rather than a
    failure: Amazon may well list siblings we did not crawl, and going to
    fetch them is a discovery decision, not this one.
    """
    index = offer_index(records, asin_of)

    def identify(record):
        if key is not None:
            explicit = key(record)
            if explicit is not None:
                return explicit
        return index.get(asin_of(record)) or offer_key(record)

    groups, ungrouped = {}, []
    for record in records:
        identity = identify(record)
        if identity is None:
            ungrouped.append(record)
        else:
            groups.setdefault(identity, []).append(record)

    result = list(groups.items())
    result.extend((None, [record]) for record in ungrouped)
    result.sort(key=lambda item: (-len(item[1]), str(item[0] or '')))
    return result
