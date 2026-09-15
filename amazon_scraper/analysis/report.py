"""Rendering: evidence cards, comparisons, rankings and a corpus summary.

The output format is a product decision, not a presentation detail. Nothing
here emits a quality score, and the reason is measurable in both categories
shipped. For dry pasta, price per kg is disputed or unknown on a real
fraction of records, plausible protein exists on a third, bronze-die claims on
about a third; for tyre mounting paste the criterion that decides the whole
purchase is stated on 3 of 43 listings. A single number computed over that
would be a confident answer built on inputs that are partly wrong and mostly
missing -- and it could not answer "why is A better than B", which is the
whole point.

So the unit of output is an evidence card, and the unit of comparison is a
difference with the quote behind it. Missing data is shown as missing.

Everything below is driven by the category's own descriptor -- its axes, their
direction, its claims -- so a new category gets the same reports without
touching this file.
"""

from dataclasses import replace

from ..validation import (DISPUTED, NOT_CLAIMED, TRUSTED, UNKNOWN, UNVERIFIED,
                          variation)
from .category import get, is_match

MARK = {TRUSTED: 'trusted', DISPUTED: 'DISPUTED', UNVERIFIED: 'unverified',
        UNKNOWN: 'unknown', NOT_CLAIMED: 'not claimed'}

WIDTH = 78
INDENT = ' ' * 18


def category_of(card):
    return get(card['category_key'])


def _wrap(text, indent=INDENT, width=WIDTH):
    words, lines, line = text.split(), [], indent
    for word in words:
        if len(line) + len(word) + 1 > width and line.strip():
            lines.append(line.rstrip())
            line = indent
        line += word + ' '
    if line.strip():
        lines.append(line.rstrip())
    return lines


def _shown(value, axis=None):
    if not value.known:
        return '—'
    if axis is not None and axis.render:
        return axis.render(value.value)
    text = f'{value.value:g}' if isinstance(value.value, (int, float)) \
        else f'{value.value}'
    return f'{text} {value.unit}'.strip() if value.unit else text


def _value_lines(label, value, axis=None):
    """One labelled value with its status, notes and evidence."""
    if value is None:
        return []
    lines = [f'  {label:<14} {_shown(value, axis):<40} [{MARK[value.status]}]']
    if axis is not None and axis.caveat and value.known:
        lines += _wrap(f'· {axis.caveat}')
    for note in value.notes:
        lines += _wrap(f'! {note}')
    for item in value.evidence:
        lines += _wrap(f'← {item.field}: "{item.quote}"')
    return lines


def card_text(card):
    """One product's evidence card."""
    category = category_of(card)
    head = f'{card["brand"] or "?"} · {card["title"] or ""}'
    lines = ['─' * WIDTH, head[:WIDTH],
             f'{card["asin"]}  ·  found via "{card["query"]}"', '']

    lines += _value_lines('Category', card['category'])
    if not is_match(card):
        lines += ['', f'  Not {category.label} — excluded from comparison.']
        return '\n'.join(lines)

    for axis in category.axes:
        value = card['axes'].get(axis.key)
        if value is not None:
            lines += _value_lines(axis.label, value, axis)

    if card.get('size_label'):
        lines.append(f'  {"Sold as":<14} {card["size_label"]}')
    siblings = [asin for asin in card.get('siblings') or []
                if asin != card['asin']]
    if siblings:
        lines += _wrap(
            f'Amazon lists {len(siblings)} other listing'
            f'{"s" if len(siblings) > 1 else ""} in the same product family: '
            + ', '.join(siblings[:6]) + ('…' if len(siblings) > 6 else ''),
            indent=' ' * 4)

    made = [(claim, card['claims'][claim.key]) for claim in category.claims
            if card['claims'].get(claim.key) is not None
            and card['claims'][claim.key].status != NOT_CLAIMED]
    silent = [claim for claim in category.claims
              if card['claims'].get(claim.key) is not None
              and card['claims'][claim.key].status == NOT_CLAIMED]
    # A category may add a claim that is not in its static list, e.g. a
    # consistency check that only fires on a contradiction.
    extra = [(key, value) for key, value in card['claims'].items()
             if category.claim(key) is None]

    if made or extra:
        lines += ['', '  Claims']
        for claim, value in made:
            flag = '!' if value.status == DISPUTED or claim.adverse else '✓'
            lines.append(f'    {flag} {claim.label}')
            if claim.why:
                lines += _wrap(f'· {claim.why}', indent=' ' * 8)
            for note in value.notes:
                lines += _wrap(f'! {note}', indent=' ' * 8)
            for item in value.evidence[:1]:
                lines += _wrap(f'← {item.field}: "{item.quote}"', indent=' ' * 8)
        for key, value in extra:
            lines.append(f'    {"!" if value.status == DISPUTED else "✓"} {key}')
            for note in value.notes:
                lines += _wrap(f'! {note}', indent=' ' * 8)
            for item in value.evidence[:1]:
                lines += _wrap(f'← {item.field}: "{item.quote}"', indent=' ' * 8)

    if silent:
        lines += ['', '  Not claimed (which is not the same as untrue)']
        lines += _wrap(', '.join(claim.label for claim in silent),
                       indent=' ' * 4)

    unknown = [axis.label for axis in category.axes
               if not (card['axes'].get(axis.key)
                       and card['axes'][axis.key].usable)]
    if unknown:
        lines += ['', '  Not known for this product']
        lines += _wrap(', '.join(unknown), indent=' ' * 4)

    if category.render_extra:
        lines += category.render_extra(card)
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _comparable(a, b):
    """Why these two values cannot be compared, or None if they can."""
    for name, value in (('the first', a), ('the second', b)):
        if value is None:
            return f'{name} product has no value for it'
        if not value.known:
            return f'{name} product has no value for it'
        if value.status == DISPUTED:
            return (f'{name} product\'s value is disputed: '
                    f'{value.notes[0] if value.notes else "see card"}')
        if value.status == UNVERIFIED:
            return (f'{name} product\'s value is unverified, so a difference '
                    f'would not mean anything')
    return None


