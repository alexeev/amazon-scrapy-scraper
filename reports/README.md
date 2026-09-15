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

What is committed is the category code, tests, selected category cases, and
crawl evidence behind some roadmap decisions under `data/evidence/`. This is
**not everything needed to regenerate each original report**: the complete
briefs, feeds, external sources and reports are not all tracked. Do not infer
reproducibility from a report name in the table below. The self-contained
[offline walkthrough](../RESEARCH.md#offline-walkthrough) uses committed cases.

Use [RESEARCH.md](../RESEARCH.md) for the current research and verification
workflow. Until portable study bundles are implemented (T2/T3), keep a working
note alongside a report with the question/constraints, assumptions, feed paths,
run IDs, commands/options, code revision, source URLs and dates, verification
results and unresolved limits. Ignored local output is not automatically backed
up. Keep dated notes/revisions when refreshing a report so its old evidence is
not silently overwritten.

## Convention

| | |
|---|---|
| One file per question | `BASMATI.md`, `OLIVE-OIL.md`, … |
| Name it after the product | not after the date; the file says its own crawl date |
| State the crawl date at the top | prices are a snapshot and must be labelled as one |
| Cite per claim | every figure traceable to a record, a quote or an external source |
| Say "unknown" | absence of data is not an adverse finding, and must not be dressed as one |

## Historical reports (not included in this checkout)

| Report | Question | Category module |
|---|---|---|
| `BASMATI.md` | best dry basmati on Amazon.de for regular home use | `analysis/categories/basmati_rice.py` |
| `FUSILLI.md` | best fusilli on Amazon.de for regular home use | `analysis/categories/dry_pasta.py` |
| `MOUNTING-PASTE.md` | tyre mounting paste for a 10-inch tubed scooter tyre on an aluminium rim, which must dry out after mounting | `analysis/categories/mounting_paste.py` |

The mounting-paste study is the one that best shows why the category module is
the committed artefact and the report is not. Three rounds of defects surfaced
while answering one question, and each was found the same way — by someone
reading the output against the world rather than by a test:

1. Four claim patterns were too narrow, because each had been written from the
   listings it already matched and none could show the listings it missed.
2. The extractor published the low end of a price range as a price (schema v6).
3. The pack-size rule would only take corroboration from a title or size
   field, so the smallest pack on the shelf — the one the ranking existed to
   surface — was never ranked at all.

All three corrections live in the modules and in `tests/cases/`, where the next
study inherits them. The prices they were found around were stale within the
week, which is the whole argument for what gets committed and what does not.

4. Search does not enumerate a shelf. Thirteen queries across five crawls —
   three naming the brand — never surfaced a 50 ml tin from a major
   manufacturer, because its title is "Rema Tip Top 501004 - Schwammdose,
   Transparent, 50 ml" and contains no word anyone would search for. The same
   silence made the title-based classifier reject it when it finally arrived.
   The spider now takes `-a asin=` for products someone can name, and the
   classifier falls back to the description when a title names nothing.

The one that has no fix here is the habit, not the code: this study wrote "no
listing says this" twice where "no listing I saw says this" was what the
evidence supported. Both times a manufacturer's own catalogue disproved it.

What that exercise revealed about the platform itself — as opposed to about
rice — is in [USABILITY.md](../USABILITY.md), which *is* committed, because it
is about this repository rather than about a shelf.
