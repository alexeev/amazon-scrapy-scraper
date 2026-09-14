# Rich PDP extraction layer — technical report

Scope: replace the baseline's handful of PDP selectors with a structured,
marketplace-aware extraction layer, and produce evidence that it works on real
amazon.de product pages. The validated `search → pagination → PDP → JSONL`
crawl flow is retained; only the PDP parsing stage was rebuilt.

---

## 1. Investigation

### 1.1 Method

34 live amazon.de PDPs were downloaded to disk with the production settings
profile (same UA, headers and throttle as the real crawler) and then analysed
offline, so every structural claim below is measured against the exact bytes
the spider receives.

The sample was chosen for layout diversity, not just for pasta:

| Query | PDPs |
|---|---|
| `spaghetti hartweizen` | 6 |
| `pasta di gragnano igp` | 5 |
| `penne rigate bio vollkorn` | 5 |
| `bronze gezogen pasta italien` | 4 |
| `vollkorn dinkel spaghetti` | 4 |
| `olivenoel nativ extra italien` | 4 |
| `basmati reis 1kg` | 3 |
| `bluetooth kopfhoerer` | 3 |

The last two groups are deliberate controls: a non-pasta grocery product and a
non-grocery product, to check that the design does not silently depend on
pasta or even on food.

### 1.2 Where the data actually lives

Presence across the 34-PDP sample:

| Structure | Present | Notes |
|---|---:|---|
| `#productTitle` | 34/34 | |
| `#bylineInfo` | 34/34 | brand *or* a store link, needs cleanup |
| `#corePrice_feature_div` | 34/34 | |
| `#wayfinding-breadcrumbs_feature_div` | 34/34 | category lineage |
| `colorImages` gallery blob | 34/34 | see §1.3 |
| `#landingImage[data-a-dynamic-image]` | 34/34 | image fallback |
| `#acrPopover` (rating) | 33/34 | |
| `table.a-normal.a-spacing-micro` | 31/34 | product overview k/v |
| `#detailBullets_feature_div` | 31/34 | label/value bullets |
| `#important-information` | 31/34 | headed sections |
| `#feature-bullets` | 31/34 | |
| `nutritionalInfoAndIngredients_feature_div` | 34/34 | container |
| `#nic-ingredients-content` | 21/34 | server-rendered ingredients |
| `#aplus` (A+ content) | 21/34 | |
| `#productDescription` | 17/34 | largely complementary to A+ |
| `#prodDetails` tech-spec tables | 6/34 | mostly non-grocery |
| `#nic-eu-nutrition-facts` | 4/34 | structured nutrition |
| `application/ld+json` | 0/34 | **no** structured-data shortcut exists |
| `#glance_icons_div`, `#merchant-info`, `#aplus3p_feature_div` | 0/34 | selectors from other locales/eras |

**Everything above is server-rendered HTML.** No browser execution and no
follow-up request was needed for any of it.

### 1.3 Important layout variants found

**a) The image gallery is a JS literal, in two shapes.** Current amazon.de
serves

```js
'colorImages': { 'initial': A.$.parseJSON('[{"hiRes":"…","variant":"MAIN"}]') }
```

The baseline's regex expected the older bare-array form terminated by a
literal newline, which is why the baseline reported `images` populated on
**0/26** records while the data was on the page all along. Both shapes are now
handled, plus a `data-a-dynamic-image` fallback. Result: **34/34**.

**b) Key/value product data appears in three different containers**, and which
one a product uses is category- and layout-dependent:

1. two-column tables under `#poExpander` / `#topHighlight`
   (`table.a-normal.a-spacing-micro`) — the grocery "product overview";
2. `#detailBullets_feature_div` bullets, where the label and value are two
   sibling `<span>`s separated by RLM/LRM bidi marks (`Hersteller ‏ : ‎`);
3. `#prodDetails` tech-spec tables — dominant on non-grocery.

Rather than pick one, the extractor harvests all of them into a single raw
`label → value` map and records which container each label came from. Across
the sample this yields **15.7 distinct labels per PDP**, of which only a
minority map to canonical fields — the rest are preserved verbatim.

**c) Nutrition has four distinct sources, and the structured one is rare.**

| Source | Sample coverage | Confidence |
|---|---:|---|
| `#nic-eu-nutrition-facts-table` (structured card) | 4/34 | high |
| nutrition filed as ordinary attribute rows (`Eiweiß: 12 Gramm`) | 1/34 | medium |
| prose in `#productDescription` | 4/34 | medium/low |
| prose in A+ content or important-information | 4/34 | medium/low |

