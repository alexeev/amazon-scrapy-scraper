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

Because the pages survive, a finished run re-extracts offline with today's
extractor and no network at all::

    python -m amazon_scraper.run reextract data/runs/<run_id> \
        --feed data/products.jsonl -o data/products.v6.jsonl
"""

import argparse
import datetime as _dt
import gzip
import hashlib
import json
import pathlib
import re
import sys

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


def read_jsonl(path):
    """Every record of a feed, gzipped or not."""
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# Re-extracting a finished run
# ---------------------------------------------------------------------------

# What a record knows that its page does not. A stored page says everything
# about the product and nothing about the crawl: which query found it, where
# it ranked, when it was fetched. Those come from the feed the crawl wrote,
# and are copied across verbatim rather than guessed at.
CRAWL_FIELDS = ('marketplace', 'asin', 'product_url', 'canonical_url',
                'search_query', 'search_page', 'search_position',
                'run_id', 'locale', 'accept_language', 'fetched_at')


def _page_fetched_at(path):
    """When the page was fetched, which is when it was written down.

    Not when it is being re-read. A re-extraction that stamped itself with
    today's clock would make every old page look like the freshest evidence
    in the study, which is the one thing a merge across crawls must not
    believe.
    """
    stamp = _dt.datetime.fromtimestamp(path.stat().st_mtime, _dt.timezone.utc)
    return stamp.replace(microsecond=0).isoformat()


def _lineage(asin, path, manifest, crawled, canonical_url):
    """The provenance a re-extracted record carries, best available first."""
    marketplace = manifest.get('marketplace') or ''
    locale = manifest.get('locale') or {}
    lineage = {
        'marketplace': marketplace,
        'asin': asin,
        'product_url': f'https://{marketplace}/dp/{asin}',
        'canonical_url': canonical_url or f'https://{marketplace}/dp/{asin}',
        'run_id': manifest.get('run_id') or '',
        'locale': locale.get('language') or '',
        'accept_language': locale.get('accept_language') or '',
        'fetched_at': _page_fetched_at(path),
    }
    # The crawl's own record wins wherever it has something to say: it is the
    # only witness to the search that found this page.
    lineage.update({key: crawled[key] for key in CRAWL_FIELDS
                    if key in (crawled or {})})
    return lineage


def reextract(directory, feed=None):
    """Re-extract every page a run retained, with today's extractor.

    Yields ``(asin, record, error)`` per stored page, in ASIN order, and
    touches no network. ``error`` is a string on the pages that could not be
    read or parsed at all and ``None`` otherwise; block-level failures are
    not errors here -- the extractor reports those inside the record, in
    ``extraction.errors``, and the record is still worth writing.

    ``feed`` is the JSONL the crawl wrote. It is optional, and supplying it
    is the difference between a record that knows which query found it and
    one that does not.
    """
    from parsel import Selector

    from .extraction import PdpExtractor, for_domain

    directory = pathlib.Path(directory)
    manifest = load_manifest(directory)
    extractor = PdpExtractor(for_domain(manifest['marketplace']))
    crawled = {record['asin']: record
               for record in (read_jsonl(feed) if feed else [])
               if record.get('asin')}

    for asin, path in stored_pages(directory).items():
        try:
            html = read_page(path)
            selector = Selector(html)
            lineage = _lineage(
                asin, path, manifest, crawled.get(asin),
                selector.css('link[rel=canonical]::attr(href)').get())
            record = extractor.extract(selector, html, lineage)
        except Exception as exc:  # one unreadable page must not end the pass
            yield asin, None, f'{type(exc).__name__}: {exc}'
        else:
            yield asin, record, None


def reextract_command(args):
    """``reextract <run_dir> -o new.jsonl [--feed old.jsonl]``."""
    feed = read_jsonl(args.feed) if args.feed else []
    known = {record['asin'] for record in feed if record.get('asin')}

    opener = gzip.open if args.output.endswith('.gz') else open
    pages = records = block_errors = 0
    failed, unseen = [], []
    with opener(args.output, 'wt', encoding='utf-8') as out:
        for asin, record, error in reextract(args.run_dir, args.feed):
            pages += 1
            if error is not None:
                failed.append(f'{asin} — {error}')
                continue
            records += 1
            block_errors += len(record['extraction']['errors'])
            if args.feed and asin not in known:
                unseen.append(asin)
            out.write(json.dumps(record, ensure_ascii=False) + '\n')

    print(f'{args.run_dir}: {pages} pages, {records} records, '
          f'{block_errors} extraction errors -> {args.output}')
    if unseen:
        print(f'  {len(unseen)} pages had no record in {args.feed}, so they '
              f'carry the run\'s provenance but not a search query: '
              + ', '.join(unseen[:6]) + ('…' if len(unseen) > 6 else ''))
    for line in failed[:10]:
        print(f'  unreadable: {line}')
    if len(failed) > 10:
        print(f'  … and {len(failed) - 10} more unreadable pages')
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='amazon_scraper.run',
        description='Work with the evidence a finished crawl left behind.')
    commands = parser.add_subparsers(dest='command', required=True)

    reextraction = commands.add_parser(
        'reextract', help='re-extract a run\'s retained pages, offline')
    reextraction.add_argument('run_dir', help='data/runs/<run_id>')
    reextraction.add_argument('-o', '--output', required=True,
                              help='JSONL to write; .gz is compressed')
    reextraction.add_argument('--feed', default='',
                              help='the JSONL this run wrote, so the new '
                                   'records keep the search query, position '
                                   'and fetch time only the crawl knew')
    reextraction.set_defaults(handler=reextract_command)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == '__main__':
    sys.exit(main())