def _mismatched_units(a, b):
    """Why two values on one axis cannot be set against each other, or ''."""
    if a.unit and b.unit and a.unit != b.unit:
        return (f'measured in different units ({a.unit} and {b.unit}), so the '
                f'two numbers are not comparable')
    return ''


def _axis_difference(axis, left, right):
    """A rendered difference on one axis, or None when there is none."""
    a, b = left['axes'].get(axis.key), right['axes'].get(axis.key)
    # A direction only means something for a number. An axis that declares one
    # over a list -- a mis-declared category -- degrades to "they differ"
    # rather than raising inside a report.
    if axis.better and not all(isinstance(v.value, (int, float))
                               for v in (a, b)):
        axis = replace(axis, better='')
    if not axis.better:
        if a is None or b is None or a.value == b.value:
            return None
        return (axis.label, f'A {_shown(a, axis)} vs B {_shown(b, axis)}',
                _mismatched_units(a, b) or axis.why or '')

    mismatch = _mismatched_units(a, b)
    if mismatch:
        # Two numbers in different units are not one axis. Report both and
        # say so, rather than declaring a winner between grams and
        # millilitres -- which is what a density would be needed for.
        return (axis.label, f'A {_shown(a, axis)} vs B {_shown(b, axis)}',
                mismatch)

    if abs(a.value - b.value) < axis.tolerance:
        return None
    winner = ('A' if ((a.value < b.value) == (axis.better == 'lower'))
              else 'B')
    low, high = sorted((abs(a.value), abs(b.value)))
    ratio = high / max(low, 1e-9)
    comparative = axis.comparative or f'{axis.better} on {axis.label.lower()}'
    why = (f'{winner} is {ratio:.1f}× {comparative}'
           if ratio >= 1.05 else f'{winner} is {comparative}')
    if axis.why:
        why = f'{why}, {axis.why}'
    return (axis.label, f'A {_shown(a, axis)} vs B {_shown(b, axis)}', why)


def compare_text(left, right):
    """Why one is the better buy — or why we cannot say."""
    category = category_of(left)
    lines = ['─' * WIDTH,
             f'A  {left["asin"]}  {(left["title"] or "")[:56]}',
             f'B  {right["asin"]}  {(right["title"] or "")[:56]}', '']

    for card, name in ((left, 'A'), (right, 'B')):
        if not is_match(card):
            lines.append(f'  {name} is not {category.label} '
                         f'({card["category"].notes[0] if card["category"].notes else ""}).'
                         ' Nothing to compare.')
            return '\n'.join(lines)

    # Amazon's own variation matrix says whether these are two products or one
    # product in two boxes. Comparing "quality" between pack sizes of the same
    # product is a research error, and a silent one: everything except the
    # price comes out identical, which reads like agreement rather than
    # tautology.
    if left.get('offer') and left['offer'] == right.get('offer'):
        return '\n'.join(lines + _same_offer_lines(category, left, right))

    differences, blocked = [], []
    for axis in category.axes:
        reason = _comparable(left['axes'].get(axis.key),
                             right['axes'].get(axis.key))
        if reason:
            blocked.append(f'{axis.label} — {reason}')
            continue
        difference = _axis_difference(axis, left, right)
        if difference:
            differences.append(difference)

    for claim in category.claims:
        claim_a, claim_b = left['claims'].get(claim.key), right['claims'].get(claim.key)
        if claim_a is None or claim_b is None:
            continue
        made_a, made_b = claim_a.status == TRUSTED, claim_b.status == TRUSTED
        if made_a == made_b:
            continue
        winner = 'A' if made_a else 'B'
        quote = (claim_a if made_a else claim_b).evidence
        shown = (f'{winner} states it, the other does not' if not claim.adverse
                 else f'{winner} declares it — which counts against it')
        differences.append(
            (claim.label, shown,
             f'{quote[0].field}: "{quote[0].quote}"' if quote else ''))

    if differences:
        lines.append('  Differences')
        for label, shown, why in differences:
            lines.append(f'    {label}')
            lines += _wrap(shown, indent=' ' * 6)
            if why:
                lines += _wrap(f'→ {why}', indent=' ' * 6)
        lines.append('')
    else:
        lines += ['  No difference the evidence supports.', '']

    if blocked:
        lines.append('  Cannot be compared')
        for item in blocked:
            lines += _wrap(item, indent=' ' * 4)
        lines.append('')

    lines += _wrap('A claim only one vendor makes is a difference in what they '
                   'wrote, not proof of a difference in the product.',
                   indent='  ')
    return '\n'.join(lines)


