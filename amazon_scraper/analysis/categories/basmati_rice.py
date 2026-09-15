"""Basmati rice: the third category, and the first with a buyer's side.

The question is "which basmati should I eat every week", and it is a harder
shape than either category before it. Dry pasta is decided by a number on the
page (price per kilogram, once the pack size is believed). Tyre mounting paste
is decided by a property Amazon almost never states. Basmati is decided by
**three things at once** -- is it really basmati, does it taste like basmati,
and is it clean -- which are answered by three *different* kinds of evidence,
only one of which the vendor controls.

What this module knows that the layers beneath it cannot:

**Authenticity has an external standard, and it is checkable.** Basmati is not
a marketing adjective in the EU. Duty-free import is restricted to a named
list of varieties, authenticity certificates are issued against it, and
imports are DNA-tested for variety. The trade's Code of Practice tolerates at
most 7% non-basmati grain in something sold as basmati. So a listing that
names its cultivar is making a claim that *could* be checked against a real
register, and one that does not is asking to be taken on trust. That is a
genuine quality signal and it is rare: see ``CULTIVARS`` below.

**"Named cultivar" is an authenticity signal and not an aroma signal.** These
were conflated in the brief this category was built for. In January 2023 six
varieties were struck off the permitted list precisely because DNA testing
showed they had never been bred for fragrance -- some lack the *BADH2* gene
that produces 2-acetyl-1-pyrroline, the compound basmati smells of. A cultivar
name therefore establishes *what it is*, and says much less than expected
about *what it tastes like*. Both are tracked, separately.

**Processing type is a health axis here, not only a taste one.** The brief
excluded parboiled/Sella and brown rice on grounds of taste and tradition.
Independent German laboratory testing puts the same exclusion on a firmer
footing: arsenic concentrates in the bran, so brown rice carries more of it
than white from the same paddy, and Öko-Test measured its highest arsenic
values in brown and parboiled rice while finding only traces in basmati. The
brief's instinct was right; the reason it gave was not the strongest one
available. Both processing type and its arsenic consequence are surfaced.

**Bio is not a health claim, and this module refuses to treat it as one.**
Inorganic arsenic is geogenic -- it comes out of the soil and the irrigation
water, not out of a spray can -- so organic certification does not predict it.
The measured case is unambiguous and it is in ``tests.py``'s fixtures: a
fair-trade organic basmati failed Öko-Test outright on mineral oil and MOAH,
and DNA analysis put 20% foreign varieties in the bag. Bio and Fairtrade are
recorded as what they are -- statements about farming method and trade terms --
and are never allowed to stand in for a contaminant measurement.

Scoring is the one place this module departs from the platform's usual rule,
and it does so deliberately and visibly. See :func:`score`.
"""

import re

from amazon_scraper.validation import (CategoryProfile, DISPUTED, NOT_CLAIMED,
                                       TRUSTED, UNKNOWN, UNVERIFIED, Evidence,
                                       Value, validate)

from .. import category as cat

KEY = 'basmati_rice'

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Groceries are well filed on Amazon.de, so breadcrumbs do most of the work --
# but they cannot do all of it, because "Reis" contains jasmine, sushi,
# risotto, paella and pudding rice, and the searches also return rice cookers,
# rice flour and rice cakes from three other departments entirely.
NOT_RICE_BREADCRUMBS = ('fertiggerichte', 'kochboxen', 'haushaltsgeräte',
                        'küchengeräte', 'reiskocher', 'babynahrung')

# The title has to name basmati. A "Langkornreis" that merely sits next to
# basmati in the search results is a different product, and the whole point of
# this exercise is the difference.
#
# No trailing word boundary, and that is not sloppiness. German compounds the
# noun: "Basmatireis" is one word, and `\bbasmati\b` does not match it. The
# first draft had the boundary and silently classified out **AKASH
# Basmatireis 1 x 10 kg** -- one of only two basmatis Stiftung Warentest
# rated "gut" in its 5/2026 test, and the best-value one of the pair. A
# grammatical detail of the marketplace's language removed the single
# best-evidenced product on the shelf from the comparison, which is exactly
# the failure mode a classifier is supposed to be tested against.
BASMATI_RE = re.compile(r'\bbasmati', re.I)

# Product classes the rice searches return that are not a bag of dry rice.
# `reiskocher` is the big one -- a search for "basmati reis 5kg" returns rice
# cookers because the cooker's copy mentions basmati and 5 kg.
NOT_DRY_RICE_RE = re.compile(
    r'reiskocher|rice\s*cooker|dampfgarer|kocher\b'
    r'|express[\s-]?reis|mikrowell|\bbecher\b|schale\b|to\s?go'
    r'|fertig(?:gericht|reis|packung)|ready\s*(?:to\s*eat|meal)|instant'
    r'|reismehl|rice\s*flour|\bmehl\b|gries|grieß'
    r'|reiswaffel|rice\s*cake|cracker|chips|snack|kekse'
    r'|reismilch|rice\s*drink|getr[äa]nk|\bsirup\b|\bessig\b|vinegar'
    r'|reisnudeln|rice\s*noodle|\bpapier\b|paper'
    r'|reisprotein|protein\s*pulver|\bpulver\b'
    r'|katzenstreu|tierfutter|hundefutter'
    r'|kochbuch|\bbuch\b|\bdeko\b|kerze', re.I)

# Sold as rice, but not as a rice you cook a portion of on a weekday: gift
# sets, sample boxes, and blends whose basmati content is unstated.
MIXED_RE = re.compile(
    r'\bmischung\b|\bmix\b|\bblend\b|probierset|geschenkset|\bset\b'
    r'|sortiment|variety\s*pack|\bw[üu]rz|seasoned|gew[üu]rzt'
    r'|risotto|paella|sushi|milchreis|pudding', re.I)


# An ingredient declaration that names water, oil or salt is describing a
# cooked dish. Dry rice declares rice and nothing else -- across 243 basmati
# records the declaration is "Basmati Reis", "Basmatireis 100%" or
# "Extralanger Basmatireis", never more.
COOKED_RE = re.compile(
    r'gekocht|vorgekocht|\bwasser\b|\bwater\b'
    r'|sonnenblumen[öo]l|\b[öo]l\b|\boil\b|\bsalz\b|\bsalt\b',
    re.I)