This is the single most important finding for the downstream analysis: a
parser that only reads the structured nutrition card would find protein on
~12% of pasta PDPs. The extractor therefore tries all four in that order and
tags the result with `source` and `confidence`.

The structured card's markup is also **malformed** — `<tr>` elements are
nested inside other `<tr>` elements — but lxml's recovery yields clean
two-cell rows, so a row-based parse works without special handling.

**d) Ingredients likewise have several homes**: `#nic-ingredients-content`
(21/34), an `#important-information` section headed `Zutaten`/`Bestandteile`,
a `Zutaten` attribute row, or an arbitrary attribute label whose *value*
begins with `Zutaten:` — one vendor files the ingredient declaration under
`Servierempfehlung`. The extractor treats the declaration prefix as the
signal, not the label.

**e) A+ content ships its own CSS and JS inside the module.** A naive
`::text` join returns ~38 kB of stylesheet per PDP. Text extraction must skip
`<script>`/`<style>` subtrees; doing so turns 38 kB of noise into ~2 kB of
product copy. A+ images are lazy-loaded, with the real URL in `data-src` and a
`grey-pixel.gif` placeholder in `src`.

**f) Accessibility labels are double-escaped.** `#apex-pricetopay-accessibility-label`
and the price-per-unit label decode to text that still contains `&nbsp;` and
`&euro;`, so one extra unescaping pass is required. These labels are also
repeated once per purchase option, so taking the first *element* (not a join
over all matches) is what keeps `"3,39 €"` from becoming
`"3,39 € 3,22 € mit 5 Prozent Einsparungen"`.

**g) Attribute labels do not always mean what they say.** One vendor files
`Stückzahl: 500.0 gramm` — a weight under a piece-count label. Reading it as a
count and multiplying by the 500 g item weight produced a 250 kg pack. The
extractor now decides by the *shape of the value*: a value carrying a mass or
volume unit is a quantity, never a piece count. This rule is
marketplace-independent.

### 1.4 Data that is *not* server-rendered

`nutritionalInfoAndIngredients_feature_div` also contains an **ACP card
placeholder** (`data-acp-path="/acp/cse-nutritional-info-and-ingredient-card/…"`)
on 31/34 PDPs. This is a client-side-loaded card. Crucially, on the pages
where nutrition and ingredient data exists, the *same* data is **also
server-rendered** next to the placeholder — the placeholder is an alternate
render slot, not the only copy. On pages with no server-rendered nutrition,
spot checks found no evidence that the ACP endpoint would return any, and the
`nic-po-expander-content` element is empty in the HTTP response.

**No high-value field was found that is available only after browser
execution.** Browser automation is therefore still not justified. See §4.

---

## 2. Implementation

### 2.1 Layering

```
amazon_scraper/extraction/
  text.py          locale-agnostic text + number primitives
  marketplaces.py  per-location labels, currency, number format
  blocks.py        generic harvesters for Amazon's page structures
  pdp.py           composes a record and records provenance
```

The split follows the axis along which Amazon actually varies. Page
*structure* (element ids, table shapes, the gallery blob) is shared across
locations; *labels* and *number formats* are not. Adding a marketplace is
therefore a data change in `marketplaces.py`, not a parser change.

- **`text.py`** — whitespace/bidi cleanup, script/style-safe text extraction,
  and a number parser that resolves `12,9g`, `3000.0 gramm` and `1.234,56 €`
  correctly on the same page by taking the right-most separator as the decimal
  point. Also `parse_quantity`, which understands `6 x 500 g` multipacks.
- **`marketplaces.py`** — canonical attribute keys and nutrient keys, each
  with per-language label lists; byline cleanup patterns; unit table. Unknown
  domains fall back to a neutral English profile and still crawl.
- **`blocks.py`** — `key_value_tables`, `key_value_bullets`, `bullet_list`,
  `labelled_sections`, `expander_sections`, `image_records`,
  `dynamic_image_urls`, `aplus_content`. Each returns `None` when the
  structure is absent.
- **`pdp.py`** — decides which structure answers which question, and wraps
  every block in a logger that separates *absent* from *failed*.

### 2.2 Failure isolation and provenance

Every block runs through `_BlockLog.run`. A block that raises is recorded in
`extraction.errors` and the rest of the record is still emitted; a block that
returns nothing is recorded in `extraction.blocks_absent`. A record therefore
carries its own audit trail:

```json
"extraction": {
  "blocks_present": ["raw_tables", "important_information", "…"],
  "blocks_absent": [],
  "errors": []
}
```

