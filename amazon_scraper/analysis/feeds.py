"""Several crawls, one record per ASIN.

A research question outlives a single crawl. Fusilli took three: a broad one,
a brand-name one run an hour later, and an earlier pasta crawl from the night
before that already held a third of the shelf. 471 unique products came out of
582 records, which means **111 ASINs were crawled more than once** and
something has to decide which sighting the study uses.

The rule is the freshest one wins, by ``fetched_at``, and not the order the
feeds were named on the command line. Order looks like a decision and is not
one: a shell glob sorts alphabetically, so ``data/fusilli_*.jsonl`` would have
silently preferred ``fusilli_brands`` over the hour-younger ``fusilli_broad``
for every ASIN they share. Price and availability are the two fields this
project treats as a snapshot, and they are exactly the two an arbitrary
argument order would get wrong.

A record with no ``fetched_at`` loses to any record that has one: it cannot
claim to be newer than something that says when it was fetched.
"""

import datetime as _dt

from ..run import read_jsonl

# Older than any real crawl, so an undated record never wins a tie-break.
BEGINNING = _dt.datetime.min.replace(tzinfo=_dt.timezone.utc)


def fetched_at(record):
    """When this record was crawled, or the beginning of time if it won't say."""
    stamp = record.get('fetched_at')
    if not stamp:
        return BEGINNING
    try:
        parsed = _dt.datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return BEGINNING
    # Naive and aware timestamps do not compare, and a feed that lost its
    # offset is still a feed. Read it as UTC, which is what the crawl writes.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.timezone.utc)


def merge(paths):
    """``(records, provenance)`` — the freshest record of each ASIN.

    ``provenance`` counts what the merge did: how many records survived, how
    many feeds they came from, and how many ASINs were crawled more than once
    and resolved to their freshest copy. That last number is the one worth
    printing, because it is the size of the overlap between the crawls.
    """
    chosen, order, superseded = {}, [], set()
    for path in paths:
        for position, record in enumerate(read_jsonl(path)):
            # A record with no ASIN cannot be merged with anything, so it is
            # kept as its own row rather than dropped or collided.
            key = record.get('asin') or (path, position)
            if key not in chosen:
                chosen[key] = record
                order.append(key)
                continue
            superseded.add(key)
            if fetched_at(record) > fetched_at(chosen[key]):
                chosen[key] = record

    return ([chosen[key] for key in order],
            {'records': len(order), 'feeds': len(paths),
             'superseded': len(superseded)})


def provenance_line(provenance):
    """The one line a report opens with, so a number can be traced to a crawl."""
    feeds, superseded = provenance['feeds'], provenance['superseded']
    return (f'{provenance["records"]} records from {feeds} '
            f'feed{"s" if feeds != 1 else ""}, '
            f'{superseded} ASIN{"s" if superseded != 1 else ""} '
            f'superseded by a fresher crawl')