def classify(record):
    """Is this a bag of dry basmati rice?

    Two gates, in order. The title must name basmati -- an unnamed long-grain
    is a different product however good it is -- and the listing must not be
    one of the many things a rice search returns that are not rice.
    """
    title = record.get('title') or ''
    if not title:
        return Value.unknown('the listing has no title to classify')

    crumbs = [c.lower() for c in (record.get('breadcrumbs') or [])]
    evidence = [Evidence('title', title[:160])]

    for crumb in crumbs:
        if any(bad in crumb for bad in NOT_RICE_BREADCRUMBS):
            return Value('other', TRUSTED, evidence=evidence,
                         notes=[f'filed by Amazon under "{crumb}", which is '
                                f'not dry rice'])

    if not BASMATI_RE.search(title):
        # The ingredient declaration is allowed to rescue a title that does
        # not say the word -- some vendors title by brand alone.
        declared = ((record.get('food') or {}).get('ingredients') or {}).get('text') or ''
        if not BASMATI_RE.search(declared):
            return Value('other', TRUSTED, evidence=evidence,
                         notes=['neither the title nor the ingredient '
                                'declaration names basmati'])
        evidence.append(Evidence('food.ingredients', declared[:160]))

    for pattern, why in ((NOT_DRY_RICE_RE, 'the listing is not a bag of dry '
                                           'rice'),
                         (MIXED_RE, 'the listing is a blend, a set or a '
                                    'different rice dish')):
        match = pattern.search(title)
        if match:
            return Value('other', TRUSTED, evidence=evidence,
                         notes=[f'{why}: the title says '
                                f'"{match.group(0)}"'])

    # The ingredient declaration settles what the title leaves open, and it
    # is the only thing that catches a cooked pouch whose title is just
    # "Basmati Reis, 250g". Dry rice declares rice. A declaration naming
    # water and oil is a cooked meal, whatever the title calls it.
    declared = ((record.get('food') or {}).get('ingredients') or {}).get('text') or ''
    cooked = COOKED_RE.search(declared)
    if cooked:
        return Value('other', TRUSTED,
                     evidence=[Evidence('food.ingredients', declared[:160])],
                     notes=[f'the ingredient declaration is a cooked dish, '
                            f'not dry rice: it lists "{cooked.group(0)}"'])

    return Value(KEY, TRUSTED, evidence=evidence)


# ---------------------------------------------------------------------------
# Processing type -- the axis the brief treated as a preference and the
# laboratory evidence treats as a contaminant question.
# ---------------------------------------------------------------------------

GRAIN_TYPES = (
    # Checked in order: a bag can say "Sella" and "white", and Sella wins,
    # because parboiling is what happened to it.
    ('parboiled', r'\bsella\b|\bparboiled\b|\bparboil|vorgekocht|golden\s+sella'
                  r'|\bgedämpft\b|steamed\s+rice'),
    ('brown', r'\bvollkorn|\bnaturreis\b|\bbrown\b|\bbraun(?:er)?\s+reis'
              r'|unpolier|ungeschält|whole\s*grain'),
    ('white', r'\bwei[sß]{1,2}(?:er)?\s*(?:reis)?\b|\bwhite\b|\bpoliert'
              r'|\bgeschält'),
)

# Only the fields in which the listing is talking about *this* product.
#
# This restriction is the whole accuracy of the function, and it was measured
# rather than assumed. Searching every text field marked **53 of 243** records
# parboiled, of which **29 were wrong**, in four distinct ways:
#
#   * cross-sell copy -- Tilda's own bullet reads "Neben unseren PURE BASMATI
#     Reis haben wir auch bereits vorgekochte ... Steamed Coconut & Chili",
#     which is a sentence about a different product in the range, and it
#     marked Tilda Pure Original -- the Stiftung Warentest winner -- as
#     parboiled;
#   * A+ comparison tables, which list a brand's whole shelf, sella lines
#     included, inside the page of one non-sella product;
#   * recipe suggestions: "can be used for Biryani, Pulao, Steamed Rice";
#   * outright negation: DIBA's bullet says "Non-parboiled for authentic
#     basmati" and was read as a parboiled declaration.
#
# The title, the ingredient declaration and the vendor's own attribute rows
# are the three places that describe the contents of this bag and nothing
# else. The cost is real and is the right way round: a rice that admits to
# being sella only in its description is read as white and marked
# `unverified`, which is a visible gap rather than a confident error.
GRAIN_FIELDS = ('title', 'food.ingredients', 'raw_tables')

#: "Non-parboiled", "nicht parboiled", "ohne Sella". Checked on the matched
#: quote, because a negated claim is the opposite of the claim.
NEGATION_RE = re.compile(r'\b(?:non|nicht|kein[e]?|ohne|no|free\s+of|frei\s+von)'
                         r'[\s-]{0,2}$', re.I)


def grain_type(validated):
    """White, brown, parboiled/Sella -- or white by default, and said so.

    The default matters and is stated rather than hidden: an ordinary bag of
    basmati that says nothing is milled white rice, because that is what
    basmati is sold as unless a vendor troubles to say otherwise. Recording
    it as `unverified` keeps the difference between "the page says white" and
    "the page says nothing and white is the safe reading".
    """
    for key, pattern in GRAIN_TYPES:
        hits = [hit for hit in validated.search(pattern, limit=3,
                                                fields=GRAIN_FIELDS)
                if not _negated(hit.quote, pattern)]
        if hits:
            return Value(key, TRUSTED, source='text', evidence=hits[:1])
    return Value('white', UNVERIFIED,
                 notes=['the page does not state the milling degree; plain '
                        'basmati is sold white, so that is the reading, but '
                        'nothing on the page confirms it'])


def _negated(quote, pattern):
    """True when the words immediately before the match negate it."""
    match = re.search(pattern, quote, re.I)
    if not match:
        return False
    return bool(NEGATION_RE.search(quote[:match.start()]))


# ---------------------------------------------------------------------------
# Cultivars. Not a vocabulary of nice words -- a register.
# ---------------------------------------------------------------------------