Provenance is also attached per data category: `attribute_sources` maps each
raw label to the container it came from, `food.nutrition.source` and
`.confidence` say whether numbers came from the structured card or from prose,
`food.ingredients.source` does the same, `media.image_source` distinguishes the
gallery blob from the fallback, and `package.total_quantity_source` names the
rule that produced the pack size. `nutrition.derived` lists values the
extractor computed rather than read (currently only kcal from kJ).

This is what lets the downstream layer distinguish the three cases the brief
asks for: explicitly present, normalized/derived, and genuinely absent.

### 2.3 Raw first, normalized second

`raw_tables` keeps every harvested `label → value` pair verbatim, including
labels with no canonical mapping:

```json
"raw_tables": {
  "Marke": "Naturata",
  "Artikelgewicht": "250 Gramm",
  "Allergenhinweis": "Enthält: Dinkel, Eier, …",
  "Anzahl der Einheiten": "250.0 gramm",
  "Global Trade Identification Number": "04024297021490"
}
```

`attributes` is the normalized view over the same data. Nothing is dropped
because it was not recognised, so pasta-specific signals (bronze die, drying
time, Gragnano IGP) can be mined later from `raw_tables`, `content.description`,
`content.aplus.text` and `content.feature_bullets` without re-crawling.

No pasta-specific logic exists in the parser. The closest the code comes to
domain knowledge is a generic *food* notion (nutrients, ingredients,
allergens), which applies to the whole grocery category.

### 2.4 Changes to the crawl flow

Deliberately small:

- `keyword` now accepts several `;`-separated queries, crawled one at a time
  with **exactly one search request outstanding**. This was driven by
  evidence: firing 7 `/s?` requests back-to-back during the investigation drew
  18 HTTP 503s and lost 6 of 7 searches, while the same queries chained behind
  PDP fetches drew zero.
- `max_products_per_query` caps PDP *discovery* per query rather than cutting
  the crawl mid-flight the way `CLOSESPIDER_ITEMCOUNT` does, and being
  per-query stops a broad first query from starving the rest.
- `search_position` and `canonical_url` added to lineage.
- Per-field coverage counters are emitted into Scrapy stats, so a crawl
  reports its own extraction quality.

Challenge detection, the stats taxonomy, marketplace-safe URL building,
pagination and the errback are unchanged.

### 2.5 Record schema

One JSON object per line. Every group degrades to `{}` / `[]` rather than
disappearing, so downstream consumers can index without guards.

| Group | Keys |
|---|---|
| envelope | `schema_version`, `fetched_at` |
| lineage | `marketplace`, `asin`, `product_url`, `canonical_url`, `search_query`, `search_page`, `search_position` |
| core | `title`, `brand`, `byline_text`, `brand_url`, `price{amount,currency,text}`, `unit_price{amount,unit,text}`, `rating{value,count,text,count_text}`, `availability`, `seller`, `breadcrumbs[]` |
| package | `item_weight_*`, `package_weight_*`, `unit_count_*`, `volume_*`, `item_count`, `size_name`, `dimensions`, `total_quantity_base`, `total_quantity_unit`, `total_quantity_source` |
| content | `feature_bullets[]`, `description`, `important_information[{heading,text}]`, `aplus{module_types,headings,text,text_length,images,tables}` |
| food | `ingredients{text,source}`, `allergens[]`, `nutrition{source,confidence,basis_text,per_100g,rows,derived}` |
| attributes | `attributes{}` (canonical), `raw_tables{}` (verbatim), `attribute_sources{}` |
| media | `images[{url,variant,alt,thumb}]`, `primary_image`, `image_count`, `image_source` |
| diagnostics | `extraction{blocks_present[],blocks_absent[],errors[]}` |

`nutrition.per_100g` uses canonical keys: `energy_kj`, `energy_kcal`,
`protein_g`, `fat_g`, `saturated_fat_g`, `carbohydrates_g`, `sugars_g`,
`fiber_g`, `salt_g`, `sodium_mg`. `*_base` quantities are grams or
millilitres, so multipacks are directly comparable.

### 2.6 Marketplace portability

`amazon.de` is the profile validated against live pages. `amazon.com`,
`amazon.co.uk` and `amazon.it` profiles exist so the seams are exercised, but
they are **not** validated against live pages of those locations.

What the design avoids:

- no `.de` URL is hardcoded — every URL is built from `self.base_url`, which
  comes from the `domain` argument;
- German labels live only in `marketplaces.py`, keyed by language;
- no single PDP layout is treated as universal — each data category has an
  ordered list of candidate structures;
- an unknown domain falls back to a neutral English profile and still
  produces full `raw_tables`, images, price and title, because those come from
  structure rather than labels.

What a new marketplace would actually need: a `Marketplace(...)` entry plus
label lists for any labels not already present. No parser change is expected
for another EU location; `.com` additionally uses imperial units, which the
unit table already covers (`oz`, `lb`).