def _same_offer_lines(category, left, right):
    axis = category.axis(category.default_axis) or category.axes[0]
    lines = _wrap('Amazon lists these as the same product in different pack '
                  'sizes, not as two products.', indent='  ')
    lines.append('')
    for card, name in ((left, 'A'), (right, 'B')):
        value = card['axes'].get(axis.key)
        shown = (f'{_shown(value, axis)} [{MARK[value.status]}]'
                 if value is not None and value.known
                 else f'{axis.label.lower()} unknown')
        lines.append(f'    {name}  {pack_size(card):<22} {shown}')
    usable = [card for card in (left, right)
              if card['axes'].get(axis.key) is not None
              and card['axes'][axis.key].usable]
    best = (min(usable, key=lambda card: card['axes'][axis.key].value)
            if usable else None)
    lines.append('')
    lines += _wrap(
        f'Only the pack size differs, so the question is which pack to buy, '
        f'not which product is better: {"A" if best is left else "B"} wins on '
        f'{axis.label.lower()}.'
        if best else
        f'Only the pack size differs, and neither {axis.label.lower()} '
        f'survived validation, so there is nothing to choose between them '
        f'here.', indent='  ')
    return lines


# ---------------------------------------------------------------------------
# Ranking and corpus summary
# ---------------------------------------------------------------------------

def pack_size(card):
    """A readable pack size, preferring what Amazon labelled it."""
    if card.get('size_label'):
        return card['size_label']
    quantity = card['axes'].get('quantity') or card['validated'].quantity
    if not quantity.known:
        return '?'
    amount, unit = quantity.value, quantity.unit or 'g'
    big = {'g': 'kg', 'ml': 'l'}.get(unit)
    return (f'{amount / 1000:g} {big}' if big and amount >= 1000
            else f'{amount:g} {unit}')


