"""Generic harvesters for the structural shapes Amazon reuses across PDPs.

These know about *page shapes* (a two-column table, a label/value bullet, an
expander section, the image blob) but not about products, food or locales.
A block returns ``None`` when the structure is absent and a value when it is
present, so the caller can tell "Amazon did not publish this" apart from
"our parser broke".
"""

import json
import re

from .text import clean, node_lines, node_text

# ---------------------------------------------------------------------------
# Key/value structures
# ---------------------------------------------------------------------------

# Two-column attribute tables. Amazon renders the same data under several
# containers depending on category and layout experiment.
KV_TABLE_CSS = (
    '#productOverview_feature_div table',
    '#poExpander table',
    '#poExpander table.a-normal',
    'table.a-normal.a-spacing-micro',
    '#productDetails_techSpec_section_1',
    '#productDetails_techSpec_section_2',
    '#productDetails_detailBullets_sections1',
    '#prodDetails table',
    '#technicalSpecifications_feature_div table',
)

# Label/value bullet lists ("Hersteller ‏ : ‎ Naturata AG").
KV_BULLET_CSS = (
    '#detailBullets_feature_div li',
    '#detailBulletsWrapper_feature_div li',
    '#productFactsDesktop_feature_div .a-fixed-left-grid',
)


def key_value_tables(root, css_selectors=KV_TABLE_CSS):
    """Every two-cell row of every attribute table, as (label, value) pairs.

    Rows are returned in document order and duplicates are kept: the caller
    decides precedence, and knowing that two containers agreed is useful.
    """
    pairs = []
    # The same <table> is reachable through several of the selectors above;
    # identity-dedupe so values are not counted twice. The elements are kept
    # in a list rather than reduced to id() values: lxml builds an element
    # proxy on demand and frees it once nothing refers to it, so id() values
    # of released proxies get recycled and would collide with unrelated
    # tables. Holding the proxies keeps their identity meaningful.
    seen_tables = []
    for css in css_selectors:
        for table in root.css(css):
            if any(table.root is seen for seen in seen_tables):
                continue
            seen_tables.append(table.root)
            for row in table.css('tr'):
                cells = row.xpath('./th | ./td')
                if len(cells) != 2:
                    continue
                label = clean(node_text(cells[0])).rstrip(':').strip()
                value = clean(node_text(cells[1]))
                if label and value:
                    pairs.append((label, value))
    return pairs


def key_value_bullets(root, css_selectors=KV_BULLET_CSS):
    """(label, value) pairs from Amazon's label/value bullet lists."""
    pairs = []
    for css in css_selectors:
        for item in root.css(css):
            spans = item.css('span.a-list-item > span')
            if len(spans) >= 2:
                label = clean(node_text(spans[0])).rstrip(':').strip()
                value = clean(node_text(spans[1]))
            else:
                text = clean(node_text(item))
                # "Label : Value" with the bidi marks already stripped.
                match = re.match(r'^(.{2,60}?)\s*:\s*(.+)$', text)
                if not match:
                    continue
                label, value = match.group(1).strip(), match.group(2).strip()
            if label and value and len(label) <= 80:
                pairs.append((label, value))
    return pairs


def bullet_list(root, css):
    """Non-empty list items under ``css``, de-duplicated, in order."""
    items, seen = [], set()
    for node in root.css(css):
        text = clean(node_text(node))
        if text and text not in seen:
            seen.add(text)
            items.append(text)
    return items


def labelled_sections(root, container_css, section_css='.a-section'):
    """Heading/body pairs from a container of headed sections.

    Used for ``#important-information``, whose sections carry the heading a
    food product's ingredients, usage and legal text are filed under.
    """
    container = root.css(container_css)
    if not container:
        return None

    sections = []
    for section in container.css(section_css):
        # Only leaf sections; parents would repeat their children's text.
        if section.css(f'{section_css} {section_css}'):
            continue
        heading = clean(node_text(
            section.css('h1, h2, h3, h4, h5, .a-text-bold')[:1]))
        lines = node_lines(section)
        if heading and lines and clean(lines[0]) == heading:
            lines = lines[1:]
        body = clean(' '.join(lines))
        if body:
            sections.append({'heading': heading, 'text': body})
    return sections


def expander_sections(root, container_css):
    """Heading/body pairs from Amazon's collapsible ``a-expander`` sections.

    The bodies are present in the HTML even though they render collapsed, so
    no interaction or extra request is needed to read them.
    """
    container = root.css(container_css)
    if not container:
        return None
    sections = []
    for expander in container.css('.a-expander-container'):
        heading = clean(node_text(expander.css('.a-expander-prompt')[:1]))
        body = clean(node_text(expander.css('.a-expander-content')[:1]))
        if heading or body:
            sections.append({'heading': heading, 'text': body})
    return sections


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------