#### Measured: what happens on amazon.com today

Four live `.com` PDPs (three grocery, one non-grocery) were run through the
`amazon.com` profile **with no code changes**:

| Category | Result on `.com` |
|---|---|
| title, brand, rating, breadcrumbs | works |
| `raw_tables` | works — 11–18 labels/PDP |
| label mapping | works — `Brand`, `Variety`, `Item Weight`, `Number of Items`, `Package Dimensions`, `Item model number`, `Manufacturer`, `UPC`, `ASIN` all mapped by the existing English list |
| imperial units | works — `"2 pounds"` → `1814.37 g`, `"71 pounds"` → `32205.03 g` |
| images (`colorImages` blob) | works — 3–7 images/PDP |
| ingredients | works — `"durum wheat semolina, water"` from the same `#nic-ingredients-content` element |
| feature bullets, A+ | works |
| **price** | **needed a fix** — see below |
| **nutrition** | **not supported** — see below |

*Price* was the one real defect the probe exposed, and it was a defect on
every marketplace, not just `.com`. `.com` does not render
`#corePrice_feature_div`, so the parser fell through to an unscoped
`.a-price .a-offscreen` and picked up a *related product's* price from a
carousel — reporting `97.0` for a product whose price it had not found. Worse,
`.com` renders that offscreen label without a decimal separator (`EUR097`).
Both are now fixed: price is read only from a known price container, and when
the offscreen label has no separator it is rebuilt from the
`a-price-whole`/`a-price-fraction`/`a-price-symbol` spans. On a `.com` page
with no buy box the result is now an honestly empty `price`, not a wrong
number. amazon.de price coverage is unchanged at 34/34.

*Nutrition* on `.com` is genuinely a different structure and was left
unimplemented, deliberately. The US card is `#nic-nutrition-facts` (not
`#nic-eu-nutrition-facts`), its rows are **reversed and merged** —
`['1%', 'Total Fat 1g']`, where the EU table gives `['— Fett', '1,2g']` — and
the basis is **per serving**, not per 100 g (`Serving size 2oz (56g)`,
`8.0 servings per container`). Supporting it means a second row parser plus a
serving-size conversion, which is more than a profile entry. It is scoped in
§5 rather than half-built.

### 2.7 Tests

`tests/test_extraction.py` — 19 offline unit tests over fixtures modelled on
the real structures, including the `parseJSON` gallery blob, the malformed
nutrition table, bidi-marked detail bullets, the mixed number formats, the
unit-carrying count label, and an empty page (which must yield a record, not
an exception).

```bash
.venv/bin/python -m unittest discover -s tests
```

---

## 3. Validation

### 3.1 Crawl

```bash
SCRAPY_PROJECT=baseline scrapy crawl amazon_product \
  -a keyword="spaghetti hartweizen; penne rigate bio vollkorn; pasta di gragnano igp" \
  -a domain="www.amazon.de" -a max_pages=2 -a max_products_per_query=65 \
  -s RETRY_TIMES=4 \
  -O data/validation_amazon_de.jsonl
```

| | |
|---|---|
| Date | 2026-09-14, 19:58:57–20:13:48 local (CEST), 890 s |
| Marketplace | `www.amazon.de`, no proxy, no browser |
| Queries | 3 |
| Search pages parsed | 5 (both pages reached on 2 of 3 queries) |
| Product URLs discovered | 352 |
| **Unique PDPs requested** | **195** |
| Distinct brands in output | 62 |

### 3.2 Crawl reliability

| Metric | Value |
|---|---|
| Total requests | 201 |
| HTTP 200 | **201 / 201** |
| Challenge / CAPTCHA responses | **0** |
| HTTP errors (4xx/5xx) | **0** |
| Retries | **0** |
| Download errors | **0** |
| PDP parser failures (200, not a challenge, no title) | **0** |
| Records emitted | **195 / 195** |
| Records with an extraction error | **0 / 195** |
| `finish_reason` | `finished` |

The plain-Scrapy baseline held over 7× the request volume of the original
smoke test with no degradation. Note the contrast with §1.1: firing search
requests in a burst produced 18 HTTP 503s, while this crawl — one search
request outstanding at a time — produced zero.

### 3.3 Extraction coverage (195 records)

