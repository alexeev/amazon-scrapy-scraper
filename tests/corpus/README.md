# Extraction corpus

39 real Amazon product detail pages, saved to disk, with two snapshots each:
the record the page is expected to extract to, and the **validated record**
that record is expected to produce under the published contract.
`../test_corpus.py` re-runs both on every test run and fails if any field
changes.

```
amazon_de/    38 pages + expected.jsonl.gz + validated.jsonl.gz
amazon_com/    1 page  + expected.jsonl.gz + validated.jsonl.gz
redact.py                                    run before adding a page
```

`expected.jsonl.gz` is what the page says. `validated.jsonl.gz` is how much of
that holds up — every value with its `source`, its `status` and the evidence
behind it — produced with **no category profile**, so what is pinned is the
layer that belongs to nobody. It exists because the contract is something
downstream code depends on, and a silent change in a status is as breaking as
a silent change in a value, and much easier to make by accident: the rules
interact.

## Why the pages are here

The unit tests in `../test_extraction.py` use hand-written fixtures. They pin
down the structures we already understand — that is their job, and it is why
they cannot catch the other kind of bug. These pages are 2 MB each and full of
structures nobody enumerated: nested attribute tables reachable through four
different selectors, A+ blocks, `parseJSON` image blobs, three layouts of the
same nutrition card.

The Python 3.9 → 3.14 upgrade silently dropped a whole attribute table from
two of these pages. Every unit test passed. Only a field-by-field comparison
against saved pages found it, and at the time that comparison was an ad-hoc
script run by hand, which is the weakest possible place for the strongest
regression evidence to live.

The `amazon_de` snapshot is byte-identical to the output of the pre-upgrade
Python 3.9.6 / Scrapy 2.13.4 runtime, so it is a record of validated
behaviour, not just of current behaviour.

## Pages were chosen for layout diversity

Not for being pasta. They cover pages with and without a buy box, with and
without A+ content, with the nutrition card in each of its observed shapes,
with single items and multipacks, and with the attribute data in the overview
table, the tech-spec tables or the detail bullets.

Four are **not groceries at all** (R2): `B01M25SBQ5` a 5 kg tub of tyre
mounting paste, `B000RW5FVA` the same product class sold as a 50 ml fluid —
the first size dimension in the corpus that is a volume — `B071JNV24H` a paste
with no price and a mineral-oil base declared in its bullets, and `B07J2W1S6Q`
a tube of bicycle grease whose German label, *Fett*, the food parser reads as
a nutrition declaration. They were added because a corpus made entirely of one
category cannot catch a layer that has quietly learned that category.

One caution the repository has already paid for: these pages are picked for
diversity, which makes them a **bad basis for a frequency claim**. The
variation matrix is on 26 of 38 here and on about a third of records from an
ordinary search crawl, and R3 was partly justified on the wrong one of those
two numbers.

## Privacy

The pages are fetched without signing in: `isCustomerLoggedIn` is `false` and
`customerId` is empty on all of them, so there is no account data in them.
What Amazon does embed is a per-session id, a per-request id, per-widget
correlation ids and its own render-service IP. `redact.py` replaces all of
those with fixed placeholders before a page is committed.

## Adding a page

```bash
python tests/corpus/redact.py raw.html tests/corpus/amazon_de/B0XXXXXXXX.html.gz
python tests/test_corpus.py --update
```

Then read the snapshot diff before committing it. Two rules:

* **Redaction must never change an extracted value.** The corpus test is what
  proves it. Redacting by shape rather than by anchoring to the key that
  carries the identifier has already broken this twice — every UUID also
  matches an A+ image URL, and every 20-character uppercase token also matches
  a German A+ heading.
* **A snapshot diff is a code review, not a refresh.** `--update` will happily
  record a regression as the new expectation.
