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
macronutrients are fine, on B086K1MFSL it is the other way round. They are
handed to the generic layer as data, in a
:class:`~amazon_scraper.validation.CategoryProfile`, and this module never
decides a trust status itself.

**Which claims matter.** Bronze-die extrusion, slow and low-temperature
drying, Italian wheat, Gragnano IGP. These are deliberately *not* in the
extractor -- they are recovered here from the text it already preserved, which
is why a second category needs no crawler change.

A claim that is absent is reported as "not claimed", never as "no". A producer
may use a bronze die and never write it down.
"""

import re

from amazon_scraper.validation import (CategoryProfile, DISPUTED, NOT_CLAIMED,
                                       TRUSTED, UNVERIFIED, Evidence, Value,
                                       validate)

from .. import category as cat

KEY = 'dry_pasta'

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Breadcrumbs are the cheapest and most reliable classifier Amazon gives us
# *for groceries*: on the validation set they separate 163 dry pastas from 32
# other things with no text analysis at all. That is a property of the
# category, not of Amazon -- tyre mounting paste is filed under four unrelated
# breadcrumb roots and has to be classified from the title instead. Kept as
# data so a second locale is a data change.
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

MATERIAL_LABELS = {
    'durum_wheat': 'durum wheat', 'wholegrain': 'wholegrain',
    'egg': 'egg', 'legume': 'legume flour',
    'gluten_free_grain': 'maize / rice / buckwheat',
}

CLAIMS = (
    cat.Claim('bronze_die', 'Bronze die',
              r'bronze|trafilat[ao]\s+al\s+bronzo|bronzo',
              why='a rough surface the sauce holds on to'),
    cat.Claim('slow_drying', 'Slow drying',
              r'langsam\w*\s+(?:ge)?trockn|langzeittrocknung|lenta\s+essicc|'
              r'slow[- ]dried|slow drying',
              why='less starch damage, firmer bite'),
    cat.Claim('low_temperature_drying', 'Low-temperature drying',
              r'niedrig\w*\s*temperatur|niedertemperatur|schonend\w*\s+(?:ge)?trockn|'
              r'bassa temperatura|low[- ]temperature',
              why='protein structure survives drying'),
    cat.Claim('gragnano_igp', 'Pasta di Gragnano IGP',
              r'gragnano[^.]{0,40}\b(?:i\.?g\.?p|g\.?g\.?a)\b|'
              r'\b(?:i\.?g\.?p|g\.?g\.?a)\b[^.]{0,40}gragnano',
              why='a protected designation with an enforced method'),
    cat.Claim('italian_wheat', 'Italian wheat',
              r'italienisch\w*\s+(?:hart)?weizen|weizen aus italien|'
              r'grano\s+(?:duro\s+)?(?:100%\s*)?italiano|italian durum wheat'),
    cat.Claim('made_in_italy', 'Made in Italy',
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
# Category plausibility, handed to the generic layer as data. Dry pasta is one
# of the best-characterised foods there is; these bands are wide enough for
# every real durum, wholegrain, egg and legume pasta and still reject a
# mistyped column.
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

PROFILE = CategoryProfile(key=KEY, label='dry pasta',
                          nutrition_bands=NUTRITION_BANDS,
                          price_band=PRICE_PER_KG_BAND)

def _materials(keys):
    return ', '.join(MATERIAL_LABELS.get(key, key) for key in keys or ())


AXES = (
    cat.Axis('price_per_base', 'Price per kg', better='lower',
             comparative='cheaper per kilogram', tolerance=0.01),
    cat.Axis('quantity', 'Pack size'),
    cat.Axis('raw_materials', 'Made of', render=_materials,
             why='different raw materials — these are not the same kind of pasta'),
    cat.Axis('protein_g', 'Protein', better='higher',
             comparative='higher in protein', tolerance=1.0,
             why='which for durum pasta tracks semolina quality'),
    cat.Axis('energy_kcal', 'Energy'),
    cat.Axis('fiber_g', 'Fibre'),
)

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

    from amazon_scraper.validation import search
    fresh = search(record, FRESH_RE, limit=1)
    if fresh:
        return Value('other', TRUSTED, evidence=[trail] + fresh,
                     notes=['described as fresh pasta'])

    return Value(KEY, TRUSTED, evidence=[trail])


def raw_materials(validated):
    """What the pasta is made of, from the ingredient declaration if possible."""
    record = validated.record
    declared = ((record.get('food') or {}).get('ingredients') or {}).get('text')
    found, evidence = [], []

    for key, pattern in RAW_MATERIALS:
        hits = validated.search(pattern, limit=1,
                                fields=INGREDIENT_FIELDS if declared else None)
        if hits:
            found.append(key)
            evidence.append(hits[0])

    if not found:
        return Value.unknown('no ingredient declaration and no usable '
                             'description of the raw material')
    if declared:
        return Value(found, TRUSTED, evidence=evidence, source='structured')
    return Value(found, UNVERIFIED, evidence=evidence, source='text',
                 notes=['read from marketing text; Amazon publishes no '
                        'ingredient declaration for this product'])


def claims(validated):
    """Every V1 quality claim, each present with a quote or explicitly not made."""
    result = {}
    for claim in CLAIMS:
        hits = validated.search(claim.pattern, limit=2, fields=claim.fields)
        if hits:
            result[claim.key] = Value(True, TRUSTED, evidence=hits, source='text')
        else:
            result[claim.key] = Value(
                False, NOT_CLAIMED,
                notes=[f'{claim.label} is not claimed anywhere on the page. '
                       f'That is not the same as it being untrue.'])
    return result


def drying_detail(validated):
    """Drying temperature and duration, when the vendor happens to state them."""
    detail = {}
    for key, pattern in DRYING_DETAIL:
        hits = validated.search(pattern, limit=1)
        if hits:
            detail[key] = Value(True, UNVERIFIED, evidence=hits, source='text')
    return detail


PURE_DURUM_RE = re.compile(
    r'100\s*%\s*(?:italienisch\w*\s+)?(?:hart)?weizen|'
    r'100\s*%\s*(?:semola di\s+)?grano duro|100\s*%\s*durum', re.I)


def check_claim_consistency(found, materials, validated):
    """Dispute a "100% durum" claim the ingredient declaration contradicts.

    A vendor writing "100% Hartweizen" in the bullets while declaring egg or
    chickpea flour in the ingredients is not describing the same product. The
    declaration wins -- it is the legally binding text -- and the marketing
    claim is surfaced as disputed rather than dropped.
    """
    if materials.status != TRUSTED or not materials.value:
        return
    conflicting = [key for key in ('egg', 'legume', 'gluten_free_grain')
                   if key in materials.value]
    if not conflicting:
        return
    hits = validated.search(PURE_DURUM_RE, limit=1)
    if not hits:
        return
    found['pure_durum'] = Value(
        True, DISPUTED, evidence=hits + materials.evidence, source='text',
        notes=['the page claims 100% durum wheat, but the ingredient '
               'declaration also lists ' + ', '.join(conflicting)])


def evaluate(record):
    """One dry-pasta evidence card, or a classification-only card."""
    classification = classify(record)
    validated = validate(record, PROFILE)

    if classification.value != KEY:
        return cat.card(record, validated, CATEGORY, classification,
                        axes={}, claims={})

    materials = raw_materials(validated)
    found = claims(validated)
    check_claim_consistency(found, materials, validated)

    axes = {
        'price_per_base': validated.price_per_base,
        'quantity': validated.quantity,
        'raw_materials': materials,
    }
    for key in ('protein_g', 'energy_kcal', 'fiber_g'):
        if key in validated.nutrition:
            axes[key] = validated.nutrition[key]

    card = cat.card(record, validated, CATEGORY, classification, axes, found)
    card['drying'] = drying_detail(validated)
    return card


CATEGORY = cat.register(cat.Category(
    key=KEY,
    label='dry pasta',
    profile=PROFILE,
    axes=AXES,
    claims=CLAIMS,
    evaluate=evaluate,
    default_axis='price_per_base',
    blurb='Price per kilogram is the axis this category rests on, so the pack '
          'size behind it is checked against every other statement of it on '
          'the page before any ranking happens.',
))
