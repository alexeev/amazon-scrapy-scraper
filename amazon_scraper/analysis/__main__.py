"""Command line for the pasta analysis.

    uv run python -m amazon_scraper.analysis summary  data/products.jsonl
    uv run python -m amazon_scraper.analysis rank     data/products.jsonl \
        --require bronze_die --limit 15
    uv run python -m amazon_scraper.analysis card     data/products.jsonl B0CPQ5HGC8
    uv run python -m amazon_scraper.analysis compare  data/products.jsonl A B
    uv run python -m amazon_scraper.analysis cards    data/products.jsonl --json
"""

import argparse
import gzip
import json
import sys

from . import report
from .pasta import CLAIMS, evaluate, is_pasta

CLAIM_KEYS = [key for key, _, _ in CLAIMS]


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
                        choices=('summary', 'rank', 'card', 'cards', 'compare'))
    parser.add_argument('records', help='JSONL written by the amazon_product spider')
    parser.add_argument('asins', nargs='*', help='ASIN(s), for card and compare')
    parser.add_argument('--require', default='',
                        help='comma-separated claims a product must make to be '
                             f'ranked; one of: {", ".join(CLAIM_KEYS)}')
    parser.add_argument('--axis', default='price_per_kg',
                        choices=('price_per_kg', 'quantity'))
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--json', action='store_true',
                        help='emit cards as JSON instead of text')
    args = parser.parse_args(argv)

    cards = [evaluate(record) for record in load(args.records)]
    require = tuple(key.strip() for key in args.require.split(',') if key.strip())
    for key in require:
        if key not in CLAIM_KEYS:
            sys.exit(f'{key}: unknown claim. Known: {", ".join(CLAIM_KEYS)}')

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
        chosen = [card for card in cards if is_pasta(card)]
        if args.json:
            for card in chosen:
                print(json.dumps(report.card_json(card), ensure_ascii=False))
        else:
            for card in chosen:
                print(report.card_text(card))
    elif args.command == 'compare':
        if len(args.asins) != 2:
            sys.exit('compare needs exactly two ASINs')
        print(report.compare_text(pick(cards, args.asins[0]),
                                  pick(cards, args.asins[1])))


if __name__ == '__main__':
    main()
