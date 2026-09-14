"""Identity, provenance and the on-disk evidence of one crawl.

A crawl used to leave exactly one artefact: a file of product records, with no
statement of what was asked for, which locale answered, or what was seen and
then discarded. Three consequences, all of which cost a re-crawl to undo:

* **Discovery was destroyed as it happened.** The spider drops an ASIN it has
  already queued before anything about that sighting is written down. One live
  Amazon.de search page carries the same ASIN twice -- once organic at rank 8
  and once sponsored at rank 16 -- and that fact was unrecoverable.
* **The page was thrown away.** Every new field the extractor learns to read
  costs a fresh crawl of pages we already downloaded, which contradicts the
  first thing this project decided about how to treat evidence.
* **Locale was implicit.** It lives in an HTTP header in a settings module,
  while the label vocabulary is chosen separately from the domain. The two can
  disagree with no error at all: an English-locale request to amazon.de leaves
  every German label unmapped and emits an empty ``attributes`` block beside a
  full ``raw_tables``.

So a run now owns a directory::

    data/runs/<run_id>/
        manifest.json        what was asked for, which locale answered, stats
        discovery.jsonl      one line per sighting, before de-duplication
        pages/<ASIN>.html.gz the page each record was extracted from

The product feed is unchanged and still goes wherever ``-O`` points. Nothing
here interprets anything: it records.
"""

import datetime as _dt
import gzip
import hashlib
import json
import pathlib
import re

# Written next to the crawl output rather than inside it, so a feed file can
# still be moved, appended to or replaced without losing its provenance.
DEFAULT_RUN_ROOT = 'data/runs'

MANIFEST = 'manifest.json'
DISCOVERY = 'discovery.jsonl'
PAGES = 'pages'


def _utc_now():
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def acquisition_locale(settings, marketplace):
    """The locale a crawl actually asks Amazon for, and whether it fits.

    Returns ``{'accept_language', 'language', 'expected_language', 'status'}``.
    ``status`` is one of:

    ``matches``
        The request locale agrees with the marketplace profile's label
        vocabulary. This is the only configuration that has been validated.
    ``unset``
        No ``Accept-Language`` is configured, so Amazon answers in the
        marketplace's own default. On amazon.de that is German, which is what
        we want, but it is luck rather than intent -- hence a warning.
    ``conflict``
        A locale is configured that contradicts the profile. Nothing would
        raise; extraction would quietly under-report. The caller turns this
        into a hard failure.
    """
    headers = settings.getdict('DEFAULT_REQUEST_HEADERS') or {}
    header = ''
    for name, value in headers.items():
        if name.lower() == 'accept-language':
            header = (value or '').strip()
            break

    expected = marketplace.language
    if not header:
        return {'accept_language': '', 'language': None,
                'expected_language': expected, 'status': 'unset'}

    # "de-DE,de;q=0.9,en;q=0.8" -> "de". Only the first, highest-priority tag
    # decides: the rest are fallbacks Amazon may never use.
    primary = re.split(r'[;,]', header)[0].strip().lower()
    language = primary.split('-')[0] or None
    status = 'matches' if language == expected else 'conflict'
    return {'accept_language': header, 'language': language,
            'expected_language': expected, 'status': status}


