"""Marketplace profiles: everything the extractors need that is locale-specific.

The PDP *structure* (element ids, table shapes, the image blob) is shared
across Amazon locations; only the human-readable labels and the number format
differ. Keeping those in one table means adding a marketplace is a data
change, not a parser change.

`amazon.de` is the profile that is validated against live pages. `amazon.com`
is provided as a second profile so the seams are exercised and the design
stays honest, but it has not been validated against live `.com` pages.
"""

import re
from urllib.parse import urlparse

# Canonical attribute keys. Downstream consumers read these; the per-locale
# label lists below are only a lookup into them.
ATTRIBUTE_ALIASES = {
    'brand': {'de': ['marke'], 'en': ['brand', 'brand name']},
    'manufacturer': {'de': ['hersteller'], 'en': ['manufacturer']},
    'country_of_origin': {
        'de': ['herkunftsland', 'ursprungsland', 'herkunftsland des produkts'],
        'en': ['country of origin'],
    },
    'item_weight': {
        'de': ['artikelgewicht', 'nettogewicht', 'gewicht'],
        'en': ['item weight', 'net weight', 'weight'],
    },
    'package_weight': {
        'de': ['paketgewicht', 'verpackungsgewicht'],
        'en': ['package weight'],
    },
    'item_count': {
        'de': ['anzahl der artikel', 'anzahl artikel', 'stückzahl',
               'artikelmenge pro paket', 'anzahl der packungen'],
        'en': ['number of items', 'item count', 'units per package'],
    },
    'unit_count': {
        'de': ['anzahl der einheiten', 'anzahl von einheiten'],
        'en': ['unit count'],
    },
    'package_size': {
        'de': ['paketgröße - name', 'paketgröße', 'größe', 'grösse'],
        'en': ['size name', 'size'],
    },
    'dimensions': {
        'de': ['produktabmessungen', 'verpackungsabmessungen', 'abmessungen'],
        'en': ['product dimensions', 'package dimensions'],
    },
    'volume': {
        'de': ['artikelvolumen', 'nettovolumen des inhalts', 'volumen'],
        'en': ['item volume', 'net content volume'],
    },
    'ingredients': {
        'de': ['zutaten', 'bestandteile', 'inhaltsstoffe'],
        'en': ['ingredients'],
    },
    'allergen_info': {
        'de': ['allergenhinweis', 'allergene'],
        'en': ['allergen information', 'allergens'],
    },
    'flavour': {'de': ['geschmacksrichtung', 'geschmack'], 'en': ['flavour', 'flavor']},
    'form': {'de': ['form'], 'en': ['form']},
    'variety': {'de': ['auswahl', 'sorte', 'spezialität'], 'en': ['variety', 'speciality']},
    'material_feature': {
        'de': ['besondere produkteigenschaften', 'produkt-features', 'eigenschaften'],
        'en': ['specialty', 'product features', 'special feature'],
    },
    'storage': {'de': ['lagerungshinweise', 'aufbewahrung'], 'en': ['storage instructions']},
    'diet_type': {'de': ['ernährungshinweis', 'diät-typ'], 'en': ['diet type']},
    'model_number': {
        'de': ['modellnummer', 'hersteller-modellnummer', 'herstellerreferenz'],
        'en': ['item model number', 'manufacturer reference', 'model number'],
    },
    'gtin': {
        'de': ['global trade identification number'],
        'en': ['global trade identification number', 'upc', 'ean'],
    },
    'best_sellers_rank': {
        'de': ['amazon bestseller-rang'],
        'en': ['best sellers rank', 'amazon best sellers rank'],
    },
    'first_available': {
        'de': ['im angebot von amazon.de seit'],
        'en': ['date first available'],
    },
    'serving_size': {
        'de': ['portionsgröße', 'portionsgrösse', 'serviergröße'],
        'en': ['serving size'],
    },
    'asin': {'de': ['asin'], 'en': ['asin']},
}

