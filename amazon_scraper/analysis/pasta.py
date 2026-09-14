"""Dry pasta: what the category knows that the generic layers cannot.

Three things live here and nowhere else.

**What counts as dry pasta.** A search for "spaghetti hartweizen" returns a
toilet brush, a cookbook, five ready meals, three chilled pastas and a box of
spice blends. Classification is not a nicety; without it the comparison is
comparing a WC brush to a Gragnano IGP.

**What the numbers should look like.** Dry pasta is ~340-370 kcal, 10-16 g
protein and 65-80 g carbohydrate per 100 g. Those bands are what let the
system name the wrong side of a contradiction the generic layer could only
detect: on B0C3WCFKHT the vendor's energy column is mistyped and the
macronutrients are fine, on B086K1MFSL it is the other way round.

**Which claims matter.** Bronze-die extrusion, slow and low-temperature
drying, Italian wheat, Gragnano IGP. These are deliberately *not* in the
extractor -- they are recovered here from the text it already preserved, which
is why a second category needs no crawler change.

A claim that is absent is reported as "not claimed", never as "no". A producer
may use a bronze die and never write it down.
"""

import re

from .checks import (price_per_kg, promote, reconcile_quantity,
                     resolve_contradictions, validate_nutrition)
from .evidence import (DISPUTED, NOT_CLAIMED, TRUSTED, UNKNOWN, UNVERIFIED,
                       Evidence, Value, search)

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Breadcrumbs are the cheapest and most reliable classifier Amazon gives us:
# on the validation set they separate 163 dry pastas from 32 other things with
# no text analysis at all. Kept as data so a second locale is a data change.
PASTA_BREADCRUMBS = ('nudeln & pasta', 'pasta & noodles')
NOT_DRY_BREADCRUMBS = ('gekühlte pasta', 'fertiggerichte', 'nudelgerichte',
                       'konserven', 'pastasaucen', 'kühlprodukte',
                       'refrigerated', 'canned')

FRESH_RE = re.compile(r'\bfrische\s+(?:pasta|nudeln)|\bpasta fresca\b'
                      r'|\bfresh pasta\b', re.I)

# Raw material, read from the ingredient declaration where possible. The
# declaration is a legal statement; a marketing bullet is not, so a fallback
# to marketing text is reported as unverified.
RAW_MATERIALS = (
    ('durum_wheat', r'hartweizen|durum|semola di grano duro|grano duro|'
                    r'semolina|hartweizengrie(?:ß|ss)'),
    ('wholegrain', r'vollkorn|integrale|wholegrain|whole ?wheat|wholemeal'),
    ('egg', r'\bei(?:er)?\b|eifreiland|vollei|\buovo\b|\buova\b|\begg\b'),
    ('legume', r'linsen|kichererbsen|erbsen|sojabohn|bohnen|lentil|chickpea|'
               r'\blupine|edamame'),
    ('gluten_free_grain', r'maismehl|reismehl|buchweizen|quinoa|hirse|'
                          r'\bmais\b|\breis(?:mehl)?\b|corn flour|rice flour'),
)

# Quality claims. Each is (key, label, pattern, whether the ingredient
# declaration is a valid source for it).
CLAIMS = (
    ('bronze_die', 'Bronze die',
     r'bronze|trafilat[ao]\s+al\s+bronzo|bronzo'),
    ('slow_drying', 'Slow drying',
     r'langsam\w*\s+(?:ge)?trockn|langzeittrocknung|lenta\s+essicc|'
     r'slow[- ]dried|slow drying'),
    ('low_temperature_drying', 'Low-temperature drying',
     r'niedrig\w*\s*temperatur|niedertemperatur|schonend\w*\s+(?:ge)?trockn|'
     r'bassa temperatura|low[- ]temperature'),
    ('gragnano_igp', 'Pasta di Gragnano IGP',
     r'gragnano[^.]{0,40}\b(?:i\.?g\.?p|g\.?g\.?a)\b|'
     r'\b(?:i\.?g\.?p|g\.?g\.?a)\b[^.]{0,40}gragnano'),
    ('italian_wheat', 'Italian wheat',
     r'italienisch\w*\s+(?:hart)?weizen|weizen aus italien|'
     r'grano\s+(?:duro\s+)?(?:100%\s*)?italiano|italian durum wheat'),
    ('made_in_italy', 'Made in Italy',
     r'made in italy|hergestellt in italien|in italien (?:herge|produzi)|'
     r'100\s*%\s*italien|prodotto in italia'),
)

