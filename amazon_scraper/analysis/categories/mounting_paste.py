"""Tyre mounting paste: the second category, and the one that tested the contract.

The use case is specific and it is not a grocery one. A 10-inch pneumatic
scooter tyre with an inner tube has to go onto an aluminium rim by hand, and
three properties decide whether a paste is the right one:

1. **It must dry after mounting and stop lubricating.** A paste that stays
   slippery lets the tyre creep on the rim, which shears the valve off the
   tube. This is the criterion that matters most, and the hardest to read off
   a product page -- 14 of 43 listings state it, and the first version of this
   module found only 3, because it looked for the verb ("trocknet ab") and
   German marketing copy prefers the adjective ("schnelltrocknend"). The
   correction is in the ``dries_out`` pattern below, and the three records
   that forced it are in the test corpus.
2. **It must be safe on rubber**, and free of mineral oil and aggressive
   solvents -- both attack the tube as well as the tyre.
3. **It should inhibit corrosion**, or at least be declared safe on aluminium
   rims.

And the economics invert. Pack size is not a discount axis here: one scooter
tyre needs a few grams, the shelf is dominated by five-kilogram workshop tubs,
and the cheapest paste per kilogram on the page is the worst buy for this
user. So the ranking axis is *pack size, smallest first*, and price per
kilogram is computed, shown, and explicitly refused as a ranking.

What this category proved about the generic layer is written up in CONTRACT.md
§"What the second category changed". The short version: every trust rule
transferred unchanged, the one thing the layer had to learn was that a pack
measured in millilitres reconciles to a price per litre, and a real bug fell
out -- four records here state "Fett" (German for grease *and* for fat) beside
a pack size, which the food parser read as a nutrition declaration and the
generic layer would have trusted, because nothing in it required a nutrition
value to be corroborated by a second one.
"""

import re

from amazon_scraper.validation import (CategoryProfile, NOT_CLAIMED, TRUSTED,
                                       UNVERIFIED, Evidence, Value, validate)

from .. import category as cat

KEY = 'tyre_mounting_paste'

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Breadcrumbs cannot do this job. Measured over a 90-record Amazon.de crawl,
# the pastes are filed under "Auto & Motorrad" (49), "Sport & Freizeit" (31)
# and "Baumarkt" (9) -- and so is everything else the same search returns.
# One of the buckets is literally "Reifendichtmittel", the product class a
# mounting paste most needs to be told apart from. So the title is the
# classifier here, and the generic layer neither knows nor cares.
PRODUCT_RE = re.compile(
    # `gel` is here because a product called "Montagegel" is the same thing as
    # one called "Montagefluid" -- REMA TIP TOP sells one product under both
    # words, "Montage Fluid" in its Amazon title and "Montagegel" in its own
    # description. Leaving it out cost nothing visible for four crawls and
    # then cost a whole listing.
    r'(?:reifen)?montage[\s-]?(?:paste|wachs|wax|fluid|fl[üu]ssigkeit|spray|mittel|gel)'
    r'|(?:reifen)?montier[\s-]?(?:paste|wachs|wax)'
    r'|reifen[\s-]?(?:paste|wachs|wax|gleitmittel|schmiermittel)'
    r'|easy[\s-]?fit'
    r'|ty[rp]e\s+(?:lube|paste|mounting)|tire\s+(?:lube|paste|mounting)'
    r'|bead\s+(?:lube|sealer)', re.I)