# Canonical nutrient keys -> per-locale label fragments, longest first so
# "davon gesättigte Fettsäuren" wins over "Fett".
NUTRIENT_ALIASES = {
    'saturated_fat_g': {
        'de': ['davon gesättigte fettsäuren', 'gesättigte fettsäuren',
               'davon gesättigte'],
        'en': ['of which saturates', 'saturated fat', 'saturates'],
    },
    'sugars_g': {
        'de': ['davon zucker', 'zucker'],
        'en': ['of which sugars', 'total sugars', 'sugars'],
    },
    'fiber_g': {'de': ['ballaststoffe'], 'en': ['fibre', 'dietary fiber', 'fiber']},
    'protein_g': {'de': ['eiweiß', 'eiweiss', 'protein'], 'en': ['protein']},
    'carbohydrates_g': {
        'de': ['kohlenhydrate'],
        'en': ['carbohydrate', 'carbohydrates', 'total carbohydrate'],
    },
    'fat_g': {'de': ['fett'], 'en': ['total fat', 'fat']},
    'salt_g': {'de': ['salz'], 'en': ['salt']},
    'sodium_mg': {'de': ['natrium'], 'en': ['sodium']},
    'energy_kj': {'de': ['brennwert', 'energie'], 'en': ['energy']},
}

# Section headings inside #important-information that carry food data.
IMPORTANT_INFO_INGREDIENT_HEADINGS = {
    'de': ['zutaten', 'bestandteile', 'inhaltsstoffe'],
    'en': ['ingredients'],
}

# "Marke: X" / "Visit the X Store" wrappers around #bylineInfo.
BYLINE_PATTERNS = {
    'de': [r'^marke:\s*', r'^besuche(?:n sie)? den\s*', r'-store$', r'\s*store$'],
    'en': [r'^brand:\s*', r'^visit the\s*', r"'s store$", r'\s*store$'],
}

# --- Review vocabulary -----------------------------------------------------
# The review widget is structurally identical across locales -- the same
# `data-hook` names -- but everything a reader needs from it is a sentence:
# where it was written, whether the purchase was verified, how many people
# found it useful. Those are labels, so they live here with the others.

#: "Bewertet in Deutschland am 6. Juli 2026" -> country, day, month, year.
REVIEW_DATELINE = {
    'de': r'Bewertet in\s+(?P<country>.+?)\s+am\s+(?P<day>\d{1,2})\.?\s*'
          r'(?P<month>[^\s\d]+)\s+(?P<year>\d{4})',
    'en': r'Reviewed in\s+(?P<country>.+?)\s+on\s+(?:(?P<month>[A-Za-z]+)\s+'
          r'(?P<day>\d{1,2}),\s*(?P<year>\d{4})'
          r'|(?P<day2>\d{1,2})\s+(?P<month2>[A-Za-z]+)\s+(?P<year2>\d{4}))',
}

MONTHS = {
    'de': ['januar', 'februar', 'märz', 'april', 'mai', 'juni', 'juli',
           'august', 'september', 'oktober', 'november', 'dezember'],
    'en': ['january', 'february', 'march', 'april', 'may', 'june', 'july',
           'august', 'september', 'october', 'november', 'december'],
}

#: The marketplace's own country, in its own language. A review dateline
#: naming anything else came from the "reviews from other countries" section:
#: a different marketplace's listing, machine-translated.
HOME_COUNTRY = {
    'amazon.de': 'deutschland', 'amazon.com': 'the united states',
    'amazon.co.uk': 'the united kingdom', 'amazon.it': 'italien',
}

VERIFIED_PURCHASE = {
    'de': ['verifizierter kauf'],
    'en': ['verified purchase'],
}

#: "9 Personen fanden dies hilfreich" / "Eine Person fand diese Informationen
#: hilfreich" -- the singular form spells the number out, so a bare \d+ finds
#: nothing and the vote is worth 1, not 0.
HELPFUL_VOTES = {
    'de': (r'(\d[\d.\s\u00a0]*)\s*Personen fanden', r'^Eine Person fand'),
    'en': (r'(\d[\d,\s]*)\s*people found', r'^One person found'),
}