| Field | Populated | |
|---|---:|---:|
| `title` | 195/195 | 100% |
| `brand` | 195/195 | 100% |
| `price.amount` | 195/195 | 100% |
| `breadcrumbs` | 195/195 | 100% |
| `raw_tables` | 195/195 | 100% |
| `media.images` | 195/195 | 100% |
| `important_information` | 193/195 | 99% |
| `unit_price.amount` | 190/195 | 97% |
| `availability` | 190/195 | 97% |
| `package.total_quantity` | 179/195 | 92% |
| `feature_bullets` | 170/195 | 87% |
| `rating.value` / `rating.count` | 163/195 | 84% |
| `content.description` | 136/195 | 70% |
| `attributes.country_of_origin` | 118/195 | 61% |
| `content.aplus` | 89/195 | 46% |

Food fields, over the 193 grocery records:

| Field | Populated | |
|---|---:|---:|
| `food.ingredients` | 128/193 | 66% |
| `food.nutrition` (any) | 85/193 | 44% |
| `food.nutrition.per_100g.protein_g` | 82/193 | 42% |
| `carbohydrates_g` | 76/193 | 39% |
| `fat_g` | 69/193 | 36% |
| `energy_kcal` | 59/193 | 31% |
| `food.allergens` | 71/193 | 37% |
| `fiber_g` | 25/193 | 13% |

Against the baseline, which emitted `name`, `price`, `stars`, `rating_count`,
`feature_bullets`, `images` (0/26) and `variant_data`: images went from
**0% to 100%**, and ingredients, nutrition, raw attribute tables, package
quantity, description, important information, A+ content, breadcrumbs,
unit price and availability are all new.

### 3.4 Where the data came from

This is the evidence for the multi-source design. Reading only the structured
nutrition card would have found nutrition on 45 records; trying all four
sources found it on 85 — **1.9× more**.

| `nutrition.source` | records | confidence |
|---|---:|---|
| `nutrition_card` | 45 | high |
| `text:description` | 22 | medium/low |
| `text:aplus` | 13 | medium/low |
| `attributes` | 3 | medium |
| `text:feature_bullets` | 2 | medium/low |
| *(absent)* | 110 | — |

| `total_quantity_source` | records |
|---|---:|
| `unit_count` | 162 |
| `item_weight_x_count` | 11 |
| `package_weight` | 4 |
| `item_weight` | 1 |
| `title_multipack` | 1 |
| *(absent)* | 16 |

`ingredients` came from `nutrition_card` on 127 records and
`important_information` on 1. `images` came from the `colorImages` blob on
all 195 — the `data-a-dynamic-image` fallback was never needed, but it costs
nothing to keep.

Other volume figures: **12.6** raw attribute labels per record, **82**
distinct labels across the crawl, **5.1** images per record, **4.1** feature
bullets per record.

### 3.5 Independent correctness check

Coverage says a field was populated, not that it was right. Package quantity
is independently checkable: Amazon publishes both a price and a price per kg,
so `price ÷ unit_price` implies a pack weight that the extractor never looks
at.

**163 of 164 checkable records agree within 12%.** The single outlier
(`B0G6D354JV`, *"Italian Gourmet Pasta Set 20×500g"*) is Amazon's error, not
the extractor's: the title says 20×500 g, `Artikelgewicht` is 500 g,
`Anzahl der Artikel` is 20 and `Paketgewicht` is 10 kg — all agreeing with the
extracted 10 000 g — while Amazon's own displayed unit price implies 1 kg.

### 3.6 Code state during the crawl

The crawl ran with the extraction code as shipped except for three later
refinements: two whitespace-normalisation fixes (joining inline `<span>`s
without a gap before punctuation or inside split compound words) and the
price-container scoping fix from §2.6. Re-extracting the 34-PDP offline
corpus before and after the price fix produced **zero differing field values**
on amazon.de (only `fetched_at` changed), so the price figures above hold for
the shipped code. The whitespace fixes change string formatting inside text
fields, not whether a field is populated.

### 3.7 Representative records
#### A. Pasta PDP with the structured nutrition card