# Varieties admitted to the EU's duty concession for basmati, against which
# authenticity certificates are issued and imports DNA-tested. A listing that
# names one of these is making a claim with an external referent. Everything
# else a vendor might print ("Premium", "Super Kernel Extra Long") is a
# description of a grade, not of a variety.
#
# `super_kernel` is the honest borderline: it is how Pakistani mills sell
# Super Basmati, which *is* on the list, but the phrase itself is a grade
# name. It is recognised and marked as trade-grade rather than variety.
#
# Order is load-bearing and longest-match-first, for the same reason the
# nutrient aliases in `extraction/marketplaces.py` are: "Super Kernel Basmati"
# contains "Kernel", and `kernel` is on the EU register while the trade grade
# is not. Checked in the wrong order, every Pakistani mill's grade name is
# reported as a registered variety, which is precisely the overstatement this
# table exists to prevent.
CULTIVARS = (
    ('super_kernel', r'super\s*kernel', 'Super Kernel (Pakistani trade grade '
                                        'for Super Basmati)', False),
    ('taraori', r'taraori|\bhbc[\s-]?19\b', 'Taraori Basmati (HBC-19)', True),
    ('dehradun', r'dehra\s?dun|\btype[\s-]?3\b', 'Type-3 (Dehradun)', True),
    ('basmati_370', r'basmati\s*370', 'Basmati 370', True),
    ('basmati_386', r'basmati\s*386', 'Basmati 386', True),
    ('basmati_217', r'basmati\s*217', 'Basmati 217', True),
    ('ranbir', r'ranbir', 'Ranbir Basmati', True),
    ('super_basmati', r'super\s*basmati', 'Super Basmati', True),
    ('pusa', r'\bpusa\b', 'Pusa Basmati', True),
    ('pusa_1121', r'\b1121\b', 'Pusa Basmati 1121', True),
    ('kernel', r'\bkernel\b(?!\s*extra)', 'Kernel (Basmati)', True),
)

def cultivar(validated):
    """The variety named, if one is, and whether it is on the EU register."""
    for key, pattern, label, registered in CULTIVARS:
        hits = validated.search(pattern, limit=1)
        if not hits:
            continue
        value = Value(label, UNVERIFIED, source='text', evidence=hits)
        if registered:
            value.notes.append(
                'a variety on the EU list admitted to the basmati duty '
                'concession, so the name refers to something checkable — but '
                'the page is still the only thing saying the bag contains it')
        else:
            value.notes.append(
                'a mill\'s trade grade rather than a registered variety name')
        value.flags.add('registered_cultivar' if registered else 'trade_grade')
        return value
    return Value(None, NOT_CLAIMED,
                 notes=['no variety named. Most basmati on Amazon.de names '
                        'none, so this is the norm rather than a red flag — '
                        'but it is the difference between a checkable claim '
                        'and a word on a bag'])


# ---------------------------------------------------------------------------
# Claims in the vendor's own words
# ---------------------------------------------------------------------------

CLAIMS = (
    cat.Claim(
        'pure_basmati', '100% / pure basmati',
        r'100\s*%\s*basmati|reiner?\s+basmati|pure\s+basmati|sortenrein'
        r'|100\s*%\s*reiner|single\s+variety|nur\s+basmati',
        why='the trade Code of Practice tolerates up to 7% non-basmati grain '
            'in a bag sold as basmati, so "100%" is a claim about something '
            'real — an independent DNA test once found 20% foreign varieties '
            'in a premium organic brand'),
    cat.Claim(
        'aged', 'Aged / naturally matured',
        r'\bgereift\b|\bgealtert\b|abgelagert|\breifung\b|\balterung\b'
        r'|naturally\s+aged|\baged\b|matured|lagerung\s+von',
        why='ageing lowers the moisture of the grain, which is what makes it '
            'elongate instead of swelling and stops it clumping'),
    cat.Claim(
        'extra_long', 'Extra-long / slender grain',
        r'extra[\s-]?lang|extralang|extra[\s-]?long|besonders\s+lang'
        r'|langkörnig|schlanke?\s+körner|slender\s+grain|\blangkorn',
        why='grain length is the one physical property of basmati a buyer can '
            'check on arrival'),
    cat.Claim(
        'himalaya_origin', 'Named growing region',
        r'himalaya|\bpunjab\b|haryana|\bterai\b|uttarakhand|dehra\s?dun'
        r'|vorgebirge|foothills|\bsindh\b|kalar',
        why='basmati is a geographically restricted crop; a named region is '
            'a stronger origin statement than a country'),
    cat.Claim(
        'organic', 'Organic / Bio',
        r'\bbio\b|\börtlich\b(?!)|organic|öko[\s-]?kontroll|de-öko-\d+'
        r'|\bdemeter\b|naturland|bioland|eg-öko|eu-öko',
        why='a statement about farming method. Not a contaminant measurement: '
            'inorganic arsenic comes from soil and irrigation water and is '
            'unaffected by it'),
    cat.Claim(
        'fairtrade', 'Fairtrade / named supply chain',
        r'fairtrade|fair\s*trade|fair\s*gehandelt|direkthandel'
        r'|direct\s*trade|kleinbauern|smallholder',
        why='a statement about trade terms, and often about traceability — '
            'which is useful, but is not a quality or safety measurement'),
    cat.Claim(
        'lab_tested', 'Laboratory testing claimed',
        r'laborgeprüft|labor\s*geprüft|im\s+labor\s+(?:geprüft|getestet)'
        r'|schadstoffgeprüft|auf\s+(?:schadstoffe|rückstände|pestizide)\s+'
        r'(?:geprüft|getestet|untersucht)|rückstandskontroll'
        r'|lab(?:oratory)?\s*tested|pesticide\s*tested'
        r'|qualitätskontrolle\s+in|\bhaccp\b|\bifs\b\s*food|\bbrc\b',
        why='the only claim on the page that speaks to what the brief calls '
            'health evidence. Hunted for specifically because it is the one '
            'that turned out to be almost never made'),
    cat.Claim(
        'arsenic_tested', 'Arsenic or heavy metals specifically addressed',
        r'arsen\b|arsenic|schwermetall|heavy\s*metal|\bcadmium\b|\bblei\b',
        why='the contaminant that actually decides whether a rice is a good '
            'one to eat several times a week'),
    # --- adverse -------------------------------------------------------
    cat.Claim(
        'is_broken', 'Broken rice',
        r'\bbruchreis\b|\bbroken\s+rice\b', adverse=True,
        why='broken grain cooks unevenly and will not elongate; it is a '
            'different product at a different price'),
    cat.Claim(
        'is_flavoured', 'Flavoured or pre-seasoned',
        r'gew[üu]rzt|\bw[üu]rzmischung|seasoned|flavou?red|mit\s+kr[äa]utern',
        adverse=True,
        why='the brief wants a plain rice; a seasoned one cannot be judged '
            'on the same axes'),
)


