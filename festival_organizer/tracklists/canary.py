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

import re

from bs4 import BeautifulSoup


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def check_challenge_page(html: str) -> list[str]:
    """Detect the Cloudflare Turnstile interstitial served to unauthenticated
    or challenged clients.

    The interstitial carries a real <h1> ("Please wait, you will be
    forwarded"), so structural probes pass on it while every parser
    silently returns nothing; probe for the challenge script and the
    forwarding copy instead.
    """
    soup = _soup(html)
    if soup.select_one('script[src*="challenges.cloudflare.com"]') is not None:
        return ["cloudflare challenge interstitial"]
    h1 = soup.find("h1")
    if h1 is not None and "you will be forwarded" in h1.get_text(" ", strip=True):
        return ["cloudflare challenge interstitial"]
    return []


def check_tracklist_page(html: str) -> list[str]:
    """Check a /tracklist/{ID}/ page for markers the tracklist parsers need.

    Covers _parse_tracks, _parse_h1_structure, and _extract_genres in
    one probe since they all consume the same page HTML.
    """
    # A challenge page fails every other probe; one precise label beats
    # five noisy ones.
    challenge = check_challenge_page(html)
    if challenge:
        return challenge

    soup = _soup(html)
    missing: list[str] = []

    has_rows = soup.select_one("div.tlpItem.tlpTog") is not None
    if not has_rows:
        missing.append("tlpItem row")
    if soup.select_one("input[id$='_cue_seconds']") is None:
        missing.append("cue_seconds input")
    # _parse_tracks reads the visible cue display to tell an unset cue
    # (empty div) from a genuine 00:00; if the div vanishes, uncued rows
    # silently become phantom 00:00 chapters. Gated on rows existing so a
    # row-less page reports "tlpItem row" alone instead of two labels.
    if has_rows and soup.select_one("div.tlpItem div[onclick*='toggleCue']") is None:
        missing.append("cue display div")
    # _parse_tracks names a track from meta itemprop=name, falling back to
    # span.trackValue. If neither survives a redesign every chapter would
    # come out nameless. Gated on rows for the same reason as above.
    if (
        has_rows
        and soup.select_one("div.tlpItem meta[itemprop='name']") is None
        and soup.select_one("div.tlpItem span.trackValue") is None
    ):
        missing.append("track name source")

    h1_el = soup.find("h1")
    if h1_el is None:
        missing.append("h1 element")
    elif "@" in h1_el.get_text():
        # The before-@ fragment must link the DJs (/dj/ pre-2026, /artist/
        # after the redesign). An h1 with an @ but no artist anchor is the
        # exact shape that silently cleared ARTISTS tags library-wide when
        # the 2026 redesign landed.
        has_artist_anchor = any(
            str(a.get("href", "")).startswith(("/dj/", "/artist/"))
            for a in h1_el.select("a")
        )
        if not has_artist_anchor:
            missing.append("h1 artist anchor")

    if has_rows:
        row_anchor = soup.select_one(
            'div.tlpItem a[href^="/artist/"], div.tlpItem a[href^="/dj/"]'
        )
        if row_anchor is None:
            missing.append("track artist anchor")

    if soup.select_one('meta[itemprop="genre"]') is None:
        missing.append("itemprop=genre meta")

    # Multi-source pages carry "Player N" headers; if those exist but the
    # media tabs that name each source do not parse, player selection would
    # silently fall back to wrong-timeline chapters. Surface it.
    has_player_headers = any(
        re.match(r"^Player \d+$", el.get_text(strip=True))
        for el in soup.select("div.bItmH")
    )
    if has_player_headers and soup.select_one("li[id^='mediaLinkBtn']") is None:
        missing.append("media player tabs")

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
    """Check an artist profile page (/artist/{slug}/tracklists.html, or the
    legacy /dj/{slug}/ shape) for the og:image meta that _parse_dj_profile
    reads as the primary artwork source."""
    challenge = check_challenge_page(html)
    if challenge:
        return challenge
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