# Drying detail is measured on 2 (temperature) and 7 (duration) of 165 pasta
# records -- too sparse to compare on, kept as a card note only.
DRYING_DETAIL = (
    ('drying_temperature', r'\b(\d{2})\s*°\s*C'),
    ('drying_hours', r'\b(\d{1,3})\s*(?:stunden|std\.?|ore|hours)\b'),
)

# ---------------------------------------------------------------------------
# Category plausibility. Dry pasta is one of the best-characterised foods
# there is; these bands are wide enough for every real durum, wholegrain,
# egg and legume pasta and still reject a mistyped column.
# ---------------------------------------------------------------------------

NUTRITION_BANDS = {
    'energy_kcal': (280.0, 420.0),
    # Stated separately rather than derived from the kcal band: when a vendor
    # mistypes the kJ column (353 kJ where 1489 belongs), the kJ row is the
    # value that is actually wrong, and saying so beats disputing the kcal
    # figure that was computed from it.
    'energy_kj': (1150.0, 1800.0),
    'protein_g': (4.0, 30.0),
    'carbohydrates_g': (35.0, 90.0),
    'fat_g': (0.0, 15.0),
    'fiber_g': (0.0, 20.0),
    'salt_g': (0.0, 5.0),
    'sugars_g': (0.0, 15.0),
    'saturated_fat_g': (0.0, 6.0),
}

# Below this, the pack size is wrong, not the price: no dry pasta on Amazon.de
# retails under a euro a kilo. Above it, the listing is a hamper or a gift box
# rather than pasta to cook with.
PRICE_PER_KG_BAND = (0.80, 40.00)

INGREDIENT_FIELDS = ('food.ingredients',)


def classify(record):
    """Is this dry pasta? A :class:`Value` of 'dry_pasta' / 'other' / unknown."""
    crumbs = [c.lower() for c in record.get('breadcrumbs') or []]
    if not crumbs:
        return Value.unknown('Amazon published no category breadcrumbs')

    trail = Evidence('breadcrumbs', ' > '.join(record['breadcrumbs']))

    for crumb in crumbs:
        if any(bad in crumb for bad in NOT_DRY_BREADCRUMBS):
            return Value('other', TRUSTED, evidence=[trail],
                         notes=['Amazon files it outside dry pasta'])

    if not any(good in crumb for crumb in crumbs for good in PASTA_BREADCRUMBS):
        return Value('other', TRUSTED, evidence=[trail],
                     notes=['not in a pasta category'])

    fresh = search(record, FRESH_RE, limit=1)
    if fresh:
        return Value('other', TRUSTED, evidence=[trail] + fresh,
                     notes=['described as fresh pasta'])

    return Value('dry_pasta', TRUSTED, evidence=[trail])


def raw_materials(record):
    """What the pasta is made of, from the ingredient declaration if possible."""
    declared = ((record.get('food') or {}).get('ingredients') or {}).get('text')
    found, evidence = [], []

    for key, pattern in RAW_MATERIALS:
        hits = search(record, pattern, limit=1,
                      fields=INGREDIENT_FIELDS if declared else None)
        if hits:
            found.append(key)
            evidence.append(hits[0])

    if not found:
        return Value.unknown('no ingredient declaration and no usable '
                             'description of the raw material')
    if declared:
        return Value(found, TRUSTED, evidence=evidence)
    return Value(found, UNVERIFIED, evidence=evidence,
                 notes=['read from marketing text; Amazon publishes no '
                        'ingredient declaration for this product'])