```json
{
  "schema_version": 2,
  "fetched_at": "2026-09-14T18:01:48+00:00",
  "marketplace": "www.amazon.de",
  "asin": "B00XUMS46W",
  "product_url": "https://www.amazon.de/dp/B00XUMS46W",
  "canonical_url": "https://www.amazon.de/Garofalo-Gragnano-Hartweizengrie%C3%9F-Neapolitanische-Packung/dp/B00XUMS46W",
  "search_query": "pasta di gragnano igp",
  "search_page": 1,
  "search_position": 46,
  "title": "Garofalo Pasta di Gragnano IGP Ditali N° 52 Hartweizengrieß Pasta 100% Neapolitanische Pasta Kurze Pasta Packung mit 500g",
  "brand": "GAROFALO",
  "byline_text": "Marke: GAROFALO",
  "brand_url": "/GAROFALO/b/ref=bl_dp_s_web_16449560031?ie=UTF8&…",
  "price": {
    "amount": 2.47,
    "currency": "EUR",
    "text": "2,47 €"
  },
  "unit_price": {
    "amount": 4.94,
    "unit": "kg",
    "text": "4,94 € pro kg"
  },
  "rating": {
    "value": 4.7,
    "count": 321,
    "text": "4,7 von 5 Sternen",
    "count_text": "(321)"
  },
  "availability": "Auf Lager",
  "seller": "SchroniskoBukowina",
  "breadcrumbs": [
    "Lebensmittel & Getränke",
    "Nudeln, Reis & Hülsenfrüchte",
    "Nudeln & Pasta",
    "Pasta",
    "Kurze Pasta"
  ],
  "package": {
    "unit_count_text": "500.0 gramm",
    "unit_count_amount": 500.0,
    "unit_count_unit": "g",
    "unit_count_base": 500.0,
    "item_count": 1,
    "size_name": "500 Gramm",
    "dimensions": "7 x 10 x 15 cm; 500 Gramm",
    "total_quantity_base": 500.0,
    "total_quantity_unit": "g",
    "total_quantity_source": "unit_count"
  },
  "content": {
    "feature_bullets": [
      "Der italienische Premium-Nudelhersteller Garofalo stellt seit 1789 hochwertige Pasta in Gragnano bei Neapel he…",
      "Pasta Garofalo Ditali ist eine Pasta, die sich gut als Suppenpasta eignet und hervorragend für kleine Kinder i…"
    ],
    "description": "Produktbeschreibungen Der italienische Premium-Pastahersteller Garofalo stellt seit 1789 hochwertige Pasta in Gragnano bei Neapel …",
    "important_information": [
      {
        "heading": "Bestandteile",
        "text": "Weizen"
      },
      {
        "heading": "Gebrauchsanweisung",
        "text": "Kochzeit: 9 Minuten"
      }
    ],
    "aplus": {
      "module_types": [],
      "headings": [
        "Produktbeschreibung des Herstellers"
      ],
      "text": "Produktbeschreibung des Herstellers…",
      "text_length": 35,
      "images": [
        {
          "url": "https://m.media-amazon.com/images/S/aplus-media-library-service-media/88dc1cad-01ff-42cf-8af6-6def13c0884c.__CR0,0,1941,1201_PT0_SX970_V1___.png",
          "alt": "aplus content image"
        }
      ],
      "tables": "… 0 comparison tables"
    }
  },
  "food": {
    "ingredients": {
      "text": "Weizen…",
      "source": "nutrition_card"
    },
    "allergens": [
      "Kann enthalten: Weizen",
      "Enthält: Kann Weizen enthalten"
    ],
    "nutrition": {
      "source": "nutrition_card",
      "confidence": "high",
      "basis_text": "Pro 100g",
      "per_100g": {
        "energy_kj": 1489.0,
        "fat_g": 1.0,
        "saturated_fat_g": 0.2,
        "carbohydrates_g": 70.0,
        "sugars_g": 3.0,
        "fiber_g": 3.0,
        "protein_g": 14.0,
        "salt_g": 0.01,
        "energy_kcal": 355.9
      },
      "rows": [
        {
          "label": "Energie",
          "value_text": "1489kJ",
          "amount": 1489.0,
          "unit": "kj",
          "key": "energy_kj"
        },
        {
          "label": "— Fett",
          "value_text": "1g",
          "amount": 1.0,
          "unit": "g",
          "key": "fat_g"
        },
        {
          "label": "— Gesättigte Fettsäuren",
          "value_text": "0,2g",
          "amount": 0.2,
          "unit": "g",
          "key": "saturated_fat_g"
        },
        "… +13 more rows"
      ],
      "derived": [
        "energy_kcal"
      ]
    }
  },
  "attributes": {
    "brand": "GAROFALO",
    "variety": "Ditali",
    "item_count": "1",
    "form": "Ditali",
    "flavour": "Weizenpaste",
    "allergen_info": "Enthält: Kann Weizen enthalten",
    "unit_count": "500.0 gramm",
    "package_size": "500 Gramm",
    "manufacturer": "Pastificio Lucio Garofalo S.p.A.",
    "dimensions": "7 x 10 x 15 cm; 500 Gramm",
    "asin": "B00XUMS46W",
    "model_number": "231"
  },
  "raw_tables": {
    "Marke": "GAROFALO",
    "Auswahl": "Ditali",
    "Anzahl der Artikel": "1",
    "Paketinformationen": "Paket",
    "Form": "Ditali",
    "Geschmacksrichtung": "Weizenpaste",
    "Allergenhinweis": "Enthält: Kann Weizen enthalten",
    "Anzahl der Einheiten": "500.0 gramm"
  },
  "attribute_sources": {
    "Marke": "table",
    "Auswahl": "table",
    "Anzahl der Artikel": "table"
  },
  "media": {
    "images": [
      {
        "url": "https://m.media-amazon.com/images/I/61vMwCZ2VlL._SL1000_.jpg",
        "variant": "MAIN",
        "alt": "",
        "thumb": "https://m.media-amazon.com/images/I/41Tpssg51YL._SX38_SY50_CR,0,0,38,50_.jpg"
      },
      {
        "url": "https://m.media-amazon.com/images/I/61b-pVQOcKL._SL1000_.jpg",
        "variant": "FACT",
        "alt": "",
        "thumb": "https://m.media-amazon.com/images/I/416yRiRZVpL._SX38_SY50_CR,0,0,38,50_.jpg"
      }
    ],
    "primary_image": "https://m.media-amazon.com/images/I/61vMwCZ2VlL._SL1000_.jpg",
    "image_count": 4,
    "image_source": "color_images"
  },
  "extraction": {
    "blocks_present": [
      "raw_tables",
      "important_information",
      "feature_bullets",
      "description",
      "aplus",
      "ingredients",
      "nutrition",
      "media",
      "package",
      "brand",
      "price",
      "unit_price",
      "rating",
      "breadcrumbs",
      "allergens"
    ],
    "blocks_absent": [],
    "errors": []
  }
}
```