class CrawlRun:
    """One crawl's identity and its directory of evidence."""

    def __init__(self, root, spider, marketplace, locale, arguments,
                 keep_pages=True):
        self.started_at = _utc_now()
        self.spider = spider
        self.marketplace = marketplace
        self.locale = locale
        self.arguments = dict(arguments)
        self.keep_pages = keep_pages

        # Sortable by time, readable at a glance, and unique even when two
        # crawls of the same marketplace start in the same second.
        stamp = self.started_at.strftime('%Y%m%dT%H%M%SZ')
        digest = hashlib.sha1(
            f'{stamp}{marketplace}{sorted(self.arguments.items())}'.encode()
        ).hexdigest()[:8]
        self.run_id = f'{stamp}-{marketplace}-{digest}'

        self.directory = pathlib.Path(root) / self.run_id
        self.pages_directory = self.directory / PAGES
        self.counts = {'discovery_occurrences': 0, 'pages_saved': 0,
                       'page_write_errors': 0}
        self._discovery = None

    # -- provenance carried on every record --------------------------------

    def lineage(self):
        """The provenance fields every record of this run carries."""
        return {'run_id': self.run_id,
                'locale': self.locale.get('language') or '',
                'accept_language': self.locale.get('accept_language') or ''}

    # -- writing -----------------------------------------------------------

    def open(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.keep_pages:
            self.pages_directory.mkdir(parents=True, exist_ok=True)
        self._discovery = (self.directory / DISCOVERY).open(
            'a', encoding='utf-8')
        self.write_manifest()
        return self

    def record_discovery(self, occurrence):
        """Append one sighting, exactly as seen, before any de-duplication."""
        if self._discovery is None:
            return
        line = dict(occurrence)
        line.setdefault('run_id', self.run_id)
        line.setdefault('marketplace', self.marketplace)
        line.setdefault('locale', self.locale.get('language') or '')
        line.setdefault('seen_at', _utc_now().isoformat())
        self._discovery.write(json.dumps(line, ensure_ascii=False) + '\n')
        self._discovery.flush()
        self.counts['discovery_occurrences'] += 1

    def save_page(self, asin, html):
        """Store the page a record was extracted from, gzipped.

        Redacted on the way in with the same rules the committed corpus uses:
        the identifiers Amazon mints per session and per request have no place
        in a stored page, and the corpus test proves the substitution does not
        change a single extracted value. It also means any page in this store
        can be promoted into ``tests/corpus/`` as-is.
        """
        if not (self.keep_pages and asin and html):
            return None
        path = self.pages_directory / f'{asin}.html.gz'
        try:
            with gzip.open(path, 'wt', encoding='utf-8', compresslevel=6) as fh:
                fh.write(_redact(html))
        except OSError:
            self.counts['page_write_errors'] += 1
            return None
        self.counts['pages_saved'] += 1
        return path

    def write_manifest(self, stats=None, finish_reason=None):
        manifest = {
            'run_id': self.run_id,
            'spider': self.spider,
            'marketplace': self.marketplace,
            'started_at': self.started_at.isoformat(),
            'arguments': self.arguments,
            'locale': self.locale,
            'pages_retained': self.keep_pages,
            'counts': dict(self.counts),
        }
        if finish_reason is not None:
            manifest['finished_at'] = _utc_now().isoformat()
            manifest['finish_reason'] = finish_reason
        if stats is not None:
            manifest['stats'] = {key: value for key, value in stats.items()
                                 if isinstance(value, (int, float, str, bool))}
        path = self.directory / MANIFEST
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                   sort_keys=True) + '\n', encoding='utf-8')
        return path

    def close(self, stats=None, finish_reason=None):
        if self._discovery is not None:
            self._discovery.close()
            self._discovery = None
        self.write_manifest(stats, finish_reason)


def _redact(html):
    """Strip per-session identifiers, reusing the corpus' redaction rules."""
    try:
        import sys
        corpus = pathlib.Path(__file__).resolve().parent.parent / 'tests' / 'corpus'
        if str(corpus) not in sys.path:
            sys.path.append(str(corpus))
        import redact as _redact_module
        return _redact_module.redact(html)
    except Exception:
        # A stored page is worth more than a perfectly stripped one; the store
        # is local and gitignored. Never lose the evidence over this.
        return html


# ---------------------------------------------------------------------------
# Reading a run back
# ---------------------------------------------------------------------------

def load_manifest(directory):
    return json.loads((pathlib.Path(directory) / MANIFEST)
                      .read_text(encoding='utf-8'))


def load_discovery(directory):
    path = pathlib.Path(directory) / DISCOVERY
    if not path.exists():
        return []
    with path.open(encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


def stored_pages(directory):
    """``{asin: path}`` for every page retained by a run."""
    pages = pathlib.Path(directory) / PAGES
    if not pages.is_dir():
        return {}
    return {path.name[:-len('.html.gz')]: path
            for path in sorted(pages.glob('*.html.gz'))}


def read_page(path):
    with gzip.open(path, 'rt', encoding='utf-8') as fh:
        return fh.read()