def claims(record):
    """Every V1 quality claim, each present with a quote or explicitly not made."""
    result = {}
    for key, label, pattern in CLAIMS:
        hits = search(record, pattern, limit=2)
        if hits:
            result[key] = Value(True, TRUSTED, evidence=hits)
        else:
            result[key] = Value(
                False, NOT_CLAIMED,
                notes=[f'{label} is not claimed anywhere on the page. That is '
                       f'not the same as it being untrue.'])
    return result


def drying_detail(record):
    """Drying temperature and duration, when the vendor happens to state them."""
    detail = {}
    for key, pattern in DRYING_DETAIL:
        hits = search(record, pattern, limit=1)
        if hits:
            detail[key] = Value(True, UNVERIFIED, evidence=hits)
    return detail


def apply_bands(values):
    """Reject nutrition values that are impossible for dry pasta."""
    for key, value in values.items():
        band = NUTRITION_BANDS.get(key)
        if not band or not value.known:
            continue
        low, high = band
        if not low <= value.value <= high:
            value.dispute(
                f'{value.value:g} {value.unit} per 100 g is outside the '
                f'{low:g}-{high:g} {value.unit} range every real dry pasta '
                f'falls in')
    return values


def nutrition(record):
    """Validated per-100 g nutrition: generic checks, then category bands."""
    values = validate_nutrition(record)
    if not values:
        return {}
    # Order matters. The bands name which side of a contradiction is
    # impossible, so they must run before the contradiction is resolved, and
    # nothing may be promoted to trusted until both have had their say.
    apply_bands(values)
    resolve_contradictions(values)
    return promote(values)


PURE_DURUM_RE = re.compile(
    r'100\s*%\s*(?:italienisch\w*\s+)?(?:hart)?weizen|'
    r'100\s*%\s*(?:semola di\s+)?grano duro|100\s*%\s*durum', re.I)


def check_claim_consistency(card, record):
    """Dispute a "100% durum" claim the ingredient declaration contradicts.

    A vendor writing "100% Hartweizen" in the bullets while declaring egg or
    chickpea flour in the ingredients is not describing the same product. The
    declaration wins -- it is the legally binding text -- and the marketing
    claim is surfaced as disputed rather than dropped.
    """
    materials = card['raw_materials']
    if materials.status != TRUSTED or not materials.value:
        return
    conflicting = [key for key in ('egg', 'legume', 'gluten_free_grain')
                   if key in materials.value]
    if not conflicting:
        return
    hits = search(record, PURE_DURUM_RE, limit=1)
    if not hits:
        return
    card['claims']['pure_durum'] = Value(True, DISPUTED, evidence=hits + materials.evidence,
                                         notes=[
        'the page claims 100% durum wheat, but the ingredient declaration '
        'also lists ' + ', '.join(conflicting)])


def evaluate(record):
    """One dry-pasta evidence card, or a classification-only card."""
    card = {
        'asin': record.get('asin'),
        'title': record.get('title'),
        'brand': record.get('brand'),
        'url': record.get('product_url'),
        'query': record.get('search_query'),
        'category': classify(record),
    }

    if card['category'].value != 'dry_pasta':
        card.update({'raw_materials': Value.unknown('not dry pasta'),
                     'quantity': Value.unknown('not dry pasta'),
                     'price_per_kg': Value.unknown('not dry pasta'),
                     'nutrition': {}, 'claims': {}, 'drying': {}})
        return card

    quantity = reconcile_quantity(record)
    price = price_per_kg(record, quantity)

    if price.known and price.status != DISPUTED:
        low, high = PRICE_PER_KG_BAND
        if not low <= price.value <= high:
            price.dispute(
                f'{price.value:g} {price.unit} is outside the {low:g}-{high:g} '
                f'range real dry pasta sells in, so the pack size behind it is '
                f'probably wrong')

    card.update({
        'raw_materials': raw_materials(record),
        'quantity': quantity,
        'price_per_kg': price,
        'nutrition': nutrition(record),
        'claims': claims(record),
        'drying': drying_detail(record),
    })
    check_claim_consistency(card, record)
    return card


def is_pasta(card):
    return card['category'].value == 'dry_pasta'