# ---------------------------------------------------------------------------
# What buyers said. A different kind of evidence, and weaker in a specific way.
# ---------------------------------------------------------------------------

#: ``(key, label, pattern)``. Positive signals are searched in favourable
#: reviews and negative ones in critical reviews, because a five-star review
#: saying "no broken grains at all" must not register as a broken-grain
#: complaint -- which is exactly what an unrestricted search does.
POSITIVE_SIGNALS = (
    ('aroma', 'strong characteristic aroma',
     r'\bduft|duftet|aromatisch|\baroma\b|riecht\s+(?:gut|herrlich|toll|lecker)'
     r'|fragrant|smells?\s+(?:great|wonderful|amazing)|wohlgeruch|profumat'),
    # Kept apart from `aroma` deliberately. Buyers praising a basmati
    # overwhelmingly write "schmeckt gut", not "duftet" -- on the
    # Stiftung-Warentest-winning Tilda listing, eight of nine reviews praise
    # the rice and not one uses an aroma word. Folding the two together would
    # have let generic approval be reported as "buyers confirm the aroma",
    # which is a claim about the one property that distinguishes basmati from
    # any other long grain, and they did not make it.
    ('taste_praise', 'praised for flavour generally',
     r'schmeckt\s+(?:sehr\s+)?(?:gut|lecker|köstlich|hervorragend|super|prima)'
     r'|sehr\s+lecker|köstlich|geschmacklich|guter?\s+geschmack'
     r'|im\s+geschmack\s+(?:sehr\s+)?gut|beste[rn]?\s+reis'
     r'|delicious|tastes?\s+(?:great|good|amazing)|best\s+rice'),
    ('elongates', 'grain visibly elongates',
     r'wird\s+(?:schön\s+)?lang|werden\s+lang|lange\s+körner|langes?\s+korn'
     r'|elongat|l[äa]ngen\s+sich|extra\s+lang'),
    ('fluffy', 'stays separate and fluffy',
     r'körnig|locker|rieselig|klebt\s+nicht|nicht\s+(?:zusammen)?(?:ge)?kleb'
     r'|fluffy|separate\s+grains|nicht\s+matschig|nicht\s+pappig'),
    ('consistent', 'consistent between orders',
     r'immer\s+wieder|schon\s+(?:oft|mehrfach|mehrmals)|seit\s+jahren'
     r'|jedes\s+mal|gleichbleibend|stets\s+gut|nachbestell|wieder\s+bestell'),
)

NEGATIVE_SIGNALS = (
    ('no_aroma', 'no or weak aroma',
     r'kein(?:en)?\s+(?:duft|aroma|geruch)|riecht\s+nach\s+nichts|geruchlos'
     r'|kaum\s+(?:duft|aroma)|ohne\s+(?:duft|aroma)|nicht\s+aromatisch'
     r'|no\s+(?:smell|aroma|fragrance)|wie\s+(?:normaler\s+)?langkornreis'
     r'|schmeckt\s+nach\s+nichts|kein\s+basmati(?:geschmack)?'),
    ('broken_grain', 'too many broken grains',
     r'gebrochen|bruchreis|\bbruch\b|zerbrochen|kaputte?\s+körner'
     r'|broken\s+(?:grain|rice)|viele?\s+bruch'),
    ('sticky', 'clumps or goes mushy',
     r'klebt|klebrig|verkleb|zusammenkleb|matschig|pappig|\bpampe\b|\bbrei\b'
     r'|sticky|mushy|klumpt|verklumpt'),
    ('odd_smell', 'strange or chemical smell',
     r'komischer?\s+geruch|seltsam(?:er)?\s+geruch|muffig|modrig|chemisch'
     r'|riecht\s+(?:komisch|seltsam|streng|schlecht|merkwürdig|nach\s+chemie)'
     r'|gestank|stinkt|unangenehm(?:er)?\s+geruch|strange\s+smell'
     r'|smells?\s+(?:like\s+)?(?:pesticide|chemical|insect|cockroach)'
     r'|pestizid|schaben'),
    ('rancid', 'rancid or stale',
     r'\branzig\b|rancid|\balt(?:er)?\s+geschmack|abgestanden|verdorben'
     r'|schimmel|mould|mold|\bmodrig\b'),
    ('insects', 'insects or larvae',
     r'\bk[äa]fer\b|\bmotten\b|\bmaden\b|\binsekt|\bw[üu]rmer\b|\blarven\b'
     r'|\bmilben\b|ungeziefer|\bweevil|\bbugs?\b|\bmoths?\b|\bworms?\b'),
    ('foreign_matter', 'dust, stones or foreign matter',
     r'\bsteine?\b|\bsteinchen\b|\bstaub\b|staubig|\bdreck|schmutz'
     r'|verunreinig|fremdkörper|\bstroh\b|\bh[üu]lsen\b|\bspelzen\b'
     r'|\bstones?\b|\bgrit\b|\bdirt\b|foreign\s+(?:matter|object)'),
    ('batch_change', 'quality dropped between batches',
     r'(?:qualität|quali)\s+(?:hat\s+)?(?:nachgelassen|nachgelassen|schlechter)'
     r'|früher\s+(?:war\s+.{0,20})?besser|letzte\s+(?:lieferung|charge)'
     r'|andere\s+charge|nicht\s+mehr\s+(?:so\s+)?(?:gut|die\s+gleiche)'
     r'|inzwischen\s+schlechter|quality\s+(?:has\s+)?(?:dropped|declined)'
     r'|not\s+(?:the\s+same|as\s+good)\s+(?:as\s+)?(?:before|anymore)'),
    ('not_as_described', 'not the product described',
     r'nicht\s+wie\s+beschrieben|entspricht\s+nicht|kein\s+echter\s+basmati'
     r'|anderes\s+produkt|falsche[rs]?\s+(?:produkt|reis)|nicht\s+das\s+was'
     r'|not\s+as\s+described|fake|gef[äa]lscht'),
)


