# Purchase advice reports

Finished buying recommendations produced with this platform: one file per
research question, answering "which of these should I actually buy, and what
is the evidence".

**The reports themselves are not committed.** They are gitignored, the same
way `data/` is, and for the same reason — they are output rather than source.
A report is a snapshot of one marketplace on one day: prices, availability and
review counts in it go stale within days, and a stale recommendation that
looks authoritative is worse than none. Keeping them out of git also keeps a
repository about *how to compare products* from filling up with conclusions
about particular ones.

What is committed instead is everything needed to regenerate one: the category
module under `amazon_scraper/analysis/categories/`, its tests, and the
crawl evidence behind any roadmap decision under `data/evidence/`.

## Convention

| | |
|---|---|
| One file per question | `BASMATI.md`, `OLIVE-OIL.md`, … |
| Name it after the product | not after the date; the file says its own crawl date |
| State the crawl date at the top | prices are a snapshot and must be labelled as one |
| Cite per claim | every figure traceable to a record, a quote or an external source |
| Say "unknown" | absence of data is not an adverse finding, and must not be dressed as one |

## Reports so far

| Report | Question | Category module |
|---|---|---|
| `BASMATI.md` | best dry basmati on Amazon.de for regular home use | `analysis/categories/basmati_rice.py` |

What that exercise revealed about the platform itself — as opposed to about
rice — is in [USABILITY.md](../USABILITY.md), which *is* committed, because it
is about this repository rather than about a shelf.
