"""Regression tests for the PDP extraction primitives.

These run against small HTML fixtures modelled on the structures observed on
live amazon.de PDPs, so they stay fast and offline. The shapes below (the
``parseJSON`` image blob, the malformed nutrition table, the bidi-marked
detail bullets) are copied from real pages -- they are exactly the cases a
naive parser gets wrong.
"""

import unittest

from parsel import Selector

from amazon_scraper.extraction import PdpExtractor, for_domain
from amazon_scraper.extraction import blocks
from amazon_scraper.extraction.marketplaces import UNITS
from amazon_scraper.extraction.text import (clean, decode_entities, node_text,
                                            parse_number, parse_quantity)

DE = for_domain('www.amazon.de')


class TextPrimitives(unittest.TestCase):

    def test_number_formats_seen_on_one_page(self):
        # A single German PDP mixes all of these.
        self.assertEqual(parse_number('12,9g'), 12.9)
        self.assertEqual(parse_number('3000.0 gramm'), 3000.0)
        self.assertEqual(parse_number('1.234,56 €'), 1234.56)
        self.assertEqual(parse_number('2.500 g'), 2500.0)
        self.assertEqual(parse_number('1,5 kg'), 1.5)
        self.assertIsNone(parse_number('keine Angabe'))

    def test_number_respects_locale(self):
        self.assertEqual(parse_number('1,500', decimal_sep=','), 1.5)
        self.assertEqual(parse_number('1,500', decimal_sep='.'), 1500.0)

    def test_clean_joins_split_inline_spans_without_a_gap(self):
        self.assertEqual(clean('HARTWEIZENGRIEß , Wasser.'),
                         'HARTWEIZENGRIEß, Wasser.')
        self.assertEqual(clean('Kann Spuren von Ei , Soja enthalten'),
                         'Kann Spuren von Ei, Soja enthalten')
        self.assertEqual(clean('DINKEL -VOLLKORNMEHL'), 'DINKEL-VOLLKORNMEHL')
        # but a negative number is not a split compound
        self.assertEqual(clean('haltbar bis -18 Grad'), 'haltbar bis -18 Grad')

    def test_clean_strips_bidi_marks(self):
        self.assertEqual(clean('Marke ‏ : ‎'), 'Marke:')

    def test_decode_entities_only_when_double_escaped(self):
        self.assertEqual(decode_entities('13,56&nbsp;&euro; pro kg'),
                         '13,56 € pro kg')
        self.assertEqual(decode_entities('Barilla & Co'), 'Barilla & Co')

    def test_node_text_ignores_script_and_style(self):
        html = ('<div><style>.x{color:red}</style>Echter Text'
                '<script>var a=1;</script></div>')
        self.assertEqual(node_text(Selector(html).css('div')), 'Echter Text')

    def test_parse_quantity_handles_multipacks(self):
        self.assertEqual(parse_quantity('500 Gramm', UNITS), (500.0, 'g', 500.0))
        self.assertEqual(parse_quantity('1,5 kg', UNITS), (1.5, 'kg', 1500.0))
        self.assertEqual(parse_quantity('6 x 500 g', UNITS), (3000.0, 'g', 3000.0))
        self.assertIsNone(parse_quantity('Paket', UNITS))


class Marketplaces(unittest.TestCase):

    def test_label_mapping(self):
        self.assertEqual(DE.attribute_key('Herkunftsland'), 'country_of_origin')
        self.assertEqual(DE.attribute_key('Anzahl der Artikel'), 'item_count')
        self.assertIsNone(DE.attribute_key('Völlig unbekanntes Feld'))

    def test_nutrient_mapping_prefers_longest_alias(self):
        self.assertEqual(DE.nutrient_key('davon gesättigte Fettsäuren'),
                         'saturated_fat_g')
        self.assertEqual(DE.nutrient_key('Fett'), 'fat_g')
        self.assertEqual(DE.nutrient_key('— Eiweiß'), 'protein_g')

    def test_byline_cleanup(self):
        self.assertEqual(DE.clean_byline('Besuche den Valle del Crati-Store'),
                         'Valle del Crati')
        self.assertEqual(DE.clean_byline('Marke: Naturata'), 'Naturata')

    def test_unknown_marketplace_falls_back_without_raising(self):
        self.assertEqual(for_domain('www.amazon.co.jp').language, 'en')