# Product classes the same searches return, which are not this. Several are
# near-misses on purpose: carbon assembly paste is a *friction* paste, the
# exact opposite function, and anti-seize and bearing grease are designed
# never to dry.
WRONG_PRODUCT_RE = re.compile(
    r'dichtmilch|dichtmittel|reifen[\s-]?dicht|pannenspray|pannenschutz'
    r'|pannenset|sealant|tubeless[\s-]?milch'
    r'|vulkanisier|reifenkleber|klebstoff|\bkleber\b|flickzeug|reparatur|stopfen'
    r'|lagerfett|nabenfett|schmierfett|langzeitfett|kugellager'
    r'|mehrzweck[\s-]?fett|schmierpaste|getriebe'
    r'|anti[\s-]?seize|kupferpaste|keramik|\bcarbon\b|hochtemperatur'
    r'|radnabenpaste'
    r'|montiereisen|montierhebel|reifenheber|montierger[äa]t|abdr[üu]ck'
    r'|auswucht|wuchtgewicht|klebegewicht'
    r'|kompressor|luftpumpe|druckpr[üu]fer|reifenf[üu]ller|felgenreiniger',
    re.I)

# Things sold *alongside* paste. A brush is not a paste, but "5 kg paste with
# a brush" is.
ACCESSORY_RE = re.compile(
    r'\b(?:rund)?pinsel\b|\bb[üu]rste\b|\bschaber\b|\bspachtel\b|\bspatel\b',
    re.I)

# Words that say what the paste is *for*, and answer "not tyres". These are
# checked wherever they appear, unlike WRONG_PRODUCT_RE, because the positional
# rule below assumes a disqualifying word after the head noun is a bundled
# extra -- true for "Reifenmontagepaste ... inkl. Ventildreher", false for
# "Montagepaste Assembly Paste HT/FD Hochtemperatur-Kieselgel-Montagefett 110 g
# ... Zur Behandlung und Abdichtung aller Arten von Schraubengewinden", which
# is a thread grease that the positional rule waved through to rank 6 of a
# shortlist for a scooter tyre.
PURPOSE_RE = re.compile(
    r'schraubengewinde|gewindeverbindung|\bgewinde\b'
    r'|montagefett|kieselgel', re.I)

# "X für Y" makes Y the thing the product is *for*, not the thing it is:
# "Rundpinsel für Reifenmontagepaste" is a brush, and "Montagepaste für
# Reifen-Reparaturstopfen" is a plug lubricant, not a mounting paste.
FOR_RE = re.compile(r'\b(?:f[üu]r|for)\s+[\w-]{0,14}$', re.I)

# ---------------------------------------------------------------------------
# Claims. Every pattern below was written against the text of a 90-record
# Amazon.de crawl rather than imagined; the counts in the comments are what it
# actually found among the 43 records classified as mounting paste.
#
# Written against real text is not the same as complete, and two of these
# patterns had to be widened after the fact. The lesson both times was the
# same: a pattern built from the listings that *matched* it cannot show you
# the listings it missed. What found them was reading the corpus for the
# subject rather than for the pattern -- every sentence containing "trocken"
# in any form, rather than every sentence the regex already hit.
# ---------------------------------------------------------------------------

