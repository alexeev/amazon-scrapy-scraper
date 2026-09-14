"""Strip per-session identifiers from a saved Amazon page.

Every page in this corpus is run through :func:`redact` before it is
committed. The pages are fetched without signing in -- ``customerId`` is
empty and ``isCustomerLoggedIn`` is ``false`` on all of them -- so there is no
account data to remove. What is left are the anonymous identifiers Amazon
mints per session and per request, which have no place in a git history.

Identifiers are found at their canonical declaration and then replaced
literally, rather than matched by shape across the whole document. Shape rules
are what you reach for first and they are wrong here: every UUID also matches
an A+ content image URL, and every twenty-character uppercase token also
matches a German A+ heading (``HERZENSANGELEGENHEIT``). Both mistakes were
made, and both were caught by the corpus test, which is the real guard --
redaction must not change a single extracted value.

Usage, when adding a page to the corpus::

    python tests/corpus/redact.py raw.html tests/corpus/amazon_de/B0XXXXXXXX.html.gz
"""

import gzip
import re
import sys

SESSION_ID = '000-0000000-0000000'
REQUEST_ID = 'X' * 20
CORRELATION_ID = '00000000-0000-0000-0000-000000000000'

# Amazon declares both per-page identifiers once, in the ue_* telemetry
# preamble, and then echoes them into a dozen keys, hidden inputs and query
# strings (session-id, rsid, sid, sessionId, verificationSessionID, rid,
# requestId, uedata URLs, ...). Reading them here and replacing the literal
# catches every echo without having to enumerate the keys.
DECLARED_IDS = (
    (re.compile(r"\bue_sid\s*=\s*'([^']{6,64})'"), SESSION_ID),
    (re.compile(r"\bue_id\s*=\s*'([^']{6,64})'"), REQUEST_ID),
)

SUBSTITUTIONS = (
    # Safety net for a page saved without the ue_* preamble. This shape is
    # distinctive enough not to collide with product text.
    (re.compile(r'\b\d{3}-\d{7}-\d{7}\b'), SESSION_ID),
    # Per-widget correlation ids, anchored to the attribute or key that
    # carries them: the values are opaque and come in two shapes (a UUID and a
    # base64-ish token), and bare UUIDs also appear inside A+ image URLs,
    # which are content. Both the attribute form and the HTML-escaped JSON
    # form appear on the same page.
    (re.compile(r'(data-a?rid=")[^"]{8,64}(")'),
     r'\g<1>' + CORRELATION_ID + r'\g<2>'),
    (re.compile(r'("|&quot;)a?rid\1\s*:\s*("|&quot;)[^"&]{8,64}\2'),
     r'\g<1>arid\g<1>:\g<2>' + CORRELATION_ID + r'\g<2>'),
    # The render service's own IP, echoed into A+ preview metadata.
    (re.compile(r'("|&quot;)ipAddress\1\s*:\s*("|&quot;)[0-9.]+\2'),
     r'\1ipAddress\1:\g<2>0.0.0.0\2'),
)


def redact(html):
    """Return `html` with per-session identifiers replaced by fixed values."""
    for pattern, replacement in DECLARED_IDS:
        match = pattern.search(html)
        if match:
            html = html.replace(match.group(1), replacement)
    for pattern, replacement in SUBSTITUTIONS:
        html = pattern.sub(replacement, html)
    return html


def main(src, dest):
    opener = gzip.open if src.endswith('.gz') else open
    with opener(src, 'rt', encoding='utf-8') as fh:
        html = fh.read()
    with gzip.open(dest, 'wt', encoding='utf-8', compresslevel=9) as fh:
        fh.write(redact(html))
    print(f'{src} -> {dest}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__.strip().splitlines()[-1].strip())
    main(sys.argv[1], sys.argv[2])