#### B. Nutrition recovered from prose — same schema, lower confidence

```json
{
  "asin": "B0GVF1NFRH",
  "title": "Italian Gourmet Pastificio Liguori Mezze Maniche Rigate – Italieni",
  "nutrition": {
    "source": "text:description",
    "confidence": "medium",
    "basis_text": "100 g",
    "per_100g": {
      "protein_g": 69.0
    },
    "derived": []
  },
  "package": {
    "item_weight_text": "500 Gramm",
    "item_weight_amount": 500.0,
    "item_weight_unit": "g",
    "item_weight_base": 500.0,
    "package_weight_text": "500 Gramm",
    "package_weight_amount": 500.0,
    "package_weight_unit": "g",
    "package_weight_base": 500.0,
    "unit_count_text": "2000.0 gramm",
    "unit_count_amount": 2000.0,
    "unit_count_unit": "g",
    "unit_count_base": 2000.0,
    "item_count": 4,
    "size_name": "",
    "dimensions": "30 x 30 x 15 cm; 500 Gramm",
    "total_quantity_base": 2000.0,
    "total_quantity_unit": "g",
    "total_quantity_source": "unit_count"
  }
}
```

#### C. Sparse PDP — optional sections absent, record still complete

```json
{
  "asin": "3969301173",
  "title": "Nudeln selber machen wie die Profis: Über 30 Nudelsorten ganz leic",
  "price": {
    "amount": 18.9,
    "currency": "EUR",
    "text": "18,90 €"
  },
  "raw_tables_label_count": 10,
  "media": {
    "primary_image": "https://m.media-amazon.com/images/I/81+mvAjPWTL._SL1500_.jpg",
    "image_count": 4,
    "image_source": "color_images"
  },
  "food": {
    "ingredients": {},
    "allergens": [],
    "nutrition": {}
  },
  "extraction": {
    "blocks_present": [
      "raw_tables",
      "aplus",
      "media",
      "package",
      "brand",
      "price",
      "rating",
      "breadcrumbs"
    ],
    "blocks_absent": [
      "important_information",
      "feature_bullets",
      "description",
      "ingredients",
      "nutrition",
      "unit_price",
      "allergens"
    ],
    "errors": []
  }
}
```

---

## 4. Limitations

**Nutrition coverage is bounded by Amazon, not by the parser.** 44% is close
to the ceiling for this category. Of the 110 records with no nutrition, spot
checks found the data genuinely absent from the HTML — no structured card, no
attribute rows, and no numbers in the description, bullets or A+ text. The
remaining recoverable cases are nutrition rendered *inside A+ images*, which
is an OCR problem, not a parsing one.

**Free-text nutrition is heuristic.** 37 of 85 nutrition records came from
prose. The parser anchors on a nutrient label followed by a number and unit,
and marks `confidence: "medium"` only when a per-100 g basis appears within
±140 characters; otherwise `"low"`. A vendor writing "Protein 20 g per
serving" without stating the serving size will produce a plausible but wrong
per-100 g figure. `source` and `confidence` exist so the downstream layer can
discount these, and `rows[].value_text` preserves the matched substring for
audit.

