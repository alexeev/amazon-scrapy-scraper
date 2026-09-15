# The extraction and validation contract

What downstream code may rely on, what it may not, and what has to change
before either of those changes. Two artefacts are published here:

| Artefact | Version | Produced by | Answers |
|---|---|---|---|
| **Product record** | `SCHEMA_VERSION = 4` | `amazon_scraper.extraction` | what the page says |
| **Validated record** | `CONTRACT_VERSION = 1` | `amazon_scraper.validation` | how much of that holds up |

They are versioned separately because they change for different reasons and
have different consumers. An extractor learning to read a new Amazon
structure moves the first; a rule learning that a value cannot be confirmed
moves the second.

```text
extraction  ──►  validation  ──►  category analysis  ──►  report
schema v4        contract v1      analysis/categories/    analysis/report.py
```

---

## 1. Why there are two layers and not one

A populated field is not a fact. Amazon's *structured* nutrition card states
87.7 kcal per 100 g for dry pasta on one record and 7 g of carbohydrate on
another; a sixteen-pack of Garofalo reports €62.56/kg because the vendor filed
`Anzahl der Einheiten: 500 gramm`, and Amazon's own price per kilogram agrees
with it because it is computed from the same wrong row.

The extractor's job is to be faithful to the page, including when the page is
wrong. Deciding what to believe is a separate job, with separate evidence, and
it is done once — not per category.

### The mistake this replaces

Schema v3 published `food.nutrition.confidence` (`high` / `medium` / `low`),
set from *which structure* the numbers came from. Measured over the
195-record Amazon.de validation set, `high`-confidence records failed
plausibility checks **more** often than `medium` ones — 5 of 45 against 2 of
40. A well-rendered table is evidence about the care a vendor took filling in
a form. It is not evidence about the number.

So v4 removes `confidence` and the contract splits it in two:

- **`source`** — how the value was obtained. Extraction may state this,
  because it knows it and it is a fact about the page.
- **`status`** — whether the value survived checking. Only the validation
  layer may state this, and never from the source alone.

---

## 2. The product record (schema v4)

One JSON object per line. Every group degrades to `{}` / `[]` rather than
disappearing, so consumers can index without guards.

| Group | Keys |
|---|---|
| envelope | `schema_version`, `fetched_at` |
| lineage | `marketplace`, `asin`, `product_url`, `canonical_url`, `search_query`, `search_page`, `search_position`, `run_id`, `locale`, `accept_language` |
| core | `title`, `brand`, `byline_text`, `brand_url`, `price{amount,currency,text}`, `unit_price{amount,unit,text}`, `rating{value,count,text,count_text}`, `availability`, `seller`, `breadcrumbs[]` |
| package | `item_weight_*`, `package_weight_*`, `unit_count_*`, `volume_*`, `item_count`, `size_name`, `dimensions`, `total_quantity_base`, `total_quantity_unit`, `total_quantity_source` |
| content | `feature_bullets[]`, `description`, `important_information[{heading,text}]`, `aplus{module_types,headings,text,text_length,images,tables}` |
| food | `ingredients{text,source}`, `allergens[]`, `nutrition{source,basis_text,per_100g,rows,derived}` |
| attributes | `attributes{}` (canonical), `raw_tables{}` (verbatim), `attribute_sources{}` |
| media | `images[{url,variant,alt,thumb}]`, `primary_image`, `image_count`, `image_source` |
| variation | `dimensions[]`, `display_labels{}`, `variation_values{}`, `values_by_asin{asin:[…]}`, `current_asin`, `parent_asin`, `total_variations` — decoded verbatim, never interpreted |
| diagnostics | `extraction{blocks_present[],blocks_absent[],errors[]}` |

`nutrition.per_100g` uses canonical keys: `energy_kj`, `energy_kcal`,
`protein_g`, `fat_g`, `saturated_fat_g`, `carbohydrates_g`, `sugars_g`,
`fiber_g`, `salt_g`, `sodium_mg`.

`nutrition.source` is one of `nutrition_card`, `attributes`, or `text:<field>`
— **which structure the numbers came from, and nothing more**.