def review_signals(validated):
    """What the rendered reviews report, split by what they can support.

    Positive signals are looked for in 4- and 5-star reviews and negative ones
    in 1- and 2-star reviews. Without that split the searches cross-contaminate
    in both directions: "die Körner kleben überhaupt nicht" is a five-star
    review that matches the stickiness pattern, and it is the commonest false
    positive in the whole module.
    """
    found = {}
    for key, label, pattern in POSITIVE_SIGNALS:
        found[key] = validated.review_signal(pattern, label, min_stars=4,
                                             limit=3)
    for key, label, pattern in NEGATIVE_SIGNALS:
        found[key] = validated.review_signal(pattern, label, max_stars=2,
                                             limit=3)
    return found


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

# Dry milled rice, per 100 g, wide enough to hold white and brown basmati and
# every vendor's rounding, narrow enough to catch a per-portion figure filed
# as per-100 g -- which is the error these bands exist to name.
NUTRITION_BANDS = {
    'energy_kcal': (300.0, 400.0),
    'energy_kj': (1250.0, 1700.0),
    'protein_g': (4.5, 12.0),
    'carbohydrates_g': (65.0, 88.0),
    'fat_g': (0.0, 5.0),
    'fiber_g': (0.0, 7.0),
    'sugars_g': (0.0, 3.0),
    'salt_g': (0.0, 0.5),
}

# Amazon.de sells basmati from about €1.80/kg (10 kg diaspora sacks) to about
# €25/kg (250 g organic single-estate). The band is set outside both so that
# it rejects arithmetic, not products: anything under a euro a kilo or over
# forty is a pack-size error, and on this crawl every value it caught was one.
PROFILE = CategoryProfile(key=KEY, label='basmati rice',
                          nutrition_bands=NUTRITION_BANDS,
                          price_band=(1.00, 40.00))

AXES = (
    cat.Axis('price_per_base', 'Price per kg', better='lower',
             comparative='cheaper per kilogram', tolerance=0.05,
             why='rice is bought by weight and eaten weekly, so the kilogram '
                 'is the unit that matters',
             caveat='ranked on, but never alone: the cheapest kilogram in '
                    'this category is reliably the one with the least said '
                    'about it'),
    cat.Axis('review_negative_share', 'Share of 1–2★ ratings', better='lower',
             comparative='less often disappointing', tolerance=1.0,
             why='computed from the complete ratings histogram, so unlike '
                 'anything in the review text it is an actual rate'),
    cat.Axis('review_rating', 'Average rating', better='higher',
             tolerance=0.1,
             caveat='shown because it is asked for; it separates products far '
                    'less than the negative share does'),
    cat.Axis('quantity', 'Pack size',
             caveat='shown, not ranked: a bigger bag is cheaper per kilogram '
                    'and goes stale in a cupboard, and which of those wins is '
                    'the buyer\'s business, not this module\'s'),
)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

#: The seven components, their weights, and why each weight is what it is.
#:
#: This module scores, and the rest of the platform deliberately does not:
#: ``analysis/report.py`` ranks on one axis at a time and says in as many
#: words that a composite "could not answer why A is better than B". That
#: objection is correct and it is the reason for the shape below rather than
#: an argument against having one. Three rules keep it answerable:
#:
#: 1. **Every component is reported, never just the total.** A score of 62 is
#:    published as its seven parts, each with the evidence under it.
#: 2. **No component may be filled in by assumption.** A missing input scores
#:    the *neutral* value for that component, not zero and not full marks, and
#:    the card says how many components were unknown. A product cannot win by
#:    being silent, and it cannot lose for being silent either.
#: 3. **Nothing unverified scores as if it were verified.** A claim that the
#:    vendor makes and nobody checked is worth a fraction of the same claim
#:    with an independent measurement behind it, and the fraction is explicit
#:    in the code below.
#:
#: The weights answer the brief's three questions -- tasty, genuine, sensible
#: to eat often -- with authenticity weighted highest because it is the one
#: that decides whether the other two are even about basmati.
WEIGHTS = {
    'authenticity': 22,   # is it really basmati, and can that be checked
    'taste': 20,          # aroma and texture, mostly from buyers
    'grain': 12,          # milling, breakage, processing type
    'transparency': 14,   # what the seller is willing to state
    'health': 18,         # contaminant evidence, processing, additives
    'consistency': 8,     # does it arrive the same way twice
    'value': 6,           # price per kilogram
}

#: What a score of "we know nothing about this" should be. Not zero: a
#: product nobody has measured is not a bad product.
NEUTRAL_SCORE = 50.0

#: How far an entirely unevidenced score is pulled back toward neutral. At
#: 0.6, a listing with none of the six evidence checks satisfied keeps 40% of
#: its distance from 50, so claims still count for something and cannot carry
#: a product on their own.
SHRINK = 0.6

#: Number of checks :func:`_unknown_components` can report as missing.
EVIDENCE_CHECKS = 7

#: The most an authenticity score built purely from the seller's own text may
#: reach. Vendor claims are `unverified` by the contract's own vocabulary, and
#: this is that word expressed as a number.
CLAIM_CEILING = 0.80

#: Independent laboratory results for products this category meets on the
#: shelf. Kept as *data*, sourced and dated, because it is the only evidence
#: in the whole system that Amazon did not supply -- and because a category
#: module is exactly the right place for "what is known about this product
#: from outside the page".
#:
#: Matching is by brand and product line, deliberately loosely, and a match is
#: reported to the reader with its source so they can disagree with it.
EXTERNAL_TESTS = (
    {'match': r'tilda.*(?:pure|original)|pure\s+original.*basmati',
     'brand': 'Tilda', 'verdict': 'good', 'score': 0.9,
     'source': 'Stiftung Warentest 5/2026 (40 rices, 10 of them basmati)',
     'finding': 'best basmati in the test, "gut" (2.4), singled out for '
                'particularly low contaminant levels'},
    {'match': r'\bakash\b',
     'brand': 'Akash', 'verdict': 'good', 'score': 0.85,
     'source': 'Stiftung Warentest 5/2026',
     'finding': 'rated "gut"; the only other basmati in the test to reach it'},
    {'match': r'\bgepa\b',
     'brand': 'Gepa', 'verdict': 'failed', 'score': 0.0,
     'source': 'Öko-Test, 13 July 2020',
     'finding': '"ungenügend": strongly elevated mineral oil and MOAH, and '
                'DNA analysis found 20% foreign rice varieties against the '
                'Code of Practice limit of 7%'},
)

