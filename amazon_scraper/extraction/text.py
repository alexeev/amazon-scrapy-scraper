"""Text and number primitives shared by every extractor.

Nothing in this module knows about Amazon. It deals with the three things
that make raw marketplace HTML awkward to read: invisible formatting
characters, script/style noise inside otherwise content-bearing nodes, and
locale-specific number formats.
"""

import html as _html
import re

from parsel import Selector, SelectorList

# Amazon wraps detail-bullet labels in RLM/LRM marks ("Marke ‏ : ‎")
# and uses NBSP inside prices and units.
_INVISIBLE = dict.fromkeys(
    map(ord, '​‌‍‎‏⁠﻿'), None)

_WS_RE = re.compile(r'\s+')

# Amazon splits running prose across adjacent inline <span>s to bold allergens
# ("<span>HARTWEIZENGRIEß</span><span>, Wasser.</span>"). Joining text nodes
# with a space then leaves a gap in front of the punctuation.
_SPACE_BEFORE_PUNCT_RE = re.compile(r'\s+([,.;:!?%)\]])')
_SPACE_AFTER_OPEN_RE = re.compile(r'([(\[])\s+')
# Bold allergens also split compound words ("<b>DINKEL</b>-VOLLKORNMEHL").
# Only rejoin when the hyphen leads into a word, so "bis -18 °C" is untouched.
_SPLIT_COMPOUND_RE = re.compile(r'(?<=\w)\s+(-[^\W\d_])')

# Text nodes that belong to the document's machinery rather than its content.
_TEXT_XPATH = (
    './/text()[not(ancestor-or-self::script)]'
    '[not(ancestor-or-self::style)]'
    '[not(ancestor-or-self::noscript)]'
)


def clean(value):
    """Collapse whitespace and drop invisible formatting characters."""
    if not value:
        return ''
    collapsed = _WS_RE.sub(' ', value.translate(_INVISIBLE).replace('\xa0', ' '))
    collapsed = _SPACE_BEFORE_PUNCT_RE.sub(r'\1', collapsed)
    collapsed = _SPLIT_COMPOUND_RE.sub(r'\1', collapsed)
    return _SPACE_AFTER_OPEN_RE.sub(r'\1', collapsed).strip()


def node_text(node, separator=' '):
    """Visible text of a node (or of every node in a SelectorList).

    Unlike ``node.css('::text')`` this skips ``<script>``/``<style>`` bodies,
    which matter on Amazon: A+ modules ship their own inline CSS, so a naive
    text join returns kilobytes of stylesheet instead of product copy.
    """
    if node is None:
        return ''
    if isinstance(node, SelectorList):
        parts = [node_text(item, separator) for item in node]
        return clean(separator.join(part for part in parts if part))
    if not isinstance(node, Selector):
        return clean(str(node))
    return clean(separator.join(node.xpath(_TEXT_XPATH).getall()))


def node_lines(node):
    """Visible text of a node split into non-empty logical lines."""
    if node is None:
        return []
    nodes = node if isinstance(node, SelectorList) else [node]
    lines, seen = [], set()
    for item in nodes:
        for raw in item.xpath(_TEXT_XPATH).getall():
            line = clean(raw)
            if line and line not in seen:
                seen.add(line)
                lines.append(line)
    return lines


def first_text(root, *css_selectors):
    """Text of the first *element* any of ``css_selectors`` matches.

    Deliberately not a join over all matches: Amazon renders the same
    accessibility label once per purchase option, so joining turns
    "3,39 €" into "3,39 € 3,22 € mit 5 Prozent Einsparungen".
    """
    for css in css_selectors:
        for node in root.css(css):
            text = node_text(node)
            if text:
                return text
    return ''


# Accessibility labels on Amazon are HTML-escaped a second time, so the
# decoded text still reads "13,56&nbsp;&euro; pro kg".
_ENTITY_RE = re.compile(r'&(?:[a-zA-Z][a-zA-Z0-9]{1,8}|#\d{1,5}|#[xX][0-9a-fA-F]{1,4});')


def decode_entities(value):
    """Undo one extra round of HTML escaping, if there is one."""
    if value and _ENTITY_RE.search(value):
        return clean(_html.unescape(value))
    return value


# --- numbers ---------------------------------------------------------------

_NUMBER_RE = re.compile(r'-?\d[\d.,   ]*\d|-?\d')


def parse_number(text, decimal_sep=','):
    """Parse the first number out of ``text`` for a given locale.

    Amazon mixes formats on the same page: a German PDP shows ``12,9g`` in the
    nutrition table but ``3000.0 gramm`` in the attribute table, and ``1.234,56``
    for large prices. The separator that appears last wins, which resolves all
    three without needing to know which module the string came from.
    """
    if not text:
        return None
    match = _NUMBER_RE.search(clean(str(text)))
    if not match:
        return None

    raw = re.sub(r'[   ]', '', match.group(0))
    has_dot, has_comma = '.' in raw, ',' in raw

    if has_dot and has_comma:
        sep = '.' if raw.rfind('.') > raw.rfind(',') else ','
    elif has_dot or has_comma:
        sep = '.' if has_dot else ','
        tail = raw.rsplit(sep, 1)[1]
        # A single separator followed by exactly three digits is grouping,
        # unless it is this locale's decimal separator ("1,500" kg is 1.5).
        if raw.count(sep) > 1 or (len(tail) == 3 and sep != decimal_sep):
            sep = None
    else:
        sep = None

    if sep is None:
        digits = re.sub(r'[.,]', '', raw)
    else:
        whole, _, frac = raw.rpartition(sep)
        digits = re.sub(r'[.,]', '', whole) + '.' + frac

    try:
        return float(digits)
    except ValueError:
        return None


def parse_int(text, decimal_sep=','):
    value = parse_number(text, decimal_sep)
    return int(value) if value is not None and value == int(value) else None


def parse_quantity(text, units, decimal_sep=','):
    """Split "500 Gramm" / "1,5 kg" / "6 x 500g" into a normalised quantity.

    Returns ``(amount, canonical_unit, base_amount)`` where ``base_amount`` is
    expressed in grams (mass) or millilitres (volume), or ``None`` when the
    string carries no recognisable unit. A leading multiplier ("6 x 500 g") is
    applied, which is how multipacks are written on both .de and .com.
    """
    if not text:
        return None
    normalised = clean(str(text)).lower().replace('×', 'x')

    multiplier = 1.0
    pack = re.match(r'^\s*(\d+)\s*x\s*(.+)$', normalised)
    if pack:
        multiplier = float(pack.group(1))
        normalised = pack.group(2)

    unit_names = sorted(units, key=len, reverse=True)
    match = re.search(
        r'(\d[\d.,   ]*)\s*(' + '|'.join(re.escape(u) for u in unit_names) + r')\b',
        normalised)
    if not match:
        return None

    amount = parse_number(match.group(1), decimal_sep)
    if amount is None:
        return None
    symbol, factor = units[match.group(2)]
    amount *= multiplier
    return amount, symbol, amount * factor
