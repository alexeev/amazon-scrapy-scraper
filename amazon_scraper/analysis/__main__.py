"""Command line for the category analysis.

    uv run python -m amazon_scraper.analysis summary data/products.jsonl
    uv run python -m amazon_scraper.analysis rank    data/products.jsonl \
        --require bronze_die --limit 15
    uv run python -m amazon_scraper.analysis card    data/products.jsonl B0CPQ5HGC8
    uv run python -m amazon_scraper.analysis compare data/products.jsonl A B
    uv run python -m amazon_scraper.analysis cards   data/products.jsonl --json

Every command takes ``--category`` (default ``dry_pasta``). The same records
can be read by any category: which one is right for a file is a question
about the crawl, not about the data.

    uv run python -m amazon_scraper.analysis rank data/paste.jsonl \
        --category tyre_mounting_paste
"""

import argparse
import gzip
import json
import sys

from . import report
from . import categories  # noqa: F401  (registers the built-ins)
from .category import get, is_match, known


def load(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def pick(cards, asin):
    for card in cards:
        if card['asin'] == asin:
            return card
    sys.exit(f'{asin}: not in this file')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='amazon_scraper.analysis',
                                     description=__doc__)
    parser.add_argument('command',
                        choices=('summary', 'rank', 'card', 'cards', 'compare',
                                 'validated'))
    parser.add_argument('records', help='JSONL written by the amazon_product spider')
    parser.add_argument('asins', nargs='*', help='ASIN(s), for card and compare')
    parser.add_argument('--category', default='dry_pasta',
                        help=f'one of: {", ".join(known())}')
    parser.add_argument('--require', default='',
                        help='comma-separated claims a product must make to be '
                             'ranked')
    parser.add_argument('--axis', default='',
                        help="comparison axis to rank on; defaults to the "
                             "category's own")
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--json', action='store_true',
                        help='emit cards as JSON instead of text')
    args = parser.parse_args(argv)

    try:
        category = get(args.category)
    except KeyError as exc:
        sys.exit(str(exc).strip("'"))

    records = load(args.records)

    if args.command == 'validated':
        # The contract itself, with no category interpretation on top. This is
        # what a new analyzer starts from, and what the corpus test pins.
        from ..validation import validate
        for record in records:
            print(json.dumps(validate(record, category.profile).as_dict(),
                             ensure_ascii=False))
        return

    cards = [category.evaluate(record) for record in records]
    require = tuple(key.strip() for key in args.require.split(',') if key.strip())
    for key in require:
        if key not in category.claim_keys:
            sys.exit(f'{key}: not a claim of {category.label}. '
                     f'Known: {", ".join(category.claim_keys)}')
    if args.axis and category.axis(args.axis) is None:
        sys.exit(f'{args.axis}: not an axis of {category.label}. '
                 f'Known: {", ".join(category.axis_keys)}')

    if args.command == 'summary':
        print(report.summary_text(cards))
    elif args.command == 'rank':
        print(report.rank_text(cards, args.axis, require, args.limit))
    elif args.command == 'card':
        if not args.asins:
            sys.exit('card needs an ASIN')
        for asin in args.asins:
            card = pick(cards, asin)
            print(json.dumps(report.card_json(card), ensure_ascii=False, indent=2)
                  if args.json else report.card_text(card))
    elif args.command == 'cards':
        chosen = [card for card in cards if is_match(card)]
        for card in chosen:
            print(json.dumps(report.card_json(card), ensure_ascii=False)
                  if args.json else report.card_text(card))
    elif args.command == 'compare':
        if len(args.asins) != 2:
            sys.exit('compare needs exactly two ASINs')
        print(report.compare_text(pick(cards, args.asins[0]),
                                  pick(cards, args.asins[1])))


if __name__ == '__main__':
    main()
