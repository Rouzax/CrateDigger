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