`package.total_quantity_base` is grams or millilitres, and
`total_quantity_unit` says which. The unit follows the attribute row the total
was read from — not a volume mentioned elsewhere on the page. Before v4 it was
inferred from any volume field present, which reported a 50 ml sponge tin as
50 g and then priced it per kilogram.

---

## 3. The validated record (contract v1)

`amazon_scraper.validation.validate(record, profile) -> Validated`

```python
from amazon_scraper.validation import validate, CategoryProfile

validated = validate(record, CategoryProfile(key='paint', label='wall paint'))
validated.quantity.status        # 'trusted'
validated.quantity.source        # 'attributes'
validated.price_per_base.unit    # 'EUR/l'
validated.as_dict()              # JSON-serialisable, snapshot-tested
```

| Field | Type | Meaning |
|---|---|---|
| `contract_version`, `schema_version` | int | this shape, and the record's |
| `category_profile` | str | the profile's `key`, or `'product'` for none |
| `asin`, `title`, `brand`, `url`, `marketplace`, `query`, `run_id`, `locale` | str | lineage, copied |
| `offer` | `(family, signature)` or `None` | identity of "this product, in whatever pack size" |
| `size_label`, `siblings`, `variation` | str / list / dict | Amazon's own pack label and family |
| `quantity` | `Value` | total pack content, in `g` or `ml` |
| `price` | `Value` | what the listing costs |
| `price_per_base` | `Value` | price per kilogram or per litre, following the pack's unit |
| `nutrition` | `{key: Value}` | per 100 g; `{}` for anything that is not food |
| `record` | dict | the record it was built from, for category text search |

### `Value`

```python
Value(value, status, unit, evidence=[Evidence(field, quote)], notes=[], source='')
```

`.usable` is true only for `trusted` values with a value. Nothing else may be
ranked on or asserted from.

### Status vocabulary

| Status | Meaning |
|---|---|
| `trusted` | survived every check that applies to it |
| `disputed` | sources on the page contradict each other, or a check failed — shown with the contradiction, never ranked |
| `unverified` | nothing contradicts it, nothing independent confirms it |
| `unknown` | we do not know; distinct from "the page does not say" |
| `not_claimed` | we searched every text field and the claim is not made — which is not the same as it being untrue |

### Source vocabulary

| Source | Meaning |
|---|---|
| `structured` | a structure Amazon renders as data: the nutrition card, the twister matrix |
| `attributes` | a row of a product-detail key/value table, filed by the vendor |
| `text` | prose: the title, a bullet, the description, A+ copy |
| `published` | a figure Amazon computed and published, e.g. its own price per unit |
| `derived` | computed here, from other values on the same record |

**A source never implies a status.** The nearest thing to an exception is
`derived`, and it is not one: a derived value is exactly as good as its
inputs, so whether it can be trusted depends on whether *they* were
validated. `price_per_base` is derived from price and pack size, and is
trusted when the pack size was confirmed by an independent statement on the
page. A derived *nutrient* — kcal computed from kJ — is a unit conversion of a
single unchecked number, adds no evidence about it, and is never promoted.

`Evidence.field` carries the precise origin; `source` is the coarse kind.

---

## 4. What the generic rules check

Each fires only where its evidence exists. A record with no food block pays
nothing for the nutrition rules.

**Pack quantity** — the attribute total against every *independent* statement
of it on the page: the variation matrix's size dimension, the title, the
pack-size name. A count is only ever combined with a weight stated in the
same string; multiplying a title's pack count by the attribute table's item
weight is circular, because whether that weight is per item or per pack is the
question under dispute. A bare, uncounted weight in the listing's own text may
**confirm** a total and may never contradict one.

**Price per base unit** — derived from price and pack size, cross-checked
against Amazon's own published per-unit figure. The published figure is
converted onto the pack's own dimension (`kg`, `100 g`, `l`, `ml`, `100 ml`)
and **refused** when it counts pieces rather than content, or when converting
it would need a density nobody published.