# Amazon ships the gallery as a JS literal, in two shapes:
#   'colorImages': { 'initial': A.$.parseJSON('[{...}]')   (current on .de)
#   'colorImages': { 'initial': [{...}]                    (older / other)
_COLOR_IMAGES_PARSEJSON = re.compile(
    r"['\"]colorImages['\"]\s*:\s*\{\s*['\"]initial['\"]\s*:\s*"
    r"A\.\$\.parseJSON\(\s*'")
_COLOR_IMAGES_LITERAL = re.compile(
    r"['\"]colorImages['\"]\s*:\s*\{\s*['\"]initial['\"]\s*:\s*(\[)")
# An unescaped ')' closing the parseJSON( '...' ) call.
_PARSEJSON_END = re.compile(r"(?<!\\)'\s*\)")


def _decode_js_string(raw):
    """Undo the JS single-quoted string escaping around the image JSON."""
    return raw.replace("\\'", "'").replace('\\"', '"').replace('\\\\', '\\')


def image_records(html):
    """Decode Amazon's ``colorImages.initial`` gallery blob.

    Returns the raw list of image records (hiRes/large/thumb/variant/altText)
    or ``None`` when the blob is not on the page at all.
    """
    match = _COLOR_IMAGES_PARSEJSON.search(html)
    if match:
        start = match.end()
        # The JSON may legitimately contain "\')", so try each candidate
        # terminator until one parses.
        for end in _PARSEJSON_END.finditer(html, start, start + 400_000):
            try:
                return json.loads(_decode_js_string(html[start:end.start()]))
            except ValueError:
                continue
        return None

    match = _COLOR_IMAGES_LITERAL.search(html)
    if not match:
        return None
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(html, match.start(1))
    except ValueError:
        return None
    return value if isinstance(value, list) else None


# Lazy-loaded modules point src at a 1x1 placeholder until scripts run.
_PLACEHOLDER_RE = re.compile(r'grey-pixel|transparent-pixel|loading-|\.gif($|\?)')


def _is_placeholder(url):
    return not url or bool(_PLACEHOLDER_RE.search(url))


def best_image_url(record):
    """Highest-resolution URL available in one gallery record."""
    for key in ('hiRes', 'large'):
        url = record.get(key)
        if url:
            return url
    main = record.get('main')
    if isinstance(main, dict) and main:
        # main maps url -> [width, height]; take the widest.
        return max(main.items(), key=lambda kv: (kv[1] or [0])[0])[0]
    return record.get('thumb') or ''


def dynamic_image_urls(root):
    """Fallback gallery: the ``data-a-dynamic-image`` map on the main image."""
    urls = []
    for node in root.css('#landingImage, #imgBlkFront, img[data-a-dynamic-image]'):
        blob = node.attrib.get('data-a-dynamic-image')
        if not blob:
            continue
        try:
            sizes = json.loads(blob)
        except ValueError:
            continue
        if isinstance(sizes, dict) and sizes:
            urls.append(max(sizes.items(), key=lambda kv: (kv[1] or [0])[0])[0])
    return urls


def aplus_content(root):
    """A+ / Enhanced Brand Content, if the page has any.

    A+ modules embed their own ``<style>`` and ``<script>``; ``node_text``
    drops those, which is the difference between ~1 kB of product copy and
    ~38 kB of stylesheet.
    """
    modules = root.css('#aplus, #aplus_feature_div, #aplusBrandStory_feature_div,'
                       '#aplus3p_feature_div')
    if not modules:
        return None

    module_types, headings, images, tables = [], [], [], []
    seen_images, seen_headings = set(), set()

    for node in modules.css('.aplus-module, .apm-brand-story-card'):
        for css_class in (node.attrib.get('class') or '').split():
            if css_class.startswith(('premium-module-', 'aplus-module-',
                                     'brand-story-', 'apm-')) \
                    and css_class not in module_types:
                module_types.append(css_class)

    for node in modules.css('h1, h2, h3, h4, .aplus-h1, .aplus-h2, .aplus-h3'):
        heading = clean(node_text(node))
        if heading and heading not in seen_headings and len(heading) < 200:
            seen_headings.add(heading)
            headings.append(heading)

    for img in modules.css('img'):
        url = img.attrib.get('data-src') or img.attrib.get('src') or ''
        if _is_placeholder(url) or url in seen_images:
            continue
        seen_images.add(url)
        images.append({'url': url, 'alt': clean(img.attrib.get('alt') or '')})

    for table in modules.css('table'):
        rows = []
        for row in table.css('tr'):
            cells = [clean(node_text(cell)) for cell in row.xpath('./th | ./td')]
            if any(cells):
                rows.append(cells)
        if len(rows) > 1:
            tables.append(rows)

    text = clean(' '.join(node_lines(modules)))
    return {
        'module_types': module_types,
        'headings': headings,
        'text': text,
        'text_length': len(text),
        'images': images,
        'tables': tables,
    }