CLAIMS = (
    cat.Claim(
        'dries_out', 'Dries after mounting',
        # Three phrasings the first version of this pattern did not have, each
        # of which cost a real product its decisive claim. Vendors write the
        # drying property as a compound adjective far more often than as a
        # verb ("schnelltrocknend", "schnell trocknend", "lufttrocknet"); they
        # put an adverb between the verb and its particle ("trocknet
        # rückstandslos ab"); and they file it as an attribute row rather than
        # prose ("Aushärtung: 10 Minuten"). Measured on the same 90-record
        # crawl: 3 listings matched before, 11 match now, and the one that had
        # been missed with the strongest evidence is the smallest pack on the
        # shelf.
        r'\w*trocknet\s+(?:\w+\s+){0,2}(?:nach|ab|aus|an|ein|danach|schnell)'
        r'|\b\w*[\s-]?trocknend'
        r'|\b(?:luft|durch|voll)\w*trocknet'
        r'|verfl[üu]chtigt\s+sich'
        r'|aush[äa]rtung\s*:\s*\d+\s*(?:minute|min\b|stunde)'
        r'|nach\s+dem\s+(?:an|aus)?trocknen'
        r'|(?:an|ab|aus)getrocknet'
        r'|verliert\s+[^.]{0,30}(?:schmier|gleit)'
        r'|verhindert\s+[^.]{0,40}durchdrehen'
        r'|durchdrehen\s+des\s+reifens'
        r'|ruckgleiten'
        r'|(?:festen|sicheren)\s+(?:halt|sitz)\s+[^.]{0,20}(?:felge|reifen)',
        why='a paste that stays slippery lets the tyre creep on the rim and '
            'shear the valve off the tube'),
    cat.Claim(
        'water_based', 'Water-based / water-soluble',
        r'wasserl[öo]slich|wasserbasiert|auf\s+wasserbasis|wasserbasis'
        r'|water[\s-]?based|water[\s-]?soluble',
        why='the usable proxy for drying out: a water carrier evaporates, a '
            'mineral-oil one does not'),
    cat.Claim(
        'rubber_safe', 'Safe on rubber',
        # Deliberately not `schont ... Reifen`: it matched "Schont Reifen,
        # Nerven & Geldbeutel", which is a slogan, not a compatibility claim.
        r'gummivertr[äa]glich|gummi[\s-]?schonend|gummipflege'
        # "greift Gummi oder Metall nicht an" -- the noun and the negation are
        # not adjacent, because vendors list the materials. Requiring them to
        # be adjacent matched nothing at all in 102 records; allowing the list
        # matches the two listings that make this claim most explicitly.
        r'|greift\s+[^.]{0,40}(?:gummi|reifen|schlauch)[^.]{0,25}nicht\s+an'
        r'|reifenunsch[äa]dlich|schont\s+[^.]{0,20}(?:gummi|schlauch)'
        r'|materialschonend|greift\s+weder\s+felgen\s+noch\s+reifen\s+an'
        # An attribute row rather than prose, and weaker than the phrases
        # above -- it says the vendor filed rubber as the material this is
        # compatible with, not that it tested a butyl tube. It is kept because
        # the quote on the card says exactly that much, and a reader can weigh
        # a filled-in form field for what it is.
        r'|compatible\s+material\s*:[^.\n]{0,40}gummi'
        r'|kompatible\w*\s+material\w*\s*:[^.\n]{0,40}gummi',
        why='the inner tube sees the same paste the tyre does'),
    cat.Claim(
        'mineral_oil_free', 'Free of mineral oil',
        r'mineral[öo]lfrei|frei\s+von\s+mineral[öo]l|ohne\s+mineral[öo]l'
        r'|mineral\s?oil[\s-]?free',
        why='mineral oil swells and softens tyre and tube rubber'),
    cat.Claim(
        'solvent_free', 'Free of solvents, acids and resins',
        r'l[öo]sungsmittelfrei|l[öo]semittelfrei|s[äa]urefrei|harzfrei'
        r'|frei\s+von\s+(?:l[öo]sungsmitteln?|s[äa]uren)|solvent[\s-]?free',
        why='aggressive solvents attack rubber and rim coatings'),
    cat.Claim(
        'corrosion_protection', 'Inhibits corrosion',
        r'korrosionsschutz|korrosionshemmend|rostschutz'
        r'|sch[üu]tzt\s+[^.]{0,20}vor\s+korrosion'
        r'|verhindert\s+[^.]{0,25}(?:korrosion|festrosten)'
        r'|corrosion\s+(?:protect|inhibit)',
        why='paste sits between tyre bead and rim for the life of the tyre'),
    cat.Claim(
        'aluminium_rims', 'Stated for aluminium rims',
        # `leichtmetall` bare for the same reason `aluminium` already is:
        # German elides the shared head noun in a list, so "Stahl-,
        # Leichtmetall und Kunststofffelgen" never contains the string
        # "Leichtmetallfelge" that the specific alternative looks for.
        r'alu[\s-]?felge|aluminiumfelge|leichtmetallfelge'
        r'|aluminium(?:felgen)?\b|alufelgen|leichtmetall\b',
        why='the scooter rim is aluminium, not steel'),
    cat.Claim(
        'permanent_lubricant', 'Designed to keep lubricating',
        # The other way a paste fails this use case, and the one nothing in
        # the first version caught. A general-purpose assembly paste is sold
        # on properties that only make sense if the lubricant *stays*: wear
        # protection, a low friction coefficient, emergency running, solid
        # lubricants. Those are virtues on a bolted joint and disqualifying
        # between a tyre bead and a rim.
        #
        # This does not reclassify anything. The title is still what decides
        # whether a listing is a tyre paste, because a title is the only field
        # that reliably says what a product *is*; this claim reports what the
        # vendor says the product *does*, in the vendor's own words, and lets
        # the two disagree in the open. Measured on the 90-record crawl: two
        # listings, both of them "Montagepaste" with no tyre in the name.
        r'notlaufeigenschaft|festschmierstoff|dauerschmier|langzeitschmier'
        r'|verschlei[sß]schutz|reibkoeffizient|\bmos\s?2\b|molybd[äa]n'
        r'|\bnlgi\b|\bep-additiv',
        adverse=True,
        why='an assembly paste that keeps lubricating is the failure mode '
            'this use case exists to avoid, whatever the title calls it'),
    cat.Claim(
        'mineral_oil_base', 'Built on mineral oil',
        r'mineral[öo]lbasis|auf\s+mineral[öo]lbasis'
        r'|basis\s*:[^.\n]{0,40}mineral[öo]l'
        r'|technologie\s*:\s*mineral[öo]l',
        adverse=True,
        why='a mineral-oil paste never dries and never stops lubricating, '
            'which is the one property this use case cannot do without'),
)