class ImageBlob(unittest.TestCase):
    """amazon.de wraps the gallery in A.$.parseJSON('...'), not a bare list."""

    PARSEJSON = (
        "'colorImages': { 'initial': A.$.parseJSON('"
        '[{"hiRes":"https://m.media-amazon.com/images/I/61A.jpg",'
        '"thumb":"https://m.media-amazon.com/images/I/31A.jpg",'
        '"variant":"MAIN","altText":null},'
        '{"hiRes":null,"large":"https://m.media-amazon.com/images/I/41B.jpg",'
        '"variant":"PT01","altText":"Nudeln"}]'
        "') },")

    LITERAL = ("'colorImages': { 'initial': "
               '[{"hiRes":"https://example.test/a.jpg","variant":"MAIN"}]},')

    def test_parsejson_variant(self):
        records = blocks.image_records(self.PARSEJSON)
        self.assertEqual(len(records), 2)
        self.assertEqual(blocks.best_image_url(records[0]),
                         'https://m.media-amazon.com/images/I/61A.jpg')
        # hiRes is null on the second record; large is the next best.
        self.assertEqual(blocks.best_image_url(records[1]),
                         'https://m.media-amazon.com/images/I/41B.jpg')

    def test_literal_variant(self):
        records = blocks.image_records(self.LITERAL)
        self.assertEqual(blocks.best_image_url(records[0]),
                         'https://example.test/a.jpg')

    def test_absent_blob_is_none_not_an_error(self):
        self.assertIsNone(blocks.image_records('<html>no gallery here</html>'))


NUTRITION_HTML = """
<div id="nic-eu-nutrition-facts">
  <span id="nic-nutrition-summary-serving">Pro 100g</span>
  <table id="nic-eu-nutrition-facts-table">
    <tr><td><span>Energie</span></td><td><span>1483kJ</span></td>
    <tr><td><span>— </span><span>Fett</span></td><td><span>1,2g</span></td>
    <tr><td><span>— </span><span>Kohlenhydrate</span></td><td><span>71g</span></td>
    <tr><td><span>— </span><span>Ballaststoffe</span></td><td><span>3,5g</span></td>
    <tr><td><span>— </span><span>Protein</span></td><td><span>12g</span></td>
  </table>
</div>
<div id="nic-ingredients-content">
  <span>Zutaten: </span><span>HARTWEIZENGRIEß</span><span>, Wasser.</span>
</div>
"""

TABLE_HTML = """
<div id="productOverview_feature_div"><table class="a-normal a-spacing-micro">
  <tr><td><span>Marke</span></td><td><span>Naturata</span></td></tr>
  <tr><td><span>Artikelgewicht</span></td><td><span>500 Gramm</span></td></tr>
  <tr><td><span>Anzahl der Artikel</span></td><td><span>6</span></td></tr>
  <tr><td><span>Herkunftsland</span></td><td><span>Italien</span></td></tr>
</table></div>
<div id="detailBullets_feature_div"><ul><li><span class="a-list-item">
  <span>Hersteller ‏ : ‎</span><span>Naturata AG</span>
</span></li></ul></div>
"""


class KeyValueTables(unittest.TestCase):
    """amazon.de reaches the same <table> through several of the selectors in
    ``KV_TABLE_CSS``: #prodDetails wraps the tables that the more specific ids
    also match. Each table must be read exactly once, and no table may be lost
    because another one was already read."""

    NESTED_TABLES = """
    <div id="prodDetails">
      <table id="productDetails_techSpec_section_1">
        <tr><th>Marke</th><td>Naturata</td></tr>
        <tr><th>Artikelgewicht</th><td>500 Gramm</td></tr>
      </table>
      <table id="productDetails_detailBullets_sections1">
        <tr><th>ASIN</th><td>B000000001</td></tr>
        <tr><th>Im Angebot von Amazon.de seit</th><td>18. Oktober 2023</td></tr>
      </table>
    </div>
    """

    def test_every_table_is_read_exactly_once(self):
        pairs = blocks.key_value_tables(Selector(self.NESTED_TABLES))
        self.assertEqual(pairs, [
            ('Marke', 'Naturata'),
            ('Artikelgewicht', '500 Gramm'),
            ('ASIN', 'B000000001'),
            ('Im Angebot von Amazon.de seit', '18. Oktober 2023'),
        ])

    def test_result_does_not_depend_on_object_lifetimes(self):
        # Deduplication used to key on id(element). lxml frees an element
        # proxy once nothing refers to it and CPython then reuses the address,
        # so an unrelated table could inherit a seen id and be dropped. Forcing
        # collections between selector builds reproduced that.
        import gc

        expected = blocks.key_value_tables(Selector(self.NESTED_TABLES))
        for _ in range(20):
            selector = Selector(self.NESTED_TABLES)
            gc.collect()
            self.assertEqual(blocks.key_value_tables(selector), expected)