**Vendor data is sometimes simply wrong**, and the extractor faithfully
reproduces it. One PDP publishes 87.7 kcal/100 g for dry pasta (real value
~350). Extraction is correct; the source is not. Sanity checks belong in the
normalisation layer, which is why raw rows are retained.

**`fiber_g` is only 13%.** Fibre is optional on EU nutrition labels and most
vendors omit it.

**Brand normalisation is imperfect.** `#bylineInfo` is a store link as often
as a brand name; the attribute table's `Marke` is preferred when present, but
casing is whatever the vendor typed (`GAROFALO` vs `Garofalo`), so brand
matching downstream needs case-folding.

**Rating at 84%** reflects products with no reviews yet, not a selector
problem — `#acrPopover` is simply not rendered without reviews.

**A+ content is captured as text, images and tables, not as layout.** Module
ordering and image/text association are lost. `module_types` retains the
module class names as a coarse hint.

**The ACP nutrition card endpoint is not fetched.** See §1.4: where data
exists it is also server-rendered, so this is an accepted gap rather than a
known loss.

**`amazon_scraper/spiders/amazon_search.py` is untouched** and still carries
hardcoded `.com` URLs and the off-by-one pagination bug documented in
BASELINE.md. It is not used by this pipeline.

---

## 5. Recommended next steps

### 5.1 Remaining high-value extraction gaps

1. **Nutrition from A+ images (OCR).** The largest remaining source of
   missing nutrition. Scoped, optional, and independent of the crawler: A+
   image URLs are already in every record, so this can run offline over
   existing JSONL without re-crawling.
2. **Serving-size normalisation.** Some vendors publish per-serving values
   with a `Portionsgröße` attribute. Converting those to per-100 g would add
   a few percent and is cheap, but needs a sanity check against implausible
   results.
3. **Variation / twister data.** `dimensionValuesDisplayData` is present on
   ~70% of PDPs and was dropped in this iteration. It would let the
   downstream layer group pack sizes of the same product.
4. **Review content.** Not extracted at all. Review text is a strong quality
   signal for food and would need a separate `/product-reviews/` request
   flow, which changes the crawl shape — a separate task.

### 5.2 Marketplace-specific issues

`amazon.de` is validated. For `amazon.com`, §2.6 measured what already works
(title, brand, rating, breadcrumbs, raw tables with English labels, imperial
units, images, ingredients, bullets, A+ — all with no code change) and what
does not:

1. **US nutrition table** — `#nic-nutrition-facts`, with reversed and merged
   cells (`['1%', 'Total Fat 1g']`) and a per-serving basis. Needs a second
   row parser plus a serving-size conversion. Roughly a day's work, including
   a `.com` sample crawl to validate against.
2. **`.com` price containers and unit price** should be re-checked from a US
   IP. The probe ran from a European IP, which changes both the currency shown
   and the buy-box markup, so `.com` price coverage here is not a fair
   measurement.

Neither is blocking, and neither requires changing the architecture.

### 5.3 Is browser automation justified?

**No.** 201/201 requests returned HTTP 200 with zero challenges, zero retries
and zero errors, on an ordinary residential connection with no proxy. Every
data category that Amazon publishes was found in the server-rendered HTML,
including the image gallery, ingredients and nutrition. The one
client-loaded structure found (the ACP nutrition card, §1.4) duplicates
server-rendered data rather than holding anything exclusive.

The one thing worth carrying forward is the **503 evidence**: `/s?` requests
in a burst get throttled, PDP requests do not. That is a pacing constraint,
not a blocking problem, and the spider now paces searches accordingly. Keep
watching `amazon/challenge/*` and `amazon/http_error/*` as volume grows;
those counters exist for exactly this.

### 5.4 Does the architecture extend beyond pasta?

Yes, and this was tested rather than assumed. The sample deliberately
included a non-pasta grocery product and a non-grocery product (Bluetooth
headphones). On the latter the extractor returned 43 raw attribute labels,
8 images, A+ module types, price, rating and breadcrumbs, with the food
section cleanly empty and `blocks_absent` listing exactly the sections Amazon
did not publish — no errors, no false positives.

The parser contains no pasta-specific logic. The only domain assumption is a
generic *food* notion (nutrients, ingredients, allergens) which applies to the
whole grocery category, and it degrades to empty rather than failing for
non-food. Pasta-quality signals (bronze die, drying temperature, Gragnano
IGP, Italian wheat) are deliberately **not** hard-coded: they remain
recoverable from `raw_tables`, `content.description`, `content.aplus.text`
and `content.feature_bullets`, which is where they actually appear.

Extending to a new category needs no parser change. Extending to a new
marketplace needs a profile entry plus label lists.
