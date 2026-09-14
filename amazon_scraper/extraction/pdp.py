"""Compose one rich product record from an Amazon product detail page.

The extractor is deliberately layered:

* :mod:`.blocks` finds *structures* (tables, bullet lists, the image blob);
* :mod:`.marketplaces` maps the locale's *labels* onto canonical keys;
* this module decides which structure answers which question, and records
  where every answer came from.

Every block is run through :meth:`_BlockLog.run`, so a section that Amazon did
not publish is reported as absent while a section that raised is reported as
an error. Neither can lose the rest of the record.
"""

import datetime as _dt
import re

from . import blocks
from .marketplaces import UNITS, VOLUME_UNITS
from .text import clean, decode_entities, first_text, node_text, parse_quantity

SCHEMA_VERSION = 2

# Free-text nutrition is only trustworthy when a per-100 basis is stated
# nearby; otherwise the number may be per serving or per pack.
_BASIS_RE = re.compile(r'(?:pro|per|/)\s*100\s*(?:g|ml|gramm)|100\s*g\b', re.I)
_ENERGY_UNIT_RE = re.compile(r'(kcal|kj)', re.I)
_KJ_PER_KCAL = 4.184


class _BlockLog:
    """Tracks which PDP blocks were present, absent or raised."""

    def __init__(self):
        self.present = []
        self.absent = []
        self.errors = []

    def run(self, name, func, default=None):
        try:
            value = func()
        except Exception as exc:  # one bad section must not lose the record
            self.errors.append({'block': name, 'error': f'{type(exc).__name__}: {exc}'})
            return default
        if value in (None, '', [], {}):
            self.absent.append(name)
            return default if value is None else value
        self.present.append(name)
        return value

    def as_dict(self):
        return {
            'blocks_present': self.present,
            'blocks_absent': self.absent,
            'errors': self.errors,
        }