EXTERNAL_RE = [(re.compile(entry['match'], re.I), entry)
               for entry in EXTERNAL_TESTS]


def external_test(validated):
    """An independent laboratory result for this product, if one is known.

    The title is not enough to claim one, and this is the module's sharpest
    edge. `Tilda Pure Original Basmati Reis, 1er Pack (4 x 2kg)` is filed
    under brand **Kajal**, manufacturer **Kajal GMBH**, with the ingredient
    declaration "Basmatireis tilda" and in a pack size Tilda does not sell.
    It may well be genuine Tilda in a re-boxed carton, and it may not; what
    is certain is that Stiftung Warentest bought and tested a Tilda-branded
    bag, not this one. Matching on the title alone let any seller inherit
    somebody else's laboratory result by typing their product name, which is
    the single easiest way to game a score built on external evidence.

    So the brand or manufacturer field has to agree. When only the title
    matches, the result is reported -- the reader should know the test
    exists -- as `unverified`, and the score treats it as a hint rather than
    a measurement.
    """
    attributes = validated.record.get('attributes') or {}
    identity = f'{validated.brand} {attributes.get("manufacturer") or ""}'
    for pattern, entry in EXTERNAL_RE:
        if not pattern.search(f'{validated.brand} {validated.title}'):
            continue
        if re.search(entry['brand'], identity, re.I):
            return Value(entry['verdict'], TRUSTED, source='published',
                         evidence=[Evidence(entry['source'], entry['finding'])],
                         notes=[f'{entry["source"]}: {entry["finding"]}'])
        return Value(entry['verdict'], UNVERIFIED, source='published',
                     evidence=[Evidence(entry['source'], entry['finding'])],
                     notes=[f'{entry["source"]}: {entry["finding"]} — but this '
                            f'listing names {entry["brand"]} only in its '
                            f'title: it is filed under brand '
                            f'"{validated.brand}" / manufacturer '
                            f'"{attributes.get("manufacturer") or "unstated"}", '
                            f'so the tested bag and this bag are not '
                            f'demonstrably the same'])
    return Value(None, UNKNOWN,
                 notes=['no independent laboratory result is known for this '
                        'product. That is the normal case and is not a mark '
                        'against it'])


def _found(value):
    """True when a claim or signal was actually established."""
    return value is not None and value.value is True and value.status != DISPUTED