# No nutrition, and deliberately no price band. A tube of bicycle mounting
# fluid and a five-kilogram workshop tub are both legitimately this product
# and sit two orders of magnitude apart per kilogram; inventing a range to
# have one would reject real listings. "No defensible band" is an answer.
PROFILE = CategoryProfile(key=KEY, label='tyre mounting paste',
                          nutrition_bands={}, price_band=None)

AXES = (
    cat.Axis('quantity', 'Pack size', better='lower',
             comparative='smaller', tolerance=1.0,
             why='one scooter tyre needs a few grams, so the smallest pack '
                 'that exists is the right one'),
    cat.Axis('price', 'Price', better='lower', comparative='cheaper to buy',
             tolerance=0.01,
             why='what you actually pay, which is the number that matters '
                 'when a lifetime supply is 100 g'),
    cat.Axis('price_per_base', 'Price per kg / l',
             caveat='shown, not ranked: a volume discount on a consumable you '
                    'will use twice is not a saving'),
)


def classify(record):
    """Is this a tyre mounting paste? Decided on the title, not the breadcrumbs.

    The rule that does the work is positional. German product titles put the
    head noun first and the bundled extras after it, so a disqualifying word
    *before* the paste word means the listing is that other thing, while the
    same word after it means the paste comes with one.
    ``"HASKYY 5kg Reifenmontagepaste ... inkl. Ventildreher, Auswuchtzange"``
    is paste; ``"Peaty's Max Grip Carbon Montagepaste"`` is not.
    """
    title = record.get('title') or ''
    if not title:
        return Value.unknown('the listing has no title to classify')

    head = PRODUCT_RE.search(title)
    if not head:
        return _classify_from_body(record, title)

    purpose = PURPOSE_RE.search(title)
    if purpose:
        return Value('other', TRUSTED,
                     evidence=[Evidence('title', title[:160])],
                     notes=[f'the title says what this paste is for, and it is '
                            f'not tyres: "{purpose.group(0)}"'])

    for pattern, why in ((WRONG_PRODUCT_RE, 'the listing is a different '
                                            'product class'),
                         (ACCESSORY_RE, 'the listing is an accessory')):
        for match in pattern.finditer(title):
            if match.start() < head.start() or FOR_RE.search(title[:match.start()]):
                return Value('other', TRUSTED,
                             evidence=[Evidence('title', title[:160])],
                             notes=[f'{why}: the title is headed by '
                                    f'"{match.group(0)}"'])

    return Value(KEY, TRUSTED, evidence=[Evidence('title', title[:160])])