**Nutrition** — a unit that cannot measure the field it populated; a number
lifted out of the "per 100 g" phrase that describes the basis; macronutrients
summing to more than the food they sit in; energy disagreeing with the
macronutrients it is computed from (Atwater, 35% tolerance); and a declaration
carrying a single nutrient, which has nothing on the page to confirm it.

**Variation** — family identity and the pack-size dimension, looked up by
Amazon's own dimension names, never inferred.

---

## 5. What a category supplies, and what it may not

A category hands the generic layer a `CategoryProfile`, which is **data only**:

```python
CategoryProfile(
    key='dry_pasta',
    label='dry pasta',
    nutrition_bands={'protein_g': (4.0, 30.0), ...},   # per 100 g
    price_band=(0.80, 40.00),                          # per kg or per litre
)
```

A profile cannot add a rule, reorder the pipeline, or set a status. That is
deliberate, and it is the part of R2 that took the longest to get right,
because the ordering is not obvious:

```text
detect  →  category bands  →  resolve contradictions  →  promote
```

A generic check can prove that an energy figure and its own macronutrients
contradict each other, but not which side is wrong; a plausibility band can
say which value is impossible, but only for a named category. So the bands run
in the middle, and **nothing is promoted to `trusted` until both have
spoken**. While this sequence lived inside the pasta module, the pasta module
*was* the specification, and a second category would have had to copy four
lines of ordering it had no way to know were load-bearing.

`price_band=None` is a legitimate answer, not a gap. Tyre mounting paste
spans 50 ml tubes and 5 kg workshop tubs priced two orders of magnitude apart
per kilogram; inventing a band to have one would reject real listings.

A category analyzer then adds what only it can know — what the product *is*,
which of the vendor's statements matter, and which direction is better — and
returns a card. `tests/test_mounting_paste.py` asserts mechanically that it
imports no rule and settles no numeric value of its own.

---

## 6. Compatibility policy

### Within a version

May change without a bump, because no correct consumer can depend on it:

- adding a key to the record or to `Validated`;
- adding a `status`- or `source`-bearing value to a group that already exists;
- the **wording** of a `note`, and the span of an evidence `quote`;
- which `Evidence` entries accompany a value, and their order;
- a value moving to a *more* conservative status (`trusted` → `unverified` →
  `disputed`/`unknown`) because a new rule found something.

### Requires a version bump

- removing or renaming a key, a `status` value or a `source` value;
- changing the unit or scale of a published number;
- changing what a `status` *means*;
- a value moving to a *less* conservative status by default — that is a claim
  about trustworthiness, and it has to be argued for and measured.

### How a bump is done

1. Change the code and bump `SCHEMA_VERSION` (`extraction/pdp.py`) or
   `CONTRACT_VERSION` (`validation/contract.py`).
2. Add a line to §7 saying what moved and why.
3. Regenerate the corpus snapshots and **read the diff**:
   ```bash
   uv run python tests/test_corpus.py --update
   ```
   `tests/corpus/` pins both artefacts over 39 saved real pages —
   `expected.jsonl.gz` for extraction and `validated.jsonl.gz` for the
   contract, the latter deliberately produced with *no* category profile, so
   what is pinned is the layer that belongs to nobody.
4. Records already on disk keep their own `schema_version`. The validation
   layer reads v2 and v3 records unchanged; older records simply carry fields
   it ignores.

---

## 7. Version history

| Version | Change |
|---|---|
| schema v1 | the original rich PDP record |
| schema v2 | crawl provenance: `run_id`, `locale`, `accept_language` (R1) |
| schema v3 | `variation`: the twister matrix, decoded verbatim (R1) |
| **schema v4** | removed `food.nutrition.confidence`; `package.total_quantity_unit` now follows the row the total came from (R2) |
| **contract v1** | first published validated record (R2) |

---

## 8. What the second category changed

R2's premise was that a rule earns promotion once a *second* consumer has
exercised it. The second consumer is tyre mounting paste: a non-food, with no
nutrition, sold in tubs, tubes, bottles and aerosols, classified from its
title because Amazon files it under four unrelated departments, and ranked on
*smallest pack first* — the opposite of what dry pasta wants. 90 records,
three Amazon.de queries, 93 requests, 93 × HTTP 200, 0 retries, 0 challenges.