#: "71 Prozent der Bewertungen haben 5 Sterne" on the histogram bar's link.
HISTOGRAM_LABEL = {
    'de': r'(?P<percent>\d+)\s*Prozent der Bewertungen haben\s*(?P<stars>\d)',
    'en': r'(?P<percent>\d+)\s*percent of reviews have\s*(?P<stars>\d)',
}

#: Trailing UI affordances Amazon renders *inside* the review body.
REVIEW_BODY_NOISE = {
    'de': [r'Mehr erfahren', r'Weniger anzeigen', r'Bilder in dieser Rezension',
           r'Missbrauch melden'],
    'en': [r'Read more', r'Show less', r'Images in this review',
           r'Report abuse'],
}

# Mass/volume units, mapped to a canonical symbol and a factor to grams / ml.
UNITS = {
    'g': ('g', 1.0), 'gramm': ('g', 1.0), 'gramme': ('g', 1.0),
    'gram': ('g', 1.0), 'grams': ('g', 1.0), 'gr': ('g', 1.0),
    'kg': ('kg', 1000.0), 'kilogramm': ('kg', 1000.0),
    'kilogram': ('kg', 1000.0), 'kilograms': ('kg', 1000.0),
    'mg': ('mg', 0.001), 'milligramm': ('mg', 0.001),
    'ml': ('ml', 1.0), 'milliliter': ('ml', 1.0), 'millilitre': ('ml', 1.0),
    'l': ('l', 1000.0), 'liter': ('l', 1000.0), 'litre': ('l', 1000.0),
    'liters': ('l', 1000.0), 'litres': ('l', 1000.0),
    'oz': ('oz', 28.3495), 'ounce': ('oz', 28.3495), 'ounces': ('oz', 28.3495),
    'lb': ('lb', 453.592), 'pound': ('lb', 453.592), 'pounds': ('lb', 453.592),
}

VOLUME_UNITS = {'ml', 'l'}


