"""Rendering: evidence cards, comparisons and a corpus-quality summary.

The output format is a product decision, not a presentation detail. V1 does
not emit a quality score, and the reason is measurable: price per kg is
disputed or unknown on a real fraction of records, plausible protein exists on
a third of them, and bronze-die claims on about a third. A single number
computed over that would be a confident answer built on inputs that are partly
wrong and mostly missing -- and it could not answer "why is A better than B",
which is the whole point.

So the unit of output is an evidence card, and the unit of comparison is a
difference with the quote behind it. Missing data is shown as missing.
"""

from .evidence import DISPUTED, NOT_CLAIMED, TRUSTED, UNKNOWN, UNVERIFIED
from .pasta import CLAIMS, is_pasta

MARK = {TRUSTED: 'trusted', DISPUTED: 'DISPUTED', UNVERIFIED: 'unverified',
        UNKNOWN: 'unknown', NOT_CLAIMED: 'not claimed'}

CLAIM_LABELS = {key: label for key, label, _ in CLAIMS}
CLAIM_LABELS['pure_durum'] = '100% durum wheat'

MATERIAL_LABELS = {
    'durum_wheat': 'durum wheat', 'wholegrain': 'wholegrain',
    'egg': 'egg', 'legume': 'legume flour',
    'gluten_free_grain': 'maize / rice / buckwheat',
}

NUTRIENT_LABELS = {
    'energy_kcal': 'Energy', 'protein_g': 'Protein',
    'carbohydrates_g': 'Carbohydrate', 'fat_g': 'Fat',
    'fiber_g': 'Fibre', 'salt_g': 'Salt', 'sugars_g': 'Sugars',
    'saturated_fat_g': 'Saturated fat', 'energy_kj': 'Energy',
    'sodium_mg': 'Sodium',
}

CATEGORY_LABELS = {'dry_pasta': 'dry pasta', 'other': 'not dry pasta'}

WIDTH = 78
INDENT = ' ' * 18


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


def _value_lines(label, value, render=None):
    """One labelled value with its status, notes and evidence."""
    if value is None:
        return []
    shown = (render(value.value) if render and value.known
             else ('—' if not value.known else f'{value.value}'))
    if value.unit and value.known:
        shown = f'{shown} {value.unit}'
    lines = [f'  {label:<14} {shown:<40} [{MARK[value.status]}]']
    for note in value.notes:
        lines += _wrap(f'! {note}')
    for item in value.evidence:
        lines += _wrap(f'← {item.field}: "{item.quote}"')
    return lines


def _number(value):
    return f'{value:g}'


def card_text(card):
    """One product's evidence card."""
    head = f'{card["brand"] or "?"} · {card["title"] or ""}'
    lines = ['─' * WIDTH, head[:WIDTH],
             f'{card["asin"]}  ·  found via "{card["query"]}"', '']

    lines += _value_lines('Category', card['category'],
                          lambda value: CATEGORY_LABELS.get(value, value))
    if not is_pasta(card):
        lines.append('')
        lines.append('  Not dry pasta — excluded from comparison.')
        return '\n'.join(lines)

    lines += _value_lines(
        'Made of', card['raw_materials'],
        lambda keys: ', '.join(MATERIAL_LABELS.get(k, k) for k in keys))
    lines += _value_lines('Price per kg', card['price_per_kg'], _number)
    lines += _value_lines('Pack size', card['quantity'], _number)

    for key in ('protein_g', 'energy_kcal', 'fiber_g'):
        value = card['nutrition'].get(key)
        if value is not None:
            lines += _value_lines(NUTRIENT_LABELS[key], value, _number)

    claimed = [(key, value) for key, value in card['claims'].items()
               if value.status != NOT_CLAIMED]
    silent = [key for key, value in card['claims'].items()
              if value.status == NOT_CLAIMED]

    if claimed:
        lines += ['', '  Claims']
        for key, value in claimed:
            flag = '!' if value.status == DISPUTED else '✓'
            lines.append(f'    {flag} {CLAIM_LABELS.get(key, key)}')
            for note in value.notes:
                lines += _wrap(f'! {note}', indent=' ' * 8)
            for item in value.evidence[:1]:
                lines += _wrap(f'← {item.field}: "{item.quote}"', indent=' ' * 8)

    if silent:
        lines += ['', '  Not claimed (which is not the same as untrue)']
        lines += _wrap(', '.join(CLAIM_LABELS.get(k, k) for k in silent),
                       indent=' ' * 4)

    unknown = [NUTRIENT_LABELS.get(k, k) for k in ('protein_g', 'energy_kcal',
                                                   'fiber_g', 'carbohydrates_g')
               if not (card['nutrition'].get(k) and card['nutrition'][k].usable)]
    if unknown:
        lines += ['', '  Not known for this product']
        lines += _wrap(', '.join(unknown), indent=' ' * 4)

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _comparable(a, b):
    """Why these two values cannot be compared, or None if they can."""
    for name, value in (('the first', a), ('the second', b)):
        if not value.known:
            return f'{name} product has no value for it'
        if value.status == DISPUTED:
            return (f'{name} product\'s value is disputed: '
                    f'{value.notes[0] if value.notes else "see card"}')
        if value.status == UNVERIFIED:
            return (f'{name} product\'s value is unverified, so a difference '
                    f'would not mean anything')
    return None


