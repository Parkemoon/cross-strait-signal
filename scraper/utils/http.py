"""Shared HTTP client defaults for scrapers (CODE_REVIEW_2026-07-03 §4.9).

Before this module, ~15 scrapers carried their own copy of the browser
header dict and httpx client construction, and they had drifted (Chrome
versions 120–124, timeouts 20 vs 30). One UA + one factory now; scrapers
with genuinely special requirements (cookies, API headers, deliberate bot
UA like refresh_officials' Wikidata etiquette) keep their own.
"""
import httpx

# The one browser UA. Bump the Chrome version here when sites start
# rejecting it — every converted scraper picks it up.
BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
              'AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/124.0.0.0 Safari/537.36')

DEFAULT_TIMEOUT = 30


def browser_headers(referer=None, **extra):
    """Standard browser-like headers. Pass referer= for sites that gate on
    it (guancha, BOFT); extra kwargs become additional header fields."""
    headers = {'User-Agent': BROWSER_UA}
    if referer:
        headers['Referer'] = referer
    headers.update(extra)
    return headers


def make_async_client(timeout=DEFAULT_TIMEOUT, headers=None, referer=None, **kw):
    """httpx.AsyncClient with the scraper-standard defaults
    (follow_redirects on, 30s timeout, browser headers)."""
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers if headers is not None else browser_headers(referer=referer),
        **kw,
    )
