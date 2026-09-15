# Product research runbook

This is the current workflow for the shipped tools. Read [AGENTS.md](AGENTS.md)
first. T0 makes the existing workflow discoverable; structured study artifacts
and automated report validation in the [transition plan](AGENT_TRANSITION_PLAN.md)
are not implemented yet.

## Offline walkthrough

After [setup and shell configuration](README.md#setup-and-first-check), run the
following commands from the repository root. Each is a single line that works
in PowerShell or a POSIX shell. `--offline` prevents uv downloads; these analysis
commands themselves only read local feeds and perform no network requests.

**Example question:** Among the dry pastas in the committed case set, which
have a usable price per kilogram, and what makes a comparison defensible?
This demonstrates evidence handling, not current buying advice or exhaustive
market discovery. The feed deliberately includes known defects and controls.

### 1. Inspect quality and exclusions

```text
uv run --offline --locked python -m amazon_scraper.analysis summary tests/cases/pasta_v1.jsonl.gz --category dry_pasta
```

Expect 25 records, 22 classified as dry pasta, three other products, and no
undecided classification. The summary explicitly says accuracy is not measured:
a wrong rejection could still be a confident decision. Inspect the status
counts rather than treating a populated numeric field as usable.

### 2. Rank on the declared axis

```text
uv run --offline --locked python -m amazon_scraper.analysis rank tests/cases/pasta_v1.jsonl.gz --category dry_pasta --limit 3
```

Expect price-per-kg ranking, 14 offers with a trusted ranking value, and eight
excluded records. The first result is `B0CT3Q17FP` at the historical fixture
price of 1.58 EUR/kg. This establishes cheapest within these rankable fixture
records; it does not establish best pasta for a user or a currently purchasable
offer. Read the exclusion reasons below the ranking.

### 3. Inspect a card and its evidence

```text
uv run --offline --locked python -m amazon_scraper.analysis card tests/cases/pasta_v1.jsonl.gz B08WJGD5Z5 --category dry_pasta
```

Locate the quantity, price-per-kg value, statuses, and source quotations.
For this category the same card can be inspected as JSON:

```text
uv run --offline --locked python -m amazon_scraper.analysis card tests/cases/pasta_v1.jsonl.gz B08WJGD5Z5 --category dry_pasta --json
```

The provenance summary goes to stderr and JSON goes to stdout. A single
`card --json` is a pretty-printed object; use `cards --json` for JSONL across
category matches. Do not generalize this example's JSON completeness to basmati.

### 4. Compare two usable products

```text
uv run --offline --locked python -m amazon_scraper.analysis compare tests/cases/pasta_v1.jsonl.gz B08WJGD5Z5 B0DQ2N5HRW --category dry_pasta
```

Expect a `Differences` section including the cheaper-per-kilogram comparison.
Read the individual axes and caveats before turning that into purchase advice.

### 5. Exercise a refusal

```text
uv run --offline --locked python -m amazon_scraper.analysis compare tests/cases/pasta_v1.jsonl.gz B08JLSVW3J B08WJGD5Z5 --category dry_pasta
```

Expect `Price per kg` under `Cannot be compared`: the first product's pack
quantity is disputed. The card can show an alternative calculation without
promoting it to a trusted ranking value. Do not remove the contradiction to
force a comparison.

### 6. Inspect the underlying validation

```text
uv run --offline --locked python -m amazon_scraper.analysis validated tests/cases/pasta_v1.jsonl.gz --category dry_pasta
```

Expect 25 JSONL records with `contract_version: 1` and
`category_profile: "dry_pasta"`. This command applies the selected category's
plausibility bands; it does not run its classifier/claim evaluator. For neutral
validation, use the Python API `validate(record)` without a profile. There is
no neutral CLI option.

### 7. Locate the evidence and explain the result

- The input is [tests/cases/pasta_v1.jsonl.gz](tests/cases/pasta_v1.jsonl.gz);
  [its README](tests/cases/README.md) explains why the named products were chosen.
- Cards identify record fields and quote the supporting text. Raw fields remain
  in the source JSONL; validated outputs do not retain every raw field.
- The separate [saved-page corpus](tests/corpus/README.md) tests extraction and
  neutral validation. Not every case-feed product has a saved HTML fixture.
- [data/evidence/README.md](data/evidence/README.md) describes larger committed
  historical crawls; these are not a complete archive of every study.

A defensible example conclusion distinguishes the lowest usable historical
price from a suitability recommendation, explains the disputed pack exclusion,
and labels the dataset as selected regression cases. No fresh crawl is needed
to answer this offline question.

## Live research workflow

### Record the brief and working notes

Create a dated working note under `reports/` before collection. There is no
enforced brief schema yet; include:

- Question/use case, category, marketplace and delivery region.
- Hard requirements versus preferences, budget/cost basis, and unacceptable
  alternatives. Record what evidence would establish each decisive requirement.
- Freshness needed for price, availability, and other time-sensitive claims.
- Known ASINs, planned generic/brand queries, external sources, and why chosen.
- Query/page/product/time limits, assumptions, and material unresolved questions.

Ask for missing information when it materially changes the recommendation.
Keep existing user authorization; do not ask again merely because this runbook
exists. An unsupported category requires scoped category development and tests
before its judgments become a supported method.

### Live collection

Inspect existing feeds/pages first. Fresh prices require a new observation;
new parser fields can often be obtained by re-extraction. Keep the baseline
profile and encoding variables from README. Choose a new output path for every
run; the example path below must not already contain evidence you need.

PowerShell (networked crawl):

```powershell
$env:SCRAPY_PROJECT = 'baseline'
uv run --offline --locked scrapy crawl amazon_product -a keyword="spaghetti hartweizen" -a domain="www.amazon.de" -a max_pages=1 -a max_products_per_query=5 -s CLOSESPIDER_TIMEOUT=180 -O data/research-example-01.jsonl
```

POSIX shell (same networked crawl):

```sh
SCRAPY_PROJECT=baseline uv run --offline --locked scrapy crawl amazon_product -a keyword="spaghetti hartweizen" -a domain="www.amazon.de" -a max_pages=1 -a max_products_per_query=5 -s CLOSESPIDER_TIMEOUT=180 -O data/research-example-01.jsonl
```

Here **`--offline` applies to uv, not the crawler**: Scrapy makes marketplace
requests. `CLOSESPIDER_TIMEOUT` bounds crawl duration, but in-flight requests
can take time to finish; timeout closure means partial results. The product cap
bounds discovery, not retries or the exact number of HTTP requests. The baseline
uses concurrency 1, configured delay 9 seconds with jitter/AutoThrottle, and two
retries. Keep page retention enabled and run crawls sequentially.

For a named product, replace the `keyword` argument with `-a asin="B086BX8M3C"`
and choose another output path. Several queries or ASINs use semicolon-separated
strings. An ASIN-only run does not perform the default pasta search. Named
products matter: search can miss a relevant product even across brand queries.

Record the logged run ID and the feed path together. Inspect
`data/runs/<run_id>/manifest.json` for `finish_reason`, counts,
`amazon/challenge/*`, HTTP/download/parse errors, and `page_write_errors`.
Inspect `discovery.jsonl` to distinguish never-sighted products from repeated
sightings. Direct ASIN seeds do not appear as search sightings; their feed
`search_query` is `asin:<ASIN>` and the arguments are in the manifest.

A `finished` crawl or HTTP 200 response does not prove adequate research
coverage. If challenges or failures leave decisive gaps, record them, stop
repeated collection, and use a bounded later attempt or a qualified answer.
Do not fix a source absence by changing trust rules.

### Re-extract and analyze

For a retained run, replace these paths with the actual run directory, original
feed, and a new destination. The command works in either shell:

```text
uv run --offline --locked python -m amazon_scraper.run reextract data/runs/ACTUAL_RUN_ID --feed data/research-example-01.jsonl -o data/research-example-01-reextracted.jsonl
```

Supply the original feed so fetch time and discovery lineage survive. Without
it, fetch time falls back to filesystem mtime, which copying files can change;
do not treat that as proof of freshness. Keep original feeds unchanged.

Use the walkthrough's analysis commands with your feed and explicit category.
Multiple feeds go in the positional list. Verify they are from one marketplace
before merging; the current merger deduplicates by ASIN alone. A newer record
without a price must not be silently replaced with an old priced record in the
recommendation.

Read cards for known candidates, excluded candidates, and the shortlist.
`summary` counts classifier decisions, not accuracy. Compare units, variants,
pack sizes and cost assumptions before preferring a ranking row. The existing
`rank` command does not enforce a complete user brief; in particular its
quantity ranking can mix g and ml, and it permits axes without a declared
better direction. Do not use those orderings as recommendations. `compare`
does refuse incompatible units and can expose the limitation.

### Check external evidence and write the report

Read manufacturer specifications, independent tests, or other relevant sources
when the question needs facts absent from Amazon. Record URL, title/publisher,
publication and access dates, the exact supporting location, product/variant
identity, and limits. Preserve a permitted source/excerpt locally where useful.
Distinguish a vendor declaration from a measured property and a historical test
from evidence about the current batch. Unavailable sources remain unverified.

Basmati's embedded external-test constants lack complete source provenance and
applicability controls. Its text cards show its seven-part score, but `rank`
still sorts price per kilogram and JSON omits material basmati extras. Do not
claim that the CLI reproduces a composite shortlist or that an embedded
`trusted` external match establishes current product safety.

Follow [reports/README.md](reports/README.md) for output conventions. Include the
question, as-of dates, recommendation/alternatives, suitability and tradeoffs,
comparison values, exclusions, sources per material claim, and unresolved gaps.
Record exact feed paths, run IDs, commands/options and relevant code revision in
the working note. Assess freshness and delivered cost explicitly; absent
shipping data is unknown, not zero.

Before delivery, check that decisive numeric values are usable, units/currency
agree, citations support the selected variant and claim, sample reviews are
not used for rates, and conclusions say “among sources/products inspected”
where coverage is limited. Record the checks and remaining uncertainty.
There is no automated report validator today. An honest insufficient-evidence
answer is a valid result.

### Close and capture improvements

Keep working notes and reports at explicit locations and tell the user where
they are. `reports/` and most of `data/` are gitignored; this is not a backup or
portable study archive. Do not claim that another checkout can reproduce a
report unless its inputs are available there.

Record discoveries with source/run/ASIN, observed versus expected behavior,
reproduction command, affected layer and proposed next action. Follow
[the maintenance workflow](AGENTS.md#maintenance-workflow) for a code change.
Promote verified behavior to code/tests and useful procedure to the runbook;
leave speculative improvements as dated proposals. Keep the study's original
evidence and explain any changed analysis after a fix.

## Current limitations

| Limitation | What to do now | Planned stage |
|---|---|---|
| Identical crawls started in the same second can share a directory | Run sequentially and record IDs/unique output paths; inspect any collision | T1 |
| Feed and variation identity lack marketplace scope | Analyze a single validated marketplace at a time | T1 |
| Missing hashes/code/settings and mtime fallback weaken replay | Record commands, revision, original feed and run paths; identify unknown freshness | T1 |
| Search/challenge/titleless response bodies are not retained; retention/redaction can fail | Inspect counters and retained files; do not claim full failure replay or export unverified captures | T1 |
| Some axes can be ranked despite incompatible units/no preferred direction | Use suitable comparable axes and inspect pairwise comparisons | T1/T2 |
| No structured study brief, complete category JSON, or report checks | Keep explicit working notes and perform documented manual verification | T2/T3 |
| Original full studies/reports and basmati source documents are not all tracked | Use the committed walkthrough for onboarding; request/rebuild missing evidence only when the task needs it | T2/T3 |
| No two-provider acceptance trial yet | Load the same canonical instructions; do not claim proven provider handoff | T4 |

## Failure diagnosis

| Symptom | First evidence to inspect |
|---|---|
| Setup/profile/locale failure | README troubleshooting, `scrapy.cfg`, current shell variables, `settings_baseline.py` |
| Challenge, failed download or missing candidates | Run manifest stats, logged errors, discovery occurrences, planned queries/ASINs |
| Missing or wrong extracted field | `extraction.errors`, raw content/tables, retained page; reproduce with `reextract` |
| Disputed number | Evidence card and source fields, quantity/price units, category profile |
| Expected product classified out | Title, ingredients/body, the category classifier and existing cases |
| Test snapshot mismatch | Field-level diff and saved page; explain the change before updating any expected output |

Do not recrawl just to reproduce a parser error whose page is already retained.
If the required evidence was never retained, record that limitation explicitly.