def compare_text(left, right):
    """Why one pasta is a better buy than the other — or why we cannot say."""
    lines = ['─' * WIDTH,
             f'A  {left["asin"]}  {(left["title"] or "")[:56]}',
             f'B  {right["asin"]}  {(right["title"] or "")[:56]}', '']

    for card, name in ((left, 'A'), (right, 'B')):
        if not is_pasta(card):
            lines.append(f'  {name} is not dry pasta '
                         f'({card["category"].notes[0] if card["category"].notes else ""}).'
                         ' Nothing to compare.')
            return '\n'.join(lines)

    differences, blocked = [], []

    price_a, price_b = left['price_per_kg'], right['price_per_kg']
    reason = _comparable(price_a, price_b)
    if reason:
        blocked.append(f'Price per kg — {reason}')
    else:
        cheaper, dearer = ((left, right) if price_a.value <= price_b.value
                           else (right, left))
        ratio = max(price_a.value, price_b.value) / max(
            min(price_a.value, price_b.value), 1e-9)
        differences.append(
            (f'Price per kg', f'A {price_a.value:g} vs B {price_b.value:g} '
             f'{price_a.unit}',
             f'{"A" if cheaper is left else "B"} is '
             f'{ratio:.1f}× cheaper per kilogram'))

    mats_a, mats_b = left['raw_materials'], right['raw_materials']
    reason = _comparable(mats_a, mats_b)
    if reason:
        blocked.append(f'Raw material — {reason}')
    elif set(mats_a.value) != set(mats_b.value):
        differences.append(
            ('Raw material',
             f'A {", ".join(MATERIAL_LABELS.get(k, k) for k in mats_a.value)} vs '
             f'B {", ".join(MATERIAL_LABELS.get(k, k) for k in mats_b.value)}',
             'different raw materials — these are not the same kind of pasta'))

    protein_a = left['nutrition'].get('protein_g')
    protein_b = right['nutrition'].get('protein_g')
    if protein_a is None or protein_b is None:
        blocked.append('Protein — not published for '
                       + ('both products' if protein_a is None and protein_b is None
                          else 'one of the two'))
    else:
        reason = _comparable(protein_a, protein_b)
        if reason:
            blocked.append(f'Protein — {reason}')
        elif abs(protein_a.value - protein_b.value) >= 1.0:
            higher = 'A' if protein_a.value > protein_b.value else 'B'
            differences.append(
                ('Protein', f'A {protein_a.value:g} vs B {protein_b.value:g} g/100 g',
                 f'{higher} has more protein, which for durum pasta tracks '
                 f'semolina quality'))

    for key, label, _ in CLAIMS:
        claim_a, claim_b = left['claims'][key], right['claims'][key]
        made_a = claim_a.status == TRUSTED
        made_b = claim_b.status == TRUSTED
        if made_a == made_b:
            continue
        winner, loser = ('A', left) if made_a else ('B', right)
        quote = (left if made_a else right)['claims'][key].evidence
        differences.append(
            (label, f'{winner} claims it, the other does not',
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
                   'wrote, not proof of a difference in the pasta.',
                   indent='  ')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Ranking and corpus summary
# ---------------------------------------------------------------------------

def rank_text(cards, axis='price_per_kg', require=(), limit=20):
    """Cheapest-first within one axis, over products that survived validation.

    Ranking is offered on a single axis the user names, never on a composite:
    a composite would have to weigh a trusted price against an unverified
    protein figure and a claim nobody checked.
    """
    pasta = [card for card in cards if is_pasta(card)]
    wanted = [card for card in pasta
              if all(card['claims'].get(key) is not None
                     and card['claims'][key].status == TRUSTED for key in require)]
    usable = [card for card in wanted if card[axis].usable]
    dropped = [card for card in wanted if not card[axis].usable]

    lines = [f'Ranked by {axis}'
             + (f', requiring {", ".join(require)}' if require else ''),
             f'{len(pasta)} dry pastas · {len(wanted)} match the filter · '
             f'{len(usable)} have a trusted {axis}', '']
    for position, card in enumerate(sorted(usable, key=lambda c: c[axis].value)[:limit],
                                    start=1):
        mats = (', '.join(MATERIAL_LABELS.get(k, k)
                          for k in (card['raw_materials'].value or []))
                if card['raw_materials'].known else 'raw material unknown')
        lines.append(f'{position:>3}. {card[axis].value:>7g} {card[axis].unit:<8} '
                     f'{(card["brand"] or "?")[:22]:<24}{mats[:26]:<28}{card["asin"]}')

    if dropped:
        lines += ['', f'  Excluded from the ranking ({len(dropped)}), '
                      f'because ranking them would be guessing:']
        for card in dropped[:10]:
            why = (card[axis].notes[0] if card[axis].notes else card[axis].status)
            lines += _wrap(f'{card["asin"]} — {why}', indent=' ' * 4)
        if len(dropped) > 10:
            lines.append(f'    … and {len(dropped) - 10} more')
    return '\n'.join(lines)


def summary_text(cards):
    """How much of this corpus is actually usable, and where it fails."""
    pasta = [card for card in cards if is_pasta(card)]
    other = [card for card in cards if card['category'].value == 'other']
    unclassified = [card for card in cards if not card['category'].known]

    lines = ['─' * WIDTH, 'Corpus quality', '─' * WIDTH,
             f'  {len(cards)} records · {len(pasta)} dry pasta · '
             f'{len(other)} other products · {len(unclassified)} unclassified', '']

    for axis in ('price_per_kg', 'quantity', 'raw_materials'):
        counts = {}
        for card in pasta:
            counts[card[axis].status] = counts.get(card[axis].status, 0) + 1
        shown = '  '.join(f'{MARK[status]} {count}'
                          for status, count in sorted(counts.items()))
        lines.append(f'  {axis:<16} {shown}')

    nutri = {}
    for card in pasta:
        value = card['nutrition'].get('protein_g')
        status = value.status if value is not None else 'absent'
        nutri[status] = nutri.get(status, 0) + 1
    lines.append('  protein_g        ' + '  '.join(
        f'{MARK.get(status, status)} {count}' for status, count in sorted(nutri.items())))

    lines.append('')
    for key, label, _ in CLAIMS:
        made = sum(1 for card in pasta if card['claims'][key].status == TRUSTED)
        lines.append(f'  {label:<26} claimed by {made:>3} of {len(pasta)}')

    comparable = sum(1 for card in pasta
                     if card['price_per_kg'].usable or card['raw_materials'].usable)
    lines += ['', f'  {comparable} of {len(pasta)} dry pastas have at least one '
                  f'trusted comparison axis.']
    disputed = [card for card in pasta if card['price_per_kg'].status == DISPUTED]
    lines.append(f'  {len(disputed)} have a disputed price per kg and are shown '
                 f'with the contradiction rather than ranked.')
    return '\n'.join(lines)


def card_json(card):
    """The card as plain data, for a downstream consumer or an AI reader."""
    out = {key: card[key] for key in ('asin', 'title', 'brand', 'url', 'query')}
    for key in ('category', 'raw_materials', 'quantity', 'price_per_kg'):
        out[key] = card[key].as_dict()
    out['nutrition'] = {key: value.as_dict()
                        for key, value in card['nutrition'].items()}
    out['claims'] = {key: value.as_dict() for key, value in card['claims'].items()}
    out['drying'] = {key: value.as_dict() for key, value in card['drying'].items()}
    return out