class Marketplace:
    """Locale-specific knowledge for one Amazon location."""

    def __init__(self, host, language, currency, decimal_sep):
        self.host = host
        self.language = language
        self.currency = currency
        self.decimal_sep = decimal_sep
        self._attribute_index = self._build_index(ATTRIBUTE_ALIASES)
        self._nutrient_index = self._build_index(NUTRIENT_ALIASES)
        # Longest-first so specific nutrient labels beat their own prefixes.
        self._nutrient_order = sorted(self._nutrient_index, key=len, reverse=True)
        self._byline_patterns = [
            re.compile(p, re.I) for p in BYLINE_PATTERNS.get(self.language, [])
        ]
        self._ingredient_headings = [
            h for h in IMPORTANT_INFO_INGREDIENT_HEADINGS.get(self.language, [])
        ]

    def _build_index(self, aliases):
        index = {}
        for canonical, by_language in aliases.items():
            for label in by_language.get(self.language, []):
                index[label] = canonical
        return index

    # -- lookups ----------------------------------------------------------

    def word(self, stem):
        """Regex fragment for a non-empty literal stem in this profile's language.

        German permits a compound suffix (``basmati`` matches ``Basmatireis``);
        other languages require a whole word. Both retain the leading boundary
        to reject embedded stems. This opt-in rule does not parse compounds or
        handle negation: callers still apply category exclusions and choose
        regex flags such as ``re.I`` themselves.
        """
        if not stem or not stem.strip():
            raise ValueError('word stem must not be empty')
        return r'\b' + re.escape(stem) + ('' if self.language == 'de' else r'\b')

    @staticmethod
    def _normalise_label(label):
        return re.sub(r'\s+', ' ', (label or '').strip().strip(':').lower())

    def attribute_key(self, label):
        """Canonical key for a raw table label, or None if it is unmapped.

        Unmapped labels are never dropped: the caller keeps them in the raw
        attribute map so a later normalisation layer can still reach them.
        """
        return self._attribute_index.get(self._normalise_label(label))

    def nutrient_key(self, label):
        """Canonical nutrient key for a nutrition-row label, or None."""
        normalised = self._normalise_label(label).lstrip('—- ').strip()
        if normalised in self._nutrient_index:
            return self._nutrient_index[normalised]
        for alias in self._nutrient_order:
            if alias in normalised:
                return self._nutrient_index[alias]
        return None

    def nutrient_aliases(self):
        """(alias, canonical_key) pairs, longest alias first."""
        return [(alias, self._nutrient_index[alias]) for alias in self._nutrient_order]

    def is_ingredient_heading(self, heading):
        normalised = self._normalise_label(heading)
        return any(h in normalised for h in self._ingredient_headings)

    def clean_byline(self, text):
        value = (text or '').strip()
        for pattern in self._byline_patterns:
            value = pattern.sub('', value).strip()
        return value.strip(' :')

    # -- reviews ----------------------------------------------------------

    def review_dateline(self, text):
        """"Bewertet in Italien am 11. Juli 2026" -> (country, ISO date, home?).

        ``home`` is False for the "reviews from other countries" section,
        which Amazon machine-translates onto the page from a *different*
        marketplace's listing. Those reviews are real, but they are not
        evidence about what this marketplace sells, so the caller is told
        which is which rather than having them silently merged.
        """
        pattern = REVIEW_DATELINE.get(self.language)
        match = re.search(pattern, text or '', re.I) if pattern else None
        if not match:
            return '', '', None
        parts = match.groupdict()
        country = (parts.get('country') or '').strip()
        day = parts.get('day') or parts.get('day2')
        month = parts.get('month') or parts.get('month2')
        year = parts.get('year') or parts.get('year2')
        iso = ''
        months = MONTHS.get(self.language, [])
        normalised = (month or '').strip().lower().rstrip('.')
        if normalised in months and day and year:
            iso = f'{int(year):04d}-{months.index(normalised) + 1:02d}-{int(day):02d}'
        home = HOME_COUNTRY.get(self.host)
        return country, iso, (country.lower() == home if home else None)

    def is_verified_purchase(self, text):
        value = (text or '').strip().lower()
        return any(v in value for v in VERIFIED_PURCHASE.get(self.language, []))

    def helpful_votes(self, text):
        """Number of "found this helpful" votes, or None when none is shown."""
        if not text:
            return None
        plural, singular = HELPFUL_VOTES.get(self.language, (None, None))
        if singular and re.search(singular, text.strip(), re.I):
            return 1
        match = re.search(plural, text, re.I) if plural else None
        if not match:
            return None
        digits = re.sub(r'[^\d]', '', match.group(1))
        return int(digits) if digits else None

    def histogram_share(self, label):
        """("5 stars", 71) from a histogram bar's aria-label, or None."""
        pattern = HISTOGRAM_LABEL.get(self.language)
        match = re.search(pattern, label or '', re.I) if pattern else None
        if not match:
            return None
        return int(match.group('stars')), int(match.group('percent'))

    def strip_review_noise(self, text):
        for noise in REVIEW_BODY_NOISE.get(self.language, []):
            text = re.sub(noise, ' ', text, flags=re.I)
        return re.sub(r'\s+', ' ', text).strip()

    def number(self, text):
        from .text import parse_number
        return parse_number(text, self.decimal_sep)


_PROFILES = {
    'amazon.de': Marketplace('amazon.de', 'de', 'EUR', ','),
    'amazon.com': Marketplace('amazon.com', 'en', 'USD', '.'),
    'amazon.co.uk': Marketplace('amazon.co.uk', 'en', 'GBP', '.'),
    'amazon.it': Marketplace('amazon.it', 'de', 'EUR', ','),
}

# Locations we have no profile for still crawl; they fall back to English
# labels and dot-decimals, and every raw structure is preserved regardless.
_FALLBACK = Marketplace('amazon.com', 'en', '', '.')


def domain_key(host):
    """'www.amazon.de' -> 'amazon.de'."""
    host = (host or '').strip().lower().rstrip('/')
    if '://' in host:
        host = urlparse(host).netloc
    return host[4:] if host.startswith('www.') else host


def for_domain(host):
    """Marketplace profile for a host, falling back to a neutral profile."""
    return _PROFILES.get(domain_key(host), _FALLBACK)


def supported_domains():
    return sorted(_PROFILES)
