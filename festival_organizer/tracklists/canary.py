"""Structural canary for scraped 1001tracklists.com pages.

Each probe accepts raw HTML and returns a list of human-readable
selector labels that are missing from the page. An empty list means
the page carries every structural marker our parsers depend on.

Callers in api.py run a probe immediately after each fetch and emit a
WARNING when the list is non-empty, so a 1001tracklists.com redesign
surfaces loudly instead of silently draining data out of NFOs, posters,
and chapter markers.

Probes use BeautifulSoup with the same selectors the paired parsers
use, so a canary hit corresponds to a real parser failure on the same
HTML. The labels are phrased for log output, not for code consumers.
"""
from __future__ import annotations

from bs4 import BeautifulSoup


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def check_tracklist_page(html: str) -> list[str]:
    """Check a /tracklist/{ID}/ page for markers the tracklist parsers need.

    Covers _parse_tracks, _parse_h1_structure, and _extract_genres in
    one probe since they all consume the same page HTML.
    """
    soup = _soup(html)
    missing: list[str] = []

    if soup.select_one("div.tlpItem.tlpTog") is None:
        missing.append("tlpItem row")
    if soup.select_one("input[id$='_cue_seconds']") is None:
        missing.append("cue_seconds input")

    h1 = soup.find("h1")
    if h1 is None or "@" not in h1.get_text():
        missing.append("h1 with @")

    if soup.select_one('meta[itemprop="genre"]') is None:
        missing.append("itemprop=genre meta")

    return missing


def check_search_results(html: str) -> list[str]:
    """Check a POST /search/result.php response for the page skeleton.

    Zero hits for a query is a valid outcome and must not trigger the
    canary, so this probe does not check for result cards (.bItm).
    It checks only the main_search input that frames every search
    page, hits or no hits.
    """
    soup = _soup(html)
    missing: list[str] = []
    if soup.select_one('input[name="main_search"]') is None:
        missing.append("search form skeleton")
    return missing


def check_dj_profile(html: str) -> list[str]:
    """Check a /dj/{slug}/ page for the og:image meta that _parse_dj_profile
    reads as the primary artwork source."""
    soup = _soup(html)
    missing: list[str] = []
    if soup.select_one('meta[property="og:image"]') is None:
        missing.append("og:image meta")
    return missing


def check_source_info(html: str) -> list[str]:
    """Check a /source/{id}/{slug}/ page for the markers fetch_source_info reads.

    The cRow > mtb5 div carries the source type (Festival, Club, etc.)
    and the flags/*.png img carries the country alt text. Both are the
    defining data for festival-organizer's source routing, so either
    being absent is worth surfacing.
    """
    soup = _soup(html)
    missing: list[str] = []
    if soup.select_one("div.cRow > div.mtb5") is None:
        missing.append("source type mtb5 div")
    if soup.select_one('img[src*="flags/"]') is None:
        missing.append("country flag img")
    return missing