# Words that put a body-text product claim in this category's world. Required
# alongside the product word, because "Montagepaste" in a description is not
# on its own a statement that the thing in the tin goes on a tyre bead.
TYRE_CONTEXT_RE = re.compile(
    r'reifen|fahrradmantel|wulst|felge|ty[rp]e|tire|bike|fahrrad', re.I)

# Fields that may speak when the title does not. The title stays the
# classifier -- see PRODUCT_RE -- and this is the one case it cannot decide.
BODY_FIELDS = ('content.feature_bullets', 'content.description')


def _classify_from_body(record, title):
    """Classify a listing whose title names no product class at all.

    "Rema Tip Top 501004 - Schwammdose, Transparent, 50 ml" is a real Amazon
    title for a bicycle tyre mounting gel. It names the container, the colour
    and the volume, and never says what is in it; its description does
    ("Montagegel für Fahrradreifen, das die Montage/Demontage von Reifen
    vereinfacht"). Reading the title as "no" made this listing invisible to a
    study whose whole subject it is.

    A silent title is not a denial, but it is also not the evidence the
    ordinary path has, so this route is deliberately weaker in three ways: it
    is only taken when the title names *nothing* -- neither a product word nor
    a disqualifier, so it can never overturn the positional rule; it needs a
    product word **and** a tyre-context word in the body; and what it returns
    is ``unverified``, which the card prints and no ranking treats as settled.
    """
    validated = validate(record, PROFILE)
    body = validated.search(PRODUCT_RE, limit=1, fields=BODY_FIELDS)
    context = validated.search(TYRE_CONTEXT_RE, limit=1, fields=BODY_FIELDS)
    wrong = (validated.search(WRONG_PRODUCT_RE, limit=1, fields=BODY_FIELDS)
             or validated.search(PURPOSE_RE, limit=1, fields=BODY_FIELDS))

    if body and context and not wrong:
        return Value(KEY, UNVERIFIED, evidence=list(body),
                     notes=['the title names no product class at all, so this '
                            'was decided on the description rather than on '
                            'the title'])

    return Value('other', TRUSTED,
                 evidence=[Evidence('title', title[:160])],
                 notes=['the title names no tyre mounting paste, wax or '
                        'fluid'])


# A listing that bundles tools describes them in the same text the paste is
# described in, so a claim quoted from it may be about the brush or the
# balancing weights. Measured: of five "for aluminium rims" claims, two are
# about a bundled valve tool and a set of wheel weights. The claim is kept --
# the quote is right there for the reader -- and told to say what it is.
BUNDLE_RE = re.compile(
    r'\bset\b|\bsatz\b|\d+\s*[-\s]?t(?:ei)?l(?:ig)?\b|\btlg\b|inkl\.'
    r'|\bmit\s+(?:pinsel|reiniger|ventil)', re.I)


def is_bundle(validated):
    return bool(BUNDLE_RE.search(validated.title or ''))


# A sentence that says the paste does *not* dry is not evidence that it does.
# Widening the drying pattern made this necessary rather than merely tidy: one
# 5 kg tub advertises "TROCKNET NICHT EIN IM EIMER UND AM PINSEL" -- a storage
# property, and a selling point for a workshop that leaves the lid off -- and
# the same listing separately states "Abtrocknungsverhalten: schnell
# trocknend". Both sentences are on the page and both are true of the product;
# only the second one answers the question this category asks. So negated hits
# are dropped by shared search before quoting/limiting. These expressions are
# category data; unrelated negations elsewhere in the field do not veto a hit.
NEGATED = {
    'dries_out': re.compile(
        r'trocknet[^.]{0,20}\b(?:nicht|nie|kaum)\b'
        r'|\bnicht\s+(?:aus|ein|an|ab)?(?:trocknen|trocknend)'
        r'|\bohne\s+(?:aus|ein|an|ab)?zutrocknen', re.I),
}