class PdpComposition(unittest.TestCase):

    def extract(self, html):
        return PdpExtractor(DE).extract(Selector(html), html, {'asin': 'B000000001'})

    def test_nutrition_table_and_ingredients(self):
        record = self.extract('<div id="productTitle">Pasta</div>' + NUTRITION_HTML)
        nutrition = record['food']['nutrition']
        self.assertEqual(nutrition['source'], 'nutrition_card')
        self.assertEqual(nutrition['confidence'], 'high')
        self.assertEqual(nutrition['basis_text'], 'Pro 100g')
        self.assertEqual(nutrition['per_100g']['protein_g'], 12.0)
        self.assertEqual(nutrition['per_100g']['fiber_g'], 3.5)
        self.assertEqual(nutrition['per_100g']['energy_kj'], 1483.0)
        # kcal is not published; it is derived and declared as such.
        self.assertIn('energy_kcal', nutrition['derived'])
        self.assertEqual(record['food']['ingredients'],
                         {'text': 'HARTWEIZENGRIEß, Wasser.',
                          'source': 'nutrition_card'})

    def test_raw_tables_keep_unmapped_labels(self):
        record = self.extract('<div id="productTitle">Pasta</div>' + TABLE_HTML)
        self.assertEqual(record['raw_tables']['Marke'], 'Naturata')
        self.assertEqual(record['raw_tables']['Hersteller'], 'Naturata AG')
        self.assertEqual(record['attribute_sources']['Hersteller'], 'detail_bullets')
        self.assertEqual(record['attributes']['country_of_origin'], 'Italien')
        self.assertEqual(record['brand'], 'Naturata')
        # 500 g x 6 items
        self.assertEqual(record['package']['total_quantity_base'], 3000.0)
        self.assertEqual(record['package']['total_quantity_source'],
                         'item_weight_x_count')

    def test_count_label_carrying_a_unit_is_not_a_piece_count(self):
        html = ('<div id="productTitle">Pasta</div>'
                '<table class="a-normal a-spacing-micro">'
                '<tr><td>Artikelgewicht</td><td>500 g</td></tr>'
                '<tr><td>Stückzahl</td><td>500.0 gramm</td></tr></table>')
        package = self.extract(html)['package']
        self.assertEqual(package['total_quantity_base'], 500.0)
        self.assertNotIn('item_count', package)

    def test_price_is_read_only_from_a_price_container(self):
        # A page with no buy box, but carousels full of other products'
        # prices: reporting a neighbour's price would be worse than none.
        html = ('<div id="productTitle">Pasta</div>'
                '<div id="similar"><span class="a-price">'
                '<span class="a-offscreen">EUR097</span></span></div>')
        self.assertEqual(self.extract(html)['price'], {})

    def test_price_rebuilt_when_offscreen_label_loses_the_separator(self):
        html = ('<div id="productTitle">Pasta</div>'
                '<div id="corePrice_feature_div"><span class="a-price">'
                '<span class="a-offscreen">EUR097</span>'
                '<span class="a-price-symbol">EUR</span>'
                '<span class="a-price-whole">0</span>'
                '<span class="a-price-fraction">97</span></span></div>')
        self.assertEqual(self.extract(html)['price']['amount'], 0.97)

    def test_price_uses_offscreen_label_when_it_is_usable(self):
        html = ('<div id="productTitle">Pasta</div>'
                '<div id="corePrice_feature_div"><span class="a-price">'
                '<span class="a-offscreen">3,39 €</span></span></div>')
        price = self.extract(html)['price']
        self.assertEqual(price['amount'], 3.39)
        self.assertEqual(price['currency'], 'EUR')

    def test_empty_page_yields_a_record_not_an_exception(self):
        record = self.extract('<html><body></body></html>')
        self.assertEqual(record['extraction']['errors'], [])
        self.assertIn('media', record['extraction']['blocks_absent'])
        self.assertEqual(record['food']['nutrition'], {})
        self.assertEqual(record['raw_tables'], {})

    def test_nutrition_from_prose_is_marked_lower_confidence(self):
        html = ('<div id="productTitle">Pasta</div><div id="productDescription">'
                'Pro 100 g: Eiweiß 13,5 g, Ballaststoffe 3,1 g.</div>')
        nutrition = self.extract(html)['food']['nutrition']
        self.assertEqual(nutrition['source'], 'text:description')
        self.assertEqual(nutrition['confidence'], 'medium')
        self.assertEqual(nutrition['per_100g']['protein_g'], 13.5)


if __name__ == '__main__':
    unittest.main()