def rank_text(cards, axis_key=None, require=(), limit=20):
    """Best-first on one axis the user names, one row per offer.

    Ranking is offered on a single axis, never on a composite: a composite
    would have to weigh a trusted price against an unverified figure and a
    claim nobody checked. Which direction counts as better belongs to the
    category -- cheapest per kilogram for dry pasta, *smallest pack* for a
    mounting paste nobody needs five kilograms of.

    Rows are *offers*, not ASINs: when two listings are the same product in
    different boxes, the best pack wins the row and the rest are named under
    it, so choosing a different size stays possible.
    """
    if not cards:
        return 'No records.'
    category = category_of(cards[0])
    axis = category.axis(axis_key or category.default_axis)
    if axis is None:
        return (f'{axis_key}: not an axis of {category.label}. '
                f'Known: {", ".join(category.axis_keys)}')

    matched = [card for card in cards if is_match(card)]
    wanted = [card for card in matched
              if all(card['claims'].get(key) is not None
                     and card['claims'][key].status == TRUSTED for key in require)]

    groups = variation.group_offers(wanted)
    reverse = axis.better == 'higher'
    ranked, dropped = [], []
    for _, members in groups:
        usable = [card for card in members
                  if card['axes'].get(axis.key) is not None
                  and card['axes'][axis.key].usable]
        if usable:
            usable.sort(key=lambda card: card['axes'][axis.key].value,
                        reverse=reverse)
            ranked.append(usable)
        else:
            dropped.extend(members)

    ranked.sort(key=lambda members: members[0]['axes'][axis.key].value,
                reverse=reverse)
    collapsed = sum(len(members) - 1 for members in ranked)

    lines = [f'{category.label}: ranked by {axis.label.lower()}'
             + (f' ({axis.better} first)' if axis.better else '')
             + (f', requiring {", ".join(require)}' if require else ''),
             f'{len(matched)} {category.label} · {len(wanted)} match the filter · '
             f'{len(ranked)} offers with a trusted {axis.key}'
             + (f' · {collapsed} pack-size variants folded in'
                if collapsed else ''), '']
    if category.blurb:
        lines = lines[:1] + _wrap(category.blurb, indent='  ') + lines[1:]

    for position, members in enumerate(ranked[:limit], start=1):
        best = members[0]
        lines.append(f'{position:>3}. {_shown(best["axes"][axis.key], axis):<16}'
                     f'{(best["brand"] or "?")[:20]:<22}'
                     f'{(best["title"] or "")[:30]:<32}'
                     f'{best["asin"]}  {pack_size(best)}')
        for other in members[1:]:
            lines.append(f'     {_shown(other["axes"][axis.key], axis):<16}'
                         f'{"same product, other pack":<54}'
                         f'{other["asin"]}  {pack_size(other)}')

    if dropped:
        lines += ['', f'  Excluded from the ranking ({len(dropped)}), '
                      f'because ranking them would be guessing:']
        for card in dropped[:10]:
            value = card['axes'].get(axis.key)
            why = ((value.notes[0] if value.notes else value.status)
                   if value is not None else 'no value for this axis')
            lines += _wrap(f'{card["asin"]} — {why}', indent=' ' * 4)
        if len(dropped) > 10:
            lines.append(f'    … and {len(dropped) - 10} more')
    return '\n'.join(lines)


def summary_text(cards):
    """How much of this corpus is actually usable, and where it fails."""
    if not cards:
        return 'No records.'
    category = category_of(cards[0])
    matched = [card for card in cards if is_match(card)]
    other = [card for card in cards
             if card['category'].value == 'other']
    unclassified = [card for card in cards if not card['category'].known]

    lines = ['─' * WIDTH, f'Corpus quality · {category.label}', '─' * WIDTH,
             f'  {len(cards)} records · {len(matched)} {category.label} · '
             f'{len(other)} other products · {len(unclassified)} unclassified',
             '']

    for axis in category.axes:
        counts = {}
        for card in matched:
            value = card['axes'].get(axis.key)
            status = value.status if value is not None else 'absent'
            counts[status] = counts.get(status, 0) + 1
        shown = '  '.join(f'{MARK.get(status, status)} {count}'
                          for status, count in sorted(counts.items()))
        lines.append(f'  {axis.key:<16} {shown}')

    lines.append('')
    for claim in category.claims:
        made = sum(1 for card in matched
                   if card['claims'].get(claim.key) is not None
                   and card['claims'][claim.key].status == TRUSTED)
        lines.append(f'  {claim.label:<34} '
                     f'{"declared by" if claim.adverse else "claimed by"} '
                     f'{made:>3} of {len(matched)}')

    offers = variation.group_offers(matched)
    folded = sum(len(members) - 1 for _, members in offers)
    with_family = sum(1 for card in matched if card.get('offer'))
    lines += ['', f'  {len(matched)} listings are {len(offers)} offers '
                  f'({folded} pack-size variants of a product already listed). '
                  f'{with_family} carry a variation matrix.']

    rankable = [axis for axis in category.axes if axis.better]
    comparable = sum(1 for card in matched
                     if any(card['axes'].get(axis.key) is not None
                            and card['axes'][axis.key].usable
                            for axis in rankable))
    lines += ['', f'  {comparable} of {len(matched)} have at least one trusted '
                  f'comparison axis.']
    disputed = [card for card in matched
                if any(card['axes'].get(axis.key) is not None
                       and card['axes'][axis.key].status == DISPUTED
                       for axis in category.axes)]
    lines.append(f'  {len(disputed)} carry a disputed value and are shown with '
                 f'the contradiction rather than ranked on it.')
    return '\n'.join(lines)


def card_json(card):
    """The card as plain data, for a downstream consumer or an AI reader."""
    out = {key: card[key] for key in ('category_key', 'asin', 'title', 'brand',
                                      'url', 'query')}
    out['category'] = card['category'].as_dict()
    out['axes'] = {key: value.as_dict()
                   for key, value in sorted(card['axes'].items())}
    out['claims'] = {key: value.as_dict()
                     for key, value in sorted(card['claims'].items())}
    out['validated'] = card['validated'].as_dict()
    if card.get('drying'):
        out['drying'] = {key: value.as_dict()
                         for key, value in card['drying'].items()}
    if card.get('suitability'):
        out['suitability'] = card['suitability']
    return out