def stated(validated, claim):
    """The hits that survive this claim's own negations, best source first."""
    return validated.search(claim.pattern, limit=2, fields=claim.fields,
                            scope='page', affirmative=True,
                            exclude=NEGATED.get(claim.key))


def claims(validated):
    """Every criterion, each with the vendor's own sentence or an explicit gap."""
    bundle = is_bundle(validated)
    result = {}
    for claim in CLAIMS:
        hits = stated(validated, claim)
        if hits:
            value = Value(True, TRUSTED, evidence=hits, source='text')
            if bundle:
                value.notes.append(
                    'this listing is a kit, so the sentence above may describe '
                    'one of the other items in it rather than the paste')
            result[claim.key] = value
        else:
            result[claim.key] = Value(
                False, NOT_CLAIMED,
                notes=[f'{claim.label}: not stated anywhere on the page. That '
                       f'is not the same as it being untrue.'])
    return result


def check_claim_consistency(found):
    """Dispute the claims a declared mineral-oil base contradicts.

    The mirror of the pasta layer's "100% durum beside egg in the ingredient
    declaration": a composition statement beats a marketing adjective. A paste
    the vendor files as mineral-oil-based cannot also be free of mineral oil,
    and a mineral-oil carrier does not evaporate, so a drying claim beside one
    is a claim about something the product is not.
    """
    base = found.get('mineral_oil_base')
    if base and base.status == TRUSTED:
        for key, why in (
                ('mineral_oil_free',
                 'the page claims freedom from mineral oil and also files a '
                 'mineral-oil base'),
                ('dries_out',
                 'the page claims the paste dries out, but declares a '
                 'mineral-oil base, which does not evaporate')):
            value = found.get(key)
            if value is not None and value.status == TRUSTED:
                value.dispute(why, *base.evidence[:1])

    # And the same argument from the other adverse claim. Wear protection and
    # a low friction coefficient are properties of a film that is still there;
    # a page selling both those and "dries out" is describing two products.
    lubricant = found.get('permanent_lubricant')
    if lubricant and lubricant.status == TRUSTED:
        value = found.get('dries_out')
        if value is not None and value.status == TRUSTED:
            value.dispute('the page claims the paste dries out and also sells '
                          'it on staying lubricating',
                          *lubricant.evidence[:1])


def suitability(found):
    """How much of what this use case needs the page actually establishes.

    Not a score. A count of the criteria that have evidence behind them, so a
    card can say "two of the three things you care about are simply not
    stated" instead of implying the silence means no.
    """
    decisive = ('dries_out', 'water_based', 'rubber_safe',
                'corrosion_protection')
    answered = [key for key in decisive
                if found.get(key) is not None
                and found[key].status == TRUSTED]
    adverse = [claim.key for claim in CLAIMS if claim.adverse
               and found.get(claim.key) is not None
               and found[claim.key].status == TRUSTED]
    return {'answered': answered, 'adverse': adverse,
            'total': len(decisive)}


def evaluate(record):
    """One mounting-paste evidence card, or a classification-only card."""
    classification = classify(record)
    validated = validate(record, PROFILE)

    if classification.value != KEY:
        return cat.card(record, validated, CATEGORY, classification,
                        axes={}, claims={})

    found = claims(validated)
    check_claim_consistency(found)

    axes = {'quantity': validated.quantity,
            'price': validated.price,
            'price_per_base': validated.price_per_base}

    card = cat.card(record, validated, CATEGORY, classification, axes, found)
    card['suitability'] = suitability(found)
    return card


CATEGORY = cat.register(cat.Category(
    key=KEY,
    label='tyre mounting paste',
    profile=PROFILE,
    axes=AXES,
    claims=CLAIMS,
    evaluate=evaluate,
    default_axis='quantity',
    blurb='Ranked by pack size, smallest first: a scooter tyre needs a few '
          'grams and the shelf is five-kilogram workshop tubs. Price per '
          'kilogram is shown and deliberately not ranked on.',
))