**Every trust rule transferred unchanged.** Nothing in the quantity, price or
variation logic needed to know what the product was. What did change:

1. **Price per unit was hard-wired to kilograms.** Every pack in the dry-pasta
   set is a mass, so nothing had ever asked. A third of the paste listings are
   priced per litre by Amazon, and the layer ignored those figures entirely
   rather than converting them. Now the base unit follows the pack, Amazon's
   published unit price is converted onto it, and a per-*piece* figure is
   refused rather than misread — which is the error that once showed a Barilla
   listing at €38.56/kg.

2. **An extraction bug surfaced.** `total_quantity_unit` was inferred from any
   volume field on the page rather than from the row the total came from, so a
   50 ml tin filed as `Anzahl der Einheiten: 50.0 milliliter` was reported as
   50 g. 16 of 90 paste records are affected; 1 of 39 corpus pages changed,
   and that one — a 5 L olive-oil canister filed as 5 kg — loses a per-litre
   figure that had been `trusted` on the strength of the old guess. It is now
   an unverified price per kilogram with a note saying the two cannot be
   reconciled without a density. That is the honest reading.

3. **A confidently wrong nutrition value was one step away.** German *Fett*
   means grease as well as fat, so four listings here state a pack size beside
   the word and the food parser reads a nutrition declaration: `Fett wird in
   einer 100 g Tube geliefert` → 100 g of fat per 100 g. Two of the four state
   "100 g" close enough to satisfy the per-100 g basis test, so nothing in the
   generic layer stopped them — dry pasta was protected only by having a
   plausibility band. The rule that was missing is category-neutral: **a
   declaration carrying one nutrient has nothing on the page to confirm it, so
   it can be shown but never trusted.** Thirteen lone-nutrient blocks exist
   across the two validation sets and all thirteen are artefacts of matching a
   word — nine in dry pasta, six of those reporting 100 g of protein per 100 g
   and one reporting 534.

4. **Pack quantity could barely be confirmed at all.** The hint parser only
   understood multipack phrasing — "6 × 500 g", "500 g (5er Pack)" — which
   this category does not use. It writes "Reifenmontagepaste 5 kg" and means
   it. 2 of 43 pastes had a confirmable pack size. The rule added is narrow
   and asymmetric: when nothing anywhere on the page claims more than one
   unit, a bare weight in the listing's own text is an independent statement
   of the same quantity and may **confirm** the attribute total — never
   contradict it, because the weight may still be per unit or a kit's shipping
   weight. On dry pasta it moves 23 records from `unverified` to `trusted` and
   leaves every `disputed` and every `unknown` exactly as it was.

### Measured, both categories, after R2

| | dry pasta (195 records) | tyre mounting paste (90 records) |
|---|---|---|
| Classified | 165 / 30 other / 0 unclassified | 43 / 47 other / 0 unclassified |
| Pack quantity | 131 trusted · 13 disputed · 14 unverified · 7 unknown | 25 trusted · 1 disputed · 6 unverified · 11 unknown |
| Price per base unit | 100 trusted · 9 disputed · 2 unverified · 54 unknown | 13 trusted · 1 disputed · 1 unverified · 28 unknown |
| At least one trusted axis | 117 of 165 | 32 of 43 |

Effect of R2 on dry pasta, same records, same code path:

| | before | after |
|---|---:|---:|
| Pack quantity trusted | 108 | **131** |
| Pack quantity unverified | 37 | **14** |
| Pack quantity disputed / unknown | 13 / 7 | 13 / 7 *(identical)* |
| Price per base unit | 100 trusted | 100 trusted *(identical)* |
| Protein trusted | 61 | 60 |

The one lost protein figure is `B0D4R3N142`, a lupin-flour pasta whose only
nutrition value is `"Protein und 9g"` scraped out of marketing copy — a
figure that is implausibly *low* for the product it describes.