def score(validated, found, signals, grain, variety, external):
    """Seven component scores in 0..1, their weighted total, and the gaps.

    Each component returns ``(score, evidence_count)`` where a neutral 0.5 is
    what "nothing known" earns. The total is only meaningful next to
    ``unknown``: a product scoring 61 on two known components is not the same
    product as one scoring 61 on seven, and the card prints both.
    """
    parts = {}

    # -- authenticity: is this really basmati, and who says so --------------
    value = 0.5
    if variety.value and 'registered_cultivar' in variety.flags:
        value = 0.95                       # names a variety on the EU register
    elif variety.value:
        value = 0.75                       # names a mill's trade grade
    if _found(found.get('pure_basmati')):
        value = min(1.0, value + 0.12)
    if _found(found.get('himalaya_origin')):
        value = min(1.0, value + 0.08)
    origin = (validated.record.get('attributes') or {}).get('country_of_origin')
    if origin and re.search(r'indien|india|pakistan', origin, re.I):
        value = min(1.0, value + 0.10)
    elif origin:
        # Basmati is a geographically restricted crop. A declared origin
        # outside the growing region is not fraud -- it is usually the packer's
        # country filed in the origin row -- but it is not evidence of origin.
        value = max(0.0, value - 0.05)
    if external.value == 'failed' and external.status == TRUSTED:
        value = min(value, 0.15)           # a DNA test beats every adjective
    elif external.status != TRUSTED:
        # Everything above this line came out of text the seller wrote. The
        # platform's own vocabulary calls that `unverified`, and a component
        # built entirely of unverified claims must not be able to reach the
        # top of the scale -- otherwise the highest authenticity score in the
        # category goes to whoever writes the most adjectives, which is the
        # opposite of what the component is for. The ceiling is what separates
        # "says all the right things" from "and somebody checked".
        value = min(value, CLAIM_CEILING)
    parts['authenticity'] = value

    # -- taste: aroma and texture, as buyers found them ---------------------
    value, seen = 0.5, 0
    for key, weight in (('aroma', 0.28), ('elongates', 0.12), ('fluffy', 0.12),
                        ('taste_praise', 0.10)):
        if _found(signals.get(key)):
            value += weight
            seen += 1
    for key, weight in (('no_aroma', 0.30), ('sticky', 0.14)):
        if _found(signals.get(key)):
            value -= weight
            seen += 1
    parts['taste'] = max(0.0, min(1.0, value))

    # -- grain quality and processing ---------------------------------------
    value = {'white': 0.85, 'brown': 0.55, 'parboiled': 0.35}.get(
        grain.value, 0.5)
    if grain.status != TRUSTED:
        value = 0.5 + (value - 0.5) * 0.5   # a default is half an observation
    if _found(found.get('extra_long')):
        value = min(1.0, value + 0.08)
    if _found(found.get('aged')):
        value = min(1.0, value + 0.07)
    if _found(found.get('is_broken')):
        value = min(value, 0.1)
    if _found(signals.get('broken_grain')):
        value = max(0.0, value - 0.25)
    if _found(signals.get('foreign_matter')):
        value = max(0.0, value - 0.15)
    parts['grain'] = value

    # -- transparency: what the seller was willing to write down ------------
    # Counted, not judged. Each of these is a fact a buyer can act on, and
    # their absence is the small penalty the brief asks for: between two
    # otherwise equal products, prefer the one you know more about.
    states = [
        bool(origin),
        bool(variety.value),
        bool(((validated.record.get('food') or {}).get('ingredients') or {})
             .get('text')),
        bool((validated.record.get('food') or {}).get('nutrition', {})
             .get('per_100g')),
        _found(found.get('lab_tested')),
        _found(found.get('himalaya_origin')),
        validated.quantity.status == TRUSTED,
    ]
    parts['transparency'] = sum(states) / len(states)

    # -- health and safety --------------------------------------------------
    # The component the brief cares most about and the page answers least.
    # An independent measurement dominates it; everything else is a proxy.
    if external.status == TRUSTED:
        value = 0.05 if external.value == 'failed' else 0.5
        for entry in EXTERNAL_TESTS:
            if entry['verdict'] == external.value:
                value = entry['score']
                break
    elif external.known:
        # The test exists but names a brand this listing only claims in its
        # title. Worth half the distance to what the result would be worth,
        # and no more.
        matched = next((e['score'] for e in EXTERNAL_TESTS
                        if e['verdict'] == external.value), 0.5)
        value = 0.5 + (matched - 0.5) * 0.5
    else:
        # No measurement. Fall back to what is actually predictive of
        # inorganic arsenic, which is milling degree and rice type, not Bio.
        value = {'white': 0.62, 'brown': 0.40, 'parboiled': 0.42}.get(
            grain.value, 0.5)
        if origin and re.search(r'indien|india|pakistan', origin, re.I):
            # Basmati from the subcontinent measures lowest for inorganic
            # arsenic across every survey consulted; that is a real, if
            # population-level, reason for mild confidence.
            value = min(1.0, value + 0.08)
        # A vendor saying it tests is worth something and it is worth very
        # little: the two listings on this crawl that name arsenic both state
        # results no reader can obtain. "Arsen unter der Nachweisgrenze"
        # without a report is a sentence, and the component it feeds is the
        # one where a sentence is least adequate.
        if _found(found.get('lab_tested')):
            value = min(1.0, value + 0.03)
        if _found(found.get('arsenic_tested')):
            value = min(1.0, value + 0.03)
    if _found(signals.get('odd_smell')):
        value = max(0.0, value - 0.20)
    if _found(signals.get('insects')) or _found(signals.get('rancid')):
        value = max(0.0, value - 0.15)
    parts['health'] = value

    # -- consistency between orders -----------------------------------------
    value = 0.5
    negative = validated.review_negative_share
    # `.usable`, not `.known`: the generic layer marks a share computed over
    # fewer than twenty ratings as unverified, and it is right to. A bag with
    # four five-star reviews has a 0% negative share and no track record, and
    # an earlier draft of this function ranked exactly such a product first.
    if negative.usable:
        # 0% -> 1.0, 20% or worse -> 0.0. A complete statistic, so it is
        # allowed to move this component on its own.
        value = max(0.0, min(1.0, 1.0 - negative.value / 20.0))
    if _found(signals.get('consistent')):
        value = min(1.0, value + 0.10)
    if _found(signals.get('batch_change')):
        value = max(0.0, value - 0.25)
    if _found(signals.get('not_as_described')):
        value = max(0.0, value - 0.20)
    # A review set Amazon could not tie to a purchase it processed is weaker
    # evidence of anything. Measured on this crawl: one listing shows seven of
    # its eight rendered reviews unverified, against a set where 271 of 277
    # corpus review cards carry the badge -- so this is an outlier worth
    # discounting, not the norm.
    cards = validated.review_sample.value or []
    if cards:
        unverified = sum(1 for c in cards if not c.get('verified'))
        if unverified > len(cards) / 2:
            value = max(0.0, value - 0.15)
    parts['consistency'] = value

    # -- value for money ----------------------------------------------------
    per_kg = validated.price_per_base
    if per_kg.usable and per_kg.value:
        # €2/kg or less scores full, €12/kg or more scores nothing. Weighted
        # at 6 of 100 on purpose: the brief's whole point is that the cheapest
        # kilogram is not the answer.
        parts['value'] = max(0.0, min(1.0, (12.0 - per_kg.value) / 10.0))
    else:
        parts['value'] = 0.5

    raw = sum(parts[key] * WEIGHTS[key] for key in WEIGHTS)
    unknown = _unknown_components(found, signals, grain, variety, external,
                                  validated)

    # Shrink toward the neutral 50 in proportion to how much had to be
    # guessed. This is the brief's "award no points for marketing language
    # with nothing checkable behind it", implemented rather than promised.
    #
    # It is deliberately a *shrink* and not a penalty: a product nobody has
    # measured moves toward "we do not know", never below it, because absence
    # of data is not an adverse finding. But it stops a listing whose entire
    # case is its own adjectives from outranking one with an independent
    # laboratory result. An earlier draft had no such term, and it ranked
    # first a ten-kilogram bag with five ratings whose feature bullet claimed
    # every heavy metal was under the limit of detection -- a sentence no
    # reader can check, scoring as though it were a test report.
    ignorance = len(unknown) / EVIDENCE_CHECKS
    total = NEUTRAL_SCORE + (raw - NEUTRAL_SCORE) * (1 - SHRINK * ignorance)

    return {'parts': parts, 'weights': dict(WEIGHTS),
            'raw': round(raw, 1), 'total': round(total, 1),
            'evidence': round(1 - ignorance, 2), 'unknown': unknown}


def _unknown_components(found, signals, grain, variety, external, validated):
    """Which inputs the score had to fall back to neutral on."""
    gaps = []
    if not external.known:
        gaps.append('no independent laboratory result')
    if not any(_found(signals.get(k)) for k, _, _ in POSITIVE_SIGNALS) and \
            not any(_found(signals.get(k)) for k, _, _ in NEGATIVE_SIGNALS):
        gaps.append('no usable review signal')
    if variety.value is None:
        gaps.append('no variety named')
    if grain.status != TRUSTED:
        gaps.append('milling degree assumed, not stated')
    if not (validated.record.get('attributes') or {}).get('country_of_origin'):
        gaps.append('no country of origin')
    if not validated.price_per_base.usable:
        gaps.append('no trustworthy price per kg')
    if not validated.review_negative_share.usable:
        count = (validated.record.get('rating') or {}).get('count')
        gaps.append(f'no usable rating track record'
                    f'{f" ({count} ratings)" if count else ""}')
    return gaps


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def claims(validated):
    """Every claim, with the vendor's sentence or an explicit gap."""
    result = {}
    for claim in CLAIMS:
        hits = validated.search(claim.pattern, limit=2, fields=claim.fields)
        if hits:
            result[claim.key] = Value(True, TRUSTED, evidence=hits,
                                      source='text')
        else:
            result[claim.key] = Value(
                False, NOT_CLAIMED,
                notes=[f'{claim.label}: not stated anywhere on the page, '
                       f'which is not the same as being untrue'])
    return result


