# Extraction corpus

35 real Amazon product detail pages, saved to disk, with a snapshot of the
record each one is expected to produce. `../test_corpus.py` re-extracts every
page on each run and fails if any field changes.

```
amazon_de/    34 pages + expected.jsonl.gz   the validated marketplace
amazon_com/    1 page  + expected.jsonl.gz   probed only, not supported
redact.py                                    run before adding a page
```

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