class PdpExtractor:
    """Extracts a structured record from a PDP for one marketplace."""

    def __init__(self, marketplace):
        self.mp = marketplace

    # -- public API -------------------------------------------------------

    def extract(self, selector, html, lineage=None):
        log = _BlockLog()
        sel, mp = selector, self.mp

        title = clean(first_text(sel, '#productTitle', '#title'))

        raw_tables, sources = log.run(
            'raw_tables', lambda: self._raw_tables(sel), ({}, {})) or ({}, {})
        attributes = self._canonical_attributes(raw_tables)

        important = log.run(
            'important_information',
            lambda: blocks.labelled_sections(sel, '#important-information'), [])
        feature_bullets = log.run(
            'feature_bullets',
            lambda: blocks.bullet_list(sel, '#feature-bullets ul li span.a-list-item'),
            [])
        description = log.run(
            'description',
            lambda: clean(node_text(sel.css('#productDescription'))), '')
        aplus = log.run('aplus', lambda: blocks.aplus_content(sel))

        ingredients = log.run(
            'ingredients',
            lambda: self._ingredients(sel, important, attributes, raw_tables))
        nutrition = log.run(
            'nutrition',
            lambda: self._nutrition(sel, description, aplus, important,
                                    feature_bullets, raw_tables))
        media = log.run('media', lambda: self._media(sel, html), {})
        package = log.run(
            'package', lambda: self._package(attributes, title), {})

        record = {
            'schema_version': SCHEMA_VERSION,
            'fetched_at': _dt.datetime.now(_dt.timezone.utc)
                             .replace(microsecond=0).isoformat(),
        }
        record.update(lineage or {})
        record.update({
            'title': title,
            'brand': log.run('brand', lambda: self._brand(sel, attributes), ''),
            'byline_text': clean(first_text(sel, '#bylineInfo')),
            'brand_url': clean(sel.css('#bylineInfo::attr(href)').get() or ''),
            'price': log.run('price', lambda: self._price(sel), {}),
            'unit_price': log.run('unit_price', lambda: self._unit_price(sel), {}),
            'rating': log.run('rating', lambda: self._rating(sel), {}),
            'availability': clean(first_text(
                sel, '#availability span', '#availability')),
            'seller': clean(first_text(
                sel, '#sellerProfileTriggerId', '#merchant-info a', '#merchant-info')),
            'breadcrumbs': log.run('breadcrumbs', lambda: blocks.bullet_list(
                sel, '#wayfinding-breadcrumbs_feature_div ul li a'), []),
            'package': package,
            'content': {
                'feature_bullets': feature_bullets,
                'description': description,
                'important_information': important or [],
                'aplus': aplus or {},
            },
            'food': {
                'ingredients': ingredients or {},
                'allergens': log.run(
                    'allergens',
                    lambda: self._allergens(sel, attributes), []),
                'nutrition': nutrition or {},
            },
            'attributes': attributes,
            'raw_tables': raw_tables,
            'attribute_sources': sources,
            'media': media,
            'extraction': log.as_dict(),
        })
        return record

    # -- key/value attributes ---------------------------------------------

    def _raw_tables(self, sel):
        """Merged label -> value map plus a label -> source-block map.

        Both structures are kept verbatim: unmapped labels are exactly the
        ones a later normalisation layer will want to mine.
        """
        raw, sources = {}, {}
        for source, pairs in (('table', blocks.key_value_tables(sel)),
                              ('detail_bullets', blocks.key_value_bullets(sel))):
            for label, value in pairs:
                if label not in raw:
                    raw[label] = value
                    sources[label] = source
        return raw, sources

    def _canonical_attributes(self, raw_tables):
        canonical = {}
        for label, value in raw_tables.items():
            key = self.mp.attribute_key(label)
            if key and key not in canonical:
                canonical[key] = value
        return canonical

    # -- core fields ------------------------------------------------------

    def _brand(self, sel, attributes):
        byline = clean(first_text(sel, '#bylineInfo'))
        brand = self.mp.clean_byline(byline)
        # The byline is a store link ("Besuche den X-Store") as often as a
        # brand name; the attribute table is the authoritative source.
        return attributes.get('brand') or brand

    # Price is only read from a known price container. An unscoped
    # ".a-price" also matches related-product carousels and other-seller
    # rows, so a page without a buy box would report a neighbouring
    # product's price -- a wrong number is worse than a missing one.
    PRICE_CONTAINERS = (
        '#corePriceDisplay_desktop_feature_div',
        '#corePrice_feature_div',
        '#corePrice_desktop',
        '#apex_desktop',
        '#price_inside_buybox',
        '#newBuyBoxPrice',
    )

    def _price(self, sel):
        text = decode_entities(clean(first_text(
            sel, '#apex-pricetopay-accessibility-label')))
        if not self._has_decimal(text):
            text = self._price_from_containers(sel) or text
        if not text:
            return {}
        return {
            'amount': self.mp.number(text),
            'currency': self._currency(text),
            'text': self._trim_price(text),
        }

    def _price_from_containers(self, sel):
        """First usable price inside a real price container."""
        for css in self.PRICE_CONTAINERS:
            for container in sel.css(css):
                offscreen = decode_entities(clean(
                    first_text(container, '.a-offscreen')))
                if self._has_decimal(offscreen):
                    return offscreen
                # amazon.com renders the offscreen label without a decimal
                # separator ("EUR097"); rebuild it from the visible spans,
                # where the separator is its own element.
                whole = clean(first_text(container, 'span.a-price-whole'))
                fraction = clean(first_text(container, 'span.a-price-fraction'))
                if whole and fraction:
                    symbol = clean(first_text(container, 'span.a-price-symbol'))
                    separator = '' if whole[-1] in '.,' else self.mp.decimal_sep
                    return f'{whole}{separator}{fraction} {symbol}'.strip()
                if offscreen:
                    return offscreen
        return ''

    @staticmethod
    def _has_decimal(text):
        return bool(text) and bool(re.search(r'\d[.,]\d', text))

    @staticmethod
    def _trim_price(text):
        """Drop the savings clause Amazon appends to the price label."""
        match = re.match(r'\s*([^\d]{0,3}[\d][\d.,\s]*\s*[^\w\s]{0,3})', text)
        return clean(match.group(1)) if match else text

    def _currency(self, text):
        for symbol, code in (('€', 'EUR'), ('£', 'GBP'), ('$', 'USD')):
            if symbol in text:
                return code
        return self.mp.currency

    def _unit_price(self, sel):
        text = decode_entities(clean(first_text(
            sel,
            '.apex-priceperunit-accessibility-label',
            'span.pricePerUnit',
            '#corePriceDisplay_desktop_feature_div .a-size-mini.a-color-base',
        )))
        if not text:
            return {}
        unit = ''
        match = re.search(r'(?:/|pro|per)\s*(100\s*\w+|\w+)\s*\)?$', text, re.I)
        if match:
            unit = clean(match.group(1)).lower()
        return {'amount': self.mp.number(text), 'unit': unit, 'text': text}

    def _rating(self, sel):
        text = clean(
            sel.css('#acrPopover::attr(title)').get()
            or first_text(sel, '#averageCustomerReviews .a-icon-alt',
                          '#acrPopover .a-size-small'))
        count_text = clean(first_text(
            sel, '#acrCustomerReviewText',
            'div[data-hook=total-review-count]'))
        if not text and not count_text:
            return {}
        return {
            'value': self.mp.number(text) if text else None,
            'count': int(self.mp.number(count_text))
                     if count_text and self.mp.number(count_text) is not None else None,
            'text': text,
            'count_text': count_text,
        }

    # -- package / quantity ------------------------------------------------

    def _quantity(self, text):
        return parse_quantity(text, UNITS, self.mp.decimal_sep)

    def _package(self, attributes, title):
        package = {}
        for key, attr in (('item_weight', 'item_weight'),
                          ('package_weight', 'package_weight'),
                          ('unit_count', 'unit_count'),
                          ('volume', 'volume')):
            raw = attributes.get(attr)
            if not raw:
                continue
            package[f'{key}_text'] = raw
            parsed = self._quantity(raw)
            if parsed:
                amount, unit, base = parsed
                package[f'{key}_amount'] = round(amount, 4)
                package[f'{key}_unit'] = unit
                package[f'{key}_base'] = round(base, 4)

        raw_count = attributes.get('item_count') or ''
        as_quantity = self._quantity(raw_count)
        if as_quantity and 'unit_count_base' not in package:
            # Some vendors file a weight under a count label
            # ("Stückzahl: 500.0 gramm"); the value's shape decides, not
            # the label, so a 500 g pack is never read as 500 pieces.
            amount, unit, base = as_quantity
            package.update({'unit_count_text': raw_count,
                            'unit_count_amount': round(amount, 4),
                            'unit_count_unit': unit,
                            'unit_count_base': round(base, 4)})
        elif not as_quantity:
            count = self.mp.number(raw_count)
            if count is not None and count >= 1:
                package['item_count'] = int(count)
        package['size_name'] = attributes.get('package_size', '')
        package['dimensions'] = attributes.get('dimensions', '')

        total, source = self._total_quantity(package, title)
        if total is not None:
            package['total_quantity_base'] = round(total, 2)
            package['total_quantity_unit'] = (
                'ml' if package.get('item_weight_unit') in VOLUME_UNITS
                or package.get('volume_unit') in VOLUME_UNITS else 'g')
            package['total_quantity_source'] = source
        return package

    def _total_quantity(self, package, title):
        """Total content of the listing, in grams or millilitres.

        Preference order reflects how reliable each source proved to be:
        an explicit unit count, then weight x pack count, then the pack
        weight, then a "6 x 500 g" style multipack phrase in the title.
        """
        if package.get('unit_count_base'):
            return package['unit_count_base'], 'unit_count'
        item, count = package.get('item_weight_base'), package.get('item_count')
        if item and count:
            return item * count, 'item_weight_x_count'
        if package.get('package_weight_base'):
            return package['package_weight_base'], 'package_weight'
        if item:
            return item, 'item_weight'
        match = re.search(r'(\d+)\s*[x×]\s*(\d[\d.,]*\s*(?:g|kg|ml|l)\b)', title or '',
                          re.I)
        if match:
            parsed = self._quantity(f'{match.group(1)} x {match.group(2)}')
            if parsed:
                return parsed[2], 'title_multipack'
        return None, ''

    # -- food --------------------------------------------------------------

    _INGREDIENT_PREFIX_RE = re.compile(
        r'^\s*(zutaten|bestandteile|ingredients|inhaltsstoffe)\s*:', re.I)

    def _ingredients(self, sel, important, attributes, raw_tables=None):
        """Ingredient text, with the structure it came from recorded."""
        text = clean(node_text(sel.css('#nic-ingredients-content')))
        if text:
            return {'text': self._strip_ingredient_prefix(text),
                    'source': 'nutrition_card'}

        for section in important or []:
            if self.mp.is_ingredient_heading(section.get('heading', '')):
                return {'text': self._strip_ingredient_prefix(section['text']),
                        'source': 'important_information'}

        if attributes.get('ingredients'):
            return {'text': self._strip_ingredient_prefix(attributes['ingredients']),
                    'source': 'attributes'}

        # Vendors file ingredient declarations under arbitrary labels
        # ("Servierempfehlung: Zutaten: HARTWEIZENGRIEß, Wasser."); the
        # declaration prefix identifies them regardless of the label.
        for label, value in (raw_tables or {}).items():
            if self._INGREDIENT_PREFIX_RE.match(value or ''):
                return {'text': self._strip_ingredient_prefix(value),
                        'source': f'raw_tables:{label}'}
        return None

    def _strip_ingredient_prefix(self, text):
        return re.sub(r'^\s*(zutaten|bestandteile|ingredients|inhaltsstoffe)\s*:?\s*',
                      '', text, flags=re.I).strip()

    def _allergens(self, sel, attributes):
        found, seen = [], set()
        for node in sel.css('[id^="nic-allergens"]'):
            text = clean(node_text(node))
            if text and text not in seen:
                seen.add(text)
                found.append(text)
        declared = attributes.get('allergen_info')
        if declared and declared not in seen:
            found.append(declared)
        return found

    def _nutrition(self, sel, description, aplus, important, bullets, raw_tables):
        """Nutrition facts, from the structured card if present, else text.

        The structured EU nutrition card is authoritative but uncommon; most
        grocery PDPs state the same numbers in prose. Both are returned in the
        same shape, distinguished by ``source`` and ``confidence`` so the
        downstream layer can weight them.
        """
        table = self._nutrition_table(sel)
        if table:
            return table

        from_attributes = self._nutrition_from_attributes(raw_tables)
        if from_attributes:
            return from_attributes

        candidates = [('description', description)]
        if aplus:
            candidates.append(('aplus', aplus.get('text', '')))
        for section in important or []:
            candidates.append(('important_information', section.get('text', '')))
        candidates.append(('feature_bullets', ' '.join(bullets or [])))
        candidates.append(('raw_tables', ' '.join(
            f'{k}: {v}' for k, v in (raw_tables or {}).items())))

        for source, text in candidates:
            parsed = self._nutrition_from_text(text)
            if parsed:
                parsed['source'] = f'text:{source}'
                return parsed
        return None

    def _nutrition_table(self, sel):
        table = sel.css('#nic-eu-nutrition-facts-table, #nic-nutrition-facts-table,'
                        '#nic-eu-nutrition-facts table')
        if not table:
            return None

        rows, per_100 = [], {}
        for row in table.css('tr'):
            cells = row.xpath('./th | ./td')
            if len(cells) != 2:
                continue
            label = clean(node_text(cells[0]))
            value_text = clean(node_text(cells[1]))
            if not label or not value_text:
                continue
            key = self.mp.nutrient_key(label)
            amount = self.mp.number(value_text)
            unit = self._unit_of(value_text)
            rows.append({'label': label, 'value_text': value_text,
                         'amount': amount, 'unit': unit, 'key': key})
            if key and amount is not None:
                self._store_nutrient(per_100, key, amount, unit)

        if not rows:
            return None
        basis = clean(first_text(
            sel, '#nic-nutrition-summary-serving',
            '#nic-eu-nutrition-facts-typical-values'))
        return self._finish_nutrition(rows, per_100, basis, 'nutrition_card', 'high')

    _NUTRIENT_VALUE_RE = re.compile(r'\d[\d.,]*\s*(kcal|kj|mg|g|gramm|gram)\b', re.I)

    def _nutrition_from_attributes(self, raw_tables):
        """Nutrition filed as ordinary key/value attribute rows.

        Requires at least two nutrient-shaped rows so that a lone "Fett" or
        "Energieeffizienz" label on a non-food product cannot masquerade as a
        nutrition table.
        """
        if not raw_tables:
            return None
        rows, per_100 = [], {}
        for label, value in raw_tables.items():
            if not self._NUTRIENT_VALUE_RE.search(value or ''):
                continue
            key = self.mp.nutrient_key(label)
            if not key:
                continue
            amount = self.mp.number(value)
            if amount is None:
                continue
            unit = self._unit_of(value) or ('kcal' if 'kcal' in label.lower() else '')
            rows.append({'label': label, 'value_text': value, 'amount': amount,
                         'unit': unit, 'key': key})
            self._store_nutrient(per_100, key, amount, unit)

        if len(rows) < 2:
            return None
        basis = ''
        for label, value in raw_tables.items():
            if self.mp.attribute_key(label) == 'serving_size':
                basis = value
                break
        return self._finish_nutrition(rows, per_100, basis, 'attributes', 'medium')

    def _nutrition_from_text(self, text):
        if not text or len(text) < 10:
            return None
        rows, per_100 = [], {}
        for alias, key in self.mp.nutrient_aliases():
            if key in per_100:
                continue
            pattern = re.compile(
                r'%s\b[^0-9<>]{0,24}?(\d[\d.,]*)\s*(kcal|kj|mg|g)\b' % re.escape(alias),
                re.I)
            match = pattern.search(text)
            if not match:
                continue
            window = text[max(0, match.start() - 140):match.end() + 140]
            amount = self.mp.number(match.group(1))
            if amount is None:
                continue
            unit = match.group(2).lower()
            rows.append({'label': alias, 'value_text': match.group(0),
                         'amount': amount, 'unit': unit, 'key': key,
                         'basis_confirmed': bool(_BASIS_RE.search(window))})
            self._store_nutrient(per_100, key, amount, unit)

        if not per_100:
            return None
        confirmed = any(r.get('basis_confirmed') for r in rows)
        basis = '100 g' if confirmed else ''
        return self._finish_nutrition(
            rows, per_100, basis, 'text',
            'medium' if confirmed else 'low')

    def _store_nutrient(self, per_100, key, amount, unit):
        if key == 'energy_kj':
            target = 'energy_kcal' if unit == 'kcal' else 'energy_kj'
            per_100.setdefault(target, amount)
        else:
            per_100.setdefault(key, amount)

    def _finish_nutrition(self, rows, per_100, basis, source, confidence):
        derived = []
        if 'energy_kcal' not in per_100 and 'energy_kj' in per_100:
            per_100['energy_kcal'] = round(per_100['energy_kj'] / _KJ_PER_KCAL, 1)
            derived.append('energy_kcal')
        return {
            'source': source,
            'confidence': confidence,
            'basis_text': basis,
            'per_100g': per_100,
            'rows': rows,
            'derived': derived,
        }

    @staticmethod
    def _unit_of(text):
        match = _ENERGY_UNIT_RE.search(text or '')
        if match:
            return match.group(1).lower()
        match = re.search(r'\d\s*(mg|g|ml)\b', text or '', re.I)
        return match.group(1).lower() if match else ''

    # -- media -------------------------------------------------------------

    def _media(self, sel, html):
        records = blocks.image_records(html)
        images, source = [], ''
        if records:
            source = 'color_images'
            for record in records:
                url = blocks.best_image_url(record)
                if url:
                    images.append({
                        'url': url,
                        'variant': record.get('variant') or '',
                        'alt': clean(record.get('altText') or ''),
                        'thumb': record.get('thumb') or '',
                    })
        if not images:
            urls = blocks.dynamic_image_urls(sel)
            if urls:
                source = 'dynamic_image'
                images = [{'url': u, 'variant': '', 'alt': '', 'thumb': ''}
                          for u in urls]
        if not images:
            return {}
        return {
            'images': images,
            'primary_image': images[0]['url'],
            'image_count': len(images),
            'image_source': source,
        }