#: Rice types a basmati's ingredient declaration should never name. The
#: declaration is the legally controlled statement of what is in the bag, so
#: when it disagrees with the title the disagreement is worth surfacing even
#: though this layer cannot say which side is right.
#:
#: Found on a real listing: `INDIA GATE Premium Basmati Reis ... 5 kg`, whose
#: declaration reads "Brauner Langkorn Duftreis" -- brown long-grain aromatic
#: rice -- on a product sold and photographed as white basmati. Most likely a
#: template filled in carelessly rather than the wrong rice in the bag, and
#: that is exactly why it is reported rather than acted on.
DECLARATION_CONFLICT = (
    ('brown', r'braun|vollkorn|naturreis|brown|whole\s*grain'),
    ('parboiled', r'\bsella\b|parboiled|vorgekocht'),
)


def check_declaration(validated, grain):
    """Flag a title and an ingredient declaration that describe different rice."""
    declared = ((validated.record.get('food') or {}).get('ingredients')
                or {}).get('text') or ''
    if not declared:
        return None
    for kind, pattern in DECLARATION_CONFLICT:
        if kind == grain.value or not re.search(pattern, declared, re.I):
            continue
        if re.search(pattern, validated.title or '', re.I):
            continue        # title and declaration agree; nothing to report
        return Value(
            kind, DISPUTED, source='structured',
            evidence=[Evidence('food.ingredients', declared[:160]),
                      Evidence('title', (validated.title or '')[:160])],
            notes=[f'the ingredient declaration describes {kind} rice while '
                   f'the title sells this as {grain.value}. The declaration is '
                   f'the controlled statement of contents, so the two cannot '
                   f'both be right — but a carelessly filled template is the '
                   f'likelier explanation than the wrong rice in the bag'])
    return None


def check_claim_consistency(found, grain):
    """Dispute the claims the rest of the page contradicts."""
    # "100% Basmati" on a bag the vendor also calls a blend, or broken rice.
    pure = found.get('pure_basmati')
    broken = found.get('is_broken')
    if _found(pure) and _found(broken):
        pure.dispute('the same page sells this as 100% basmati and as broken '
                     'rice; broken grain is a milling by-product, so at most '
                     'one of the two statements is about what is in the bag',
                     *broken.evidence[:1])

    # Parboiled is a process, not a variety, and it is not what "natural" or
    # "unprocessed" copy implies.
    if grain.value == 'parboiled' and _found(found.get('aged')):
        found['aged'].dispute(
            'the page claims ageing and also declares the rice parboiled — '
            'parboiling is a steam treatment that substitutes for the effect '
            'ageing has on the grain, so the ageing claim describes something '
            'the process has already done',
            *grain.evidence[:1])


def evaluate(record):
    """One basmati evidence card, or a classification-only card."""
    classification = classify(record)
    validated = validate(record, PROFILE)

    if classification.value != KEY:
        return cat.card(record, validated, CATEGORY, classification,
                        axes={}, claims={})

    found = claims(validated)
    grain = grain_type(validated)
    check_claim_consistency(found, grain)
    variety = cultivar(validated)
    signals = review_signals(validated)
    external = external_test(validated)

    axes = {'price_per_base': validated.price_per_base,
            'review_negative_share': validated.review_negative_share,
            'review_rating': validated.review_rating,
            'quantity': validated.quantity}

    card = cat.card(record, validated, CATEGORY, classification, axes, found)
    card['grain_type'] = grain
    card['declaration_conflict'] = check_declaration(validated, grain)
    card['cultivar'] = variety
    card['review_signals'] = signals
    card['external_test'] = external
    card['score'] = score(validated, found, signals, grain, variety, external)
    return card


def render_extra(card):
    """The sections only this category has: grain, variety, buyers, score."""
    if not cat.is_match(card):
        return []
    lines = ['', '  Grain and variety']
    grain, variety = card['grain_type'], card['cultivar']
    lines.append(f'    type     {grain.value} [{grain.status}]')
    lines.append(f'    variety  {variety.value or "not named"} '
                 f'[{variety.status}]')

    conflict = card.get('declaration_conflict')
    if conflict is not None:
        lines += ['', '  Contradiction on the page',
                  f'    {conflict.notes[0]}']
        for hit in conflict.evidence:
            lines.append(f'      {hit.field}: "{hit.quote[:100]}"')

    external = card['external_test']
    lines += ['', '  Independent testing']
    lines.append(f'    {external.notes[0] if external.notes else "unknown"}')

    signals = card['review_signals']
    reported = [(key, label) for key, label, _ in POSITIVE_SIGNALS
                if _found(signals.get(key))]
    problems = [(key, label) for key, label, _ in NEGATIVE_SIGNALS
                if _found(signals.get(key))]
    lines += ['', '  What buyers reported '
                  '(presence only — the sample cannot show frequency)']
    for key, label in reported:
        lines.append(f'    + {label}')
        for hit in signals[key].evidence[:1]:
            lines.append(f'        {hit.field}: "{hit.quote[:110]}"')
    for key, label in problems:
        lines.append(f'    - {label}')
        for hit in signals[key].evidence[:1]:
            lines.append(f'        {hit.field}: "{hit.quote[:110]}"')
    if not reported and not problems:
        lines.append('    nothing either way in the reviews Amazon rendered')

    detail = card['score']
    lines += ['', f'  Score {detail["total"]:.0f}/100']
    for key in WEIGHTS:
        bar = '█' * round(detail['parts'][key] * 10)
        lines.append(f'    {key:<14} {detail["parts"][key]:.2f} '
                     f'x{WEIGHTS[key]:<3} {bar}')
    if detail['unknown']:
        lines.append(f'    unknown: {"; ".join(detail["unknown"])}')
    return lines


CATEGORY = cat.register(cat.Category(
    key=KEY,
    label='basmati rice',
    profile=PROFILE,
    axes=AXES,
    claims=CLAIMS,
    evaluate=evaluate,
    default_axis='price_per_base',
    render_extra=render_extra,
    blurb='Judged on three things the page answers with three different '
          'kinds of evidence: whether it is really basmati (a register '
          'exists, and almost nobody cites it), whether it tastes like it '
          '(buyers, not vendors), and whether it is clean (almost always '
          'unknown, and never answered by the word Bio).',
))
