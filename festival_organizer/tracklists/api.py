"""1001Tracklists API: session management, search, and tracklist export.

Logging:
    Logger: 'festival_organizer.tracklists.api'
    Key events:
        - search.params (DEBUG): Search parameters sent to API
        - search.response (DEBUG): Search response status and size
        - search.no_results (DEBUG): HTML returned but zero results parsed
        - export.genres (INFO): Genres extracted from tracklist page
        - export.cached_source (INFO): Source page metadata cached
        - export.cached_dj (INFO): DJ profile cached
        - export.dj_artwork (INFO): DJ artwork URL found
        - session.validation_failed (DEBUG): Session validation request failed
        - session.cookie_save_failed (DEBUG): Could not persist cookies
        - session.cookie_restore_failed (DEBUG): Could not load cached cookies
        - dj.fetch_failed (DEBUG): DJ profile page request failed
    See docs/logging.md for full guidelines.
"""
import html as html_mod
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests

logger = logging.getLogger(__name__)

from festival_organizer.tracklists.scoring import SearchResult
from festival_organizer.tracklists import canary

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0"
BASE_URL = "https://www.1001tracklists.com"
DEFAULT_COOKIE_PATH = Path.home() / ".1001tl-cookies.json"


class TracklistError(Exception):
    """Base error for tracklist operations."""


class AuthenticationError(TracklistError):
    """Login failed or session expired."""


class RateLimitError(TracklistError):
    """Too many requests — captcha required."""


class ExportError(TracklistError):
    """Failed to export tracklist data."""


@dataclass
class Track:
    """A single track on a 1001TL tracklist.

    start_ms: chapter start in milliseconds
    raw_text: the visible track label, as exported by 1001TL (e.g. 'Artist - Title (Remix) [Label]')
    artist_slugs: 1001TL slugs for every linked artist on the track row, in link order
    artist_names: HTML display text for every linked artist, paired by index with artist_slugs
    title: track title portion only, without artist prefix or label brackets
    label: record label as plain text (e.g. "WALL"), empty if not listed
    genres: per-track <meta itemprop="genre"> values for this row
    """
    start_ms: int
    raw_text: str
    artist_slugs: list[str]
    genres: list[str]
    artist_names: list[str] = field(default_factory=list)
    title: str = ""
    label: str = ""


@dataclass
class TracklistExport:
    """Exported tracklist data."""
    lines: list[str]
    url: str
    title: str
    genres: list[str] = field(default_factory=list)
    dj_artists: list[tuple[str, str]] = field(default_factory=list)
    dj_artwork_url: str = ""
    stage_text: str = ""
    sources_by_type: dict[str, list[str]] = field(default_factory=dict)
    country: str = ""
    location: str = ""
    source_type: str = ""
    tracks: list[Track] = field(default_factory=list)
    date: str = ""


def top_genres_by_frequency(tracks: list["Track"], n: int = 5) -> list[str]:
    """Return the top-n most frequent per-track genres across the set.

    Each genre counts once per track it appears on (so a track tagged with
    three genres contributes one to each). Ties are broken by first-appearance
    order so the result is deterministic across runs.
    """
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    idx = 0
    for track in tracks:
        for g in track.genres:
            if not g:
                continue
            if g not in counts:
                first_seen[g] = idx
                idx += 1
            counts[g] = counts.get(g, 0) + 1
    ordered = sorted(counts, key=lambda g: (-counts[g], first_seen[g]))
    return ordered[:n]


def _parse_tracks(html) -> list["Track"]:
    """Extract chapter-aligned per-track rows from a 1001TL tracklist page.

    Accepts raw HTML or an already-parsed BeautifulSoup so export_tracklist
    can share one parse with the other tracklist-page parsers.

    Only rows with class 'tlpTog' and NOT 'con' and NOT 'tlpSubTog' are
    included; the page also contains mashup-component sub-rows that do not
    correspond to chapter atoms. Returns Track objects in page order with
    start_ms taken from the row's cue_seconds input (float seconds * 1000).
    """
    from bs4 import BeautifulSoup
    soup = _to_soup(html)
    tracks: list[Track] = []
    for row in soup.select("div.tlpItem"):
        classes = set(row.get("class", []))
        if "tlpTog" not in classes:
            continue
        if "con" in classes or "tlpSubTog" in classes:
            continue
        cue_el = row.select_one("input[id$='_cue_seconds']")
        if cue_el is None:
            continue
        try:
            start_ms = int(float(cue_el.get("value", "0")) * 1000)
        except ValueError:
            continue
        from festival_organizer.normalization import fix_mojibake
        name_meta = row.select_one('meta[itemprop="name"]')
        raw_text = fix_mojibake(name_meta.get("content", "")) if name_meta else ""
        genres = [
            fix_mojibake(m.get("content", ""))
            for m in row.select('meta[itemprop="genre"]')
            if m.get("content")
        ]
        # Walk artist anchors in document order; capture (slug, display_name)
        # pairs. Display name is the stripped text of the nearest ancestor
        # <span class="notranslate"> that wraps the anchor.
        slugs: list[str] = []
        names: list[str] = []
        for a in row.select("a[href^='/artist/']"):
            m = re.match(r"/artist/[^/]+/([^/]+)/", a.get("href", ""))
            if not m:
                continue
            slug = m.group(1)
            if slug in slugs:
                continue
            # Extract the per-artist display name. 1001TL renders three
            # distinct shapes around artist anchors and we handle each:
            #
            # 1. Primary artist (left side of track): the anchor lives inside
            #    <span class="tgHid spL"> inside <span class="notranslate
            #    blueTxt">NAME<tgHid/></span>. The walk-up below picks up
            #    "NAME" from that outer blueTxt wrapper.
            #
            # 2. Remix-credit artist (right side, inside parentheses): the
            #    anchor lives inside <span class="tgHid spR"> and the NAME
            #    is the preceding sibling <span class="blueTxt">NAME</span>.
            #    This path preserves casing and punctuation exactly (LAWTON,
            #    Kø:lab, Armin van Buuren with lowercase "van", etc.) rather
            #    than losing it to a slug-derived fallback.
            #
            # 3. Feature-prefix inline (e.g. " ft. Caroline Roxy<a/>"): the
            #    anchor is a direct child of a notranslate span whose text
            #    carries a feature prefix. Falls into the walk-up below; the
            #    ft./feat. prefix is stripped afterwards.
            #
            # Parenthetical credits where 1001TL wraps the anchor itself
            # inside a <span class="notranslate">( NAME Mashup )</span>
            # (Afrojack-as-mashup-credit) are rejected: the text is an edit
            # annotation, not a clean name. Slug-fallback wins in that case.
            display = ""
            parent_wrapper = a.parent
            if (parent_wrapper is not None and hasattr(parent_wrapper, "get")
                    and "tgHid" in parent_wrapper.get("class", [])
                    and "spR" in parent_wrapper.get("class", [])):
                prev = parent_wrapper.previous_sibling
                while prev is not None and getattr(prev, "name", None) is None:
                    if str(prev).strip():
                        break
                    prev = prev.previous_sibling
                if (prev is not None and getattr(prev, "name", None) == "span"
                        and hasattr(prev, "get")
                        and "blueTxt" in prev.get("class", [])):
                    display = prev.get_text(" ", strip=True)
            if not display:
                parent = a
                for _ in range(4):
                    parent = parent.parent if parent else None
                    if parent is None:
                        break
                    parent_classes = parent.get("class", []) if hasattr(parent, "get") else []
                    if "notranslate" in parent_classes and "trackValue" not in parent_classes:
                        candidate = parent.get_text(" ", strip=True)
                        if not (candidate.startswith("(") and candidate.endswith(")")):
                            display = candidate
                        break
            display = re.sub(r"^(ft\.?\s+|feat\.?\s+)", "", display, flags=re.IGNORECASE)
            if not display:
                display = slug.replace("-", " ").title()
            slugs.append(slug)
            names.append(fix_mojibake(display))
        # Title: split raw_text on the last " - " to drop the artist prefix.
        # Many tracks are formatted "Artist - Title" on 1001TL; mashups use
        # "A vs. B - Title (Mashup)" with the hyphen still delimiting the
        # title. rsplit on the last ' - ' handles both.
        title = ""
        if " - " in raw_text:
            title = raw_text.rsplit(" - ", 1)[1].strip()
        elif raw_text:
            title = raw_text.strip()
        # Label: the first <span class="trackLabel">LABEL<a>...</a></span> in
        # the row. The label text is the span's content before the nested
        # icon-only <a>. Some rows omit the label entirely.
        label = ""
        label_span = row.select_one("span.trackLabel")
        if label_span is not None:
            # Clone and strip nested <a> icons so only the plain label text remains.
            label_copy = BeautifulSoup(str(label_span), "html.parser").select_one("span.trackLabel")
            if label_copy is not None:
                for sub in label_copy.select("a"):
                    sub.decompose()
                # No separator between text nodes: when 1001TL nests an icon
                # <a> inside the label span (e.g. the external-link chevron),
                # using a space separator inserts a stray space where the <a>
                # was, producing 'SHEFFIELD TUNES (KONTOR )'. Concatenating
                # without a separator gives us 'SHEFFIELD TUNES (KONTOR)'.
                label = fix_mojibake(label_copy.get_text(strip=True))
        tracks.append(
            Track(
                start_ms=start_ms,
                raw_text=raw_text,
                artist_slugs=slugs,
                genres=genres,
                artist_names=names,
                title=title,
                label=label,
            )
        )
    return tracks


class TracklistSession:
    """Manages authenticated session with 1001tracklists.com."""

    def __init__(self, cookie_cache_path: Path | None = None,
                 source_cache=None, dj_cache=None, delay: float = 5):
        self._cookie_path = cookie_cache_path or DEFAULT_COOKIE_PATH
        self._source_cache = source_cache
        self._dj_cache = dj_cache
        self._delay = delay
        self._last_request_time: float = 0
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        })
        # (page_type, frozenset(missing)) pairs already reported at
        # WARNING this session. See _run_canary.
        self._canary_seen: set[tuple[str, frozenset[str]]] = set()

    def _run_canary(self, page_type: str, missing: list[str], url: str,
                    *extras: str) -> None:
        """Emit a WARNING when a scraped page is structurally broken.

        Dedupes by (page_type, frozenset(missing)) for the lifetime of
        this session so a bulk run over many pages with the same
        breakage emits one WARNING, not hundreds. Subsequent identical
        failures log at DEBUG so --debug still shows the full scope.
        """
        if not missing:
            return
        key = (page_type, frozenset(missing))
        if key in self._canary_seen:
            logger.debug(
                "Canary: suppressed duplicate %s breakage at %s",
                page_type, url,
            )
            return
        self._canary_seen.add(key)
        extras_str = " ".join(extras)
        logger.warning(
            "Scraping canary: %s missing selectors %s at %s %s",
            page_type, missing, url, extras_str,
        )

    def throttle(self) -> None:
        """Sleep only the remaining delay since the last request.

        If enough time has already passed (e.g. user was choosing interactively),
        returns immediately instead of adding a redundant wait.
        """
        if self._last_request_time:
            elapsed = time.monotonic() - self._last_request_time
            remaining = self._delay - elapsed
            if remaining > 0:
                time.sleep(remaining)

    def login(self, email: str, password: str) -> None:
        """Login or restore cached session. Raises AuthenticationError on failure."""
        # Try restoring cached cookies first
        if self._restore_cookies(email):
            if self._validate_session():
                return

        # Visit site first to get initial cookies (guid)
        self._request("GET", f"{BASE_URL}/")

        # Fresh login
        resp = self._request("POST", f"{BASE_URL}/action/login.html", data={
            "email": email,
            "password": password,
            "referer": f"{BASE_URL}/",
        })

        if resp.status_code != 200:
            raise AuthenticationError(f"Login returned status {resp.status_code}")

        # Verify we got session cookies
        cookies = {c.name: c for c in self._session.cookies}
        if "sid" not in cookies or "uid" not in cookies:
            raise AuthenticationError("Login succeeded but missing session cookies")

        if not self._validate_session():
            raise AuthenticationError("Login succeeded but session validation failed")

        self._save_cookies(email)

    def search(self, query: str, duration_minutes: int = 0, year: str | None = None) -> list[SearchResult]:
        """Search 1001Tracklists for matching tracklists.

        Returns list of unscored SearchResult objects.
        """
        data = {
            "main_search": query,
            "search_selection": "9",
            "filterObject": "9",
            "orderby": "added",
        }

        if year:
            data["startDate"] = f"{year}-01-01"
            data["endDate"] = f"{year}-12-31"

        logger.debug("Search params: %s", {k: v for k, v in data.items() if k != "main_search"})

        resp = self._request("POST", f"{BASE_URL}/search/result.php", data=data,
                             headers={"Referer": f"{BASE_URL}/search/"})

        logger.debug("Search response: status=%d, length=%d, has_bItm=%s", resp.status_code, len(resp.text), "bItm" in resp.text)

        self._run_canary(
            "search results",
            canary.check_search_results(resp.text),
            f"{BASE_URL}/search/result.php",
            f"(query='{query}')",
        )

        results = self._parse_search_results(resp.text)
        return results

    def export_tracklist(
        self,
        tracklist_id: str,
        full_url: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> TracklistExport:
        """Fetch tracklist data (timestamps + track titles).

        If *on_progress* is provided it's invoked exactly once, after the
        tracklist page HTML has been parsed and the linked DJ list is known,
        before any per-DJ profile fetch. The message format is
        "Fetching tracklist ({N} DJs)".

        Raises ExportError on failure.
        """
        # First fetch the tracklist page to get the actual URL
        page_url = full_url or f"{BASE_URL}/tracklist/{tracklist_id}/"
        page_resp = self._request("GET", page_url)
        actual_url = page_resp.url  # After redirects

        # Parse the page once; all four tracklist-page parsers share this soup.
        page_soup = _to_soup(page_resp.text)

        # Structural canary: flag up-front if 1001TL changed the markup
        # in ways that would silently drain data from the parsers below.
        self._run_canary("tracklist page",
                         canary.check_tracklist_page(page_resp.text),
                         actual_url)

        # Export via AJAX
        resp = self._request("POST", f"{BASE_URL}/ajax/export_data.php", data={
            "object": "tracklist",
            "idTL": tracklist_id,
        }, headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": actual_url,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": BASE_URL,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        })

        try:
            result = resp.json()
        except (json.JSONDecodeError, ValueError):
            raise ExportError(f"Invalid JSON response from export API")

        if not result.get("success"):
            raise ExportError(result.get("message", "Export failed"))

        raw_data = result.get("data", "")
        lines = [line for line in raw_data.split("\n") if line.strip()]

        # Extract title from first line or page
        title_match = re.search(r"<title>([^<]+)</title>", page_resp.text)
        title = title_match.group(1).strip() if title_match else ""
        # Clean up common suffixes
        title = re.sub(r"\s*\|.*$", "", title)
        title = re.sub(r"\s*-\s*1001Tracklists$", "", title)
        title = _html_decode(title)

        # Normalize URL to short form
        short_url = f"{BASE_URL}/tracklist/{tracklist_id}/"

        # Extract enrichment metadata from page HTML
        genres = _extract_genres(page_soup)
        if genres:
            logger.info("Genres: %s", genres)

        # Parse structured h1 for stage, source, and DJ artist metadata
        h1_el = page_soup.find("h1")
        stage_text = ""
        dj_artists: list[tuple[str, str]] = []
        sources_by_type: dict[str, list[str]] = {}
        country = ""
        location = ""
        source_type_str = ""
        h1_date = ""
        if h1_el is not None:
            h1_info = _parse_h1_structure(h1_el.decode_contents())
            stage_text = h1_info["stage_text"]
            dj_artists = h1_info["dj_artists"]
            if h1_info.get("country"):
                country = h1_info["country"]
            if h1_info.get("location"):
                location = h1_info["location"]
            if h1_info.get("date"):
                h1_date = h1_info["date"]

            if h1_info["sources"] and self._source_cache:
                for sid, slug, display_name in h1_info["sources"]:
                    if not self._source_cache.get(sid):
                        self.throttle()
                        info = self.fetch_source_info(sid, slug)
                        self._source_cache.put(sid, info)
                        logger.info("Cached source: %s = %s (%s)", display_name, info["type"], info["country"])

                sources_by_type = self._source_cache.group_by_type(
                    [s[0] for s in h1_info["sources"]]
                )

                # Derive country and source_type from the primary source
                for stype in ("Open Air / Festival", "Event Location", "Club",
                              "Conference", "Concert / Live Event", "Event Promoter"):
                    if stype in sources_by_type:
                        source_type_str = stype
                        for sid, _slug, _name in h1_info["sources"]:
                            cached = self._source_cache._data.get(sid)
                            if cached and cached.get("type") == stype:
                                country = cached.get("country", "")
                                break
                        break

        # Fetch DJ profiles and populate cache (skip already-cached DJs)
        dj_artwork_url = ""
        dj_slugs = [slug for slug, _name in dj_artists] if dj_artists else _extract_dj_slugs(page_soup)
        dj_name_map = {slug: name for slug, name in dj_artists}
        if on_progress:
            on_progress(f"Fetching tracklist ({len(dj_slugs)} DJs)")
        for i, dj_slug in enumerate(dj_slugs):
            cached = self._dj_cache.get(dj_slug) if self._dj_cache else None
            if cached:
                profile = cached
            else:
                if i > 0:
                    self.throttle()
                profile = self._fetch_dj_profile(dj_slug)
                if self._dj_cache:
                    display_name = dj_name_map.get(dj_slug, dj_slug)
                    entry = {"name": display_name, **profile}
                    self._dj_cache.put(dj_slug, entry)
                    logger.info("Cached DJ profile: %s", display_name)
            if i == 0 and profile.get("artwork_url"):
                dj_artwork_url = profile["artwork_url"]
                logger.info("DJ artwork: %s", dj_artwork_url)

        tracks = _parse_tracks(page_soup)

        # Suppress the h1-derived location when a linked source already
        # carries authoritative location info (festival, venue, conference,
        # radio channel). The cached source entry wins in those cases.
        if any(t in sources_by_type for t in LOCATION_BEARING_TYPES):
            location = ""

        return TracklistExport(
            lines=lines, url=short_url, title=title,
            genres=genres, dj_artists=dj_artists,
            dj_artwork_url=dj_artwork_url,
            stage_text=stage_text, sources_by_type=sources_by_type,
            country=country, location=location,
            source_type=source_type_str,
            tracks=tracks,
            date=h1_date,
        )

    def _request(self, method: str, url: str, data: dict | None = None,
                 headers: dict | None = None, max_retries: int = 5) -> requests.Response:
        """Make HTTP request with retry logic and rate limit handling."""
        for attempt in range(max_retries):
            try:
                if method.upper() == "GET":
                    resp = self._session.get(url, headers=headers, timeout=30)
                else:
                    resp = self._session.post(url, data=data, headers=headers, timeout=30)

                # Rate limit detection
                if resp.status_code == 429 or _is_rate_limited(resp.text):
                    if attempt < max_retries - 1:
                        wait = 30
                        time.sleep(wait)
                        continue
                    raise RateLimitError("Rate limited — solve captcha at 1001tracklists.com in your browser")

                # Transient errors
                if resp.status_code in (502, 503, 504):
                    if attempt < max_retries - 1:
                        wait = min(2 ** attempt + random.uniform(0, 3), 30)
                        time.sleep(wait)
                        continue
                    raise TracklistError(
                        f"Server error {resp.status_code} after {max_retries} attempts"
                    )

                # Force UTF-8 decoding for every 1001TL response. The server
                # serves UTF-8 but does not always include an explicit
                # charset= on Content-Type, which makes requests default to
                # ISO-8859-1 per RFC 7231. On Windows that default produces
                # mojibake in chapter titles and per-chapter tags.
                resp.encoding = "utf-8"
                self._last_request_time = time.monotonic()
                return resp

            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    wait = min(2 ** attempt + random.uniform(0, 3), 30)
                    time.sleep(wait)
                    continue
                raise TracklistError(f"Request failed after {max_retries} attempts: {e}")

        raise TracklistError("Request failed: max retries exceeded")

    def _parse_search_results(self, html: str) -> list[SearchResult]:
        """Parse search result HTML into SearchResult objects."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResult] = []
        seen_ids: set[str] = set()

        for card in soup.select(".bItm:not(.bItmH)"):
            link = card.select_one('a[href^="/tracklist/"]')
            if link is None:
                continue
            href_raw = link.get("href", "")
            href = href_raw if isinstance(href_raw, str) else ""
            m = re.match(r"/tracklist/([^/]+)/", href)
            if not m:
                continue
            tl_id = m.group(1)
            title = _html_decode(link.get_text(strip=True))

            if tl_id in seen_ids:
                continue
            if title in ("Previous", "Next", "First", "Last"):
                continue
            seen_ids.add(tl_id)

            duration_mins = None
            dur_el = card.select_one('[title="play time"]')
            if dur_el is not None:
                dur_text = dur_el.get_text(" ", strip=True)
                duration_mins = _parse_duration_string(dur_text)

            date = None
            date_el = card.select_one('[title="tracklist date"]')
            if date_el is not None:
                date_str = date_el.get_text(" ", strip=True)
                date = _normalize_date(date_str)

            results.append(SearchResult(
                id=tl_id,
                title=title,
                url=f"{BASE_URL}{href}",
                duration_mins=duration_mins,
                date=date,
            ))

        return results

    def fetch_source_info(self, source_id: str, slug: str) -> dict:
        """Fetch metadata from a /source/ page. Returns {name, slug, type, country}."""
        from bs4 import BeautifulSoup
        url = f"{BASE_URL}/source/{source_id}/{slug}/index.html"
        resp = self._request("GET", url, max_retries=2)
        self._run_canary(
            "source info",
            canary.check_source_info(resp.text),
            url,
            f"(source='{source_id}/{slug}')",
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        type_el = soup.select_one("div.cRow > div.mtb5")
        source_type = type_el.get_text(strip=True) if type_el else ""

        flag_img = soup.select_one('img[src*="flags/"]')
        country = ""
        if flag_img is not None:
            alt = flag_img.get("alt", "")
            country = (alt if isinstance(alt, str) else "").strip()

        name_el = soup.select_one("div.h")
        name = name_el.get_text(strip=True) if name_el else slug.replace("-", " ").title()

        return {"name": name, "slug": slug, "type": source_type, "country": country}

    def _fetch_dj_profile(self, dj_slug: str) -> dict:
        """Fetch and parse a /dj/ profile page for artwork, aliases, and groups.

        Returns dict with artwork_url, aliases, and member_of.
        On failure returns empty defaults.
        """
        empty = {"artwork_url": "", "aliases": [], "member_of": []}
        url = f"{BASE_URL}/dj/{dj_slug}/index.html"
        try:
            resp = self._request("GET", url, max_retries=2)
            self._run_canary(
                "DJ profile",
                canary.check_dj_profile(resp.text),
                url,
                f"(slug='{dj_slug}')",
            )
            return _parse_dj_profile(resp.text)
        except TracklistError:
            logger.debug("Failed to fetch DJ page for %s", dj_slug)
        return empty

    def _validate_session(self) -> bool:
        """Check if current session is still valid."""
        try:
            resp = self._session.get(f"{BASE_URL}/my/", timeout=15,
                                     allow_redirects=True)
            text = resp.text.lower()
            if "login-form" in text or "please log in" in text:
                return False
            if "logout" in text or "/my/" in resp.url:
                return True
            return False
        except (requests.RequestException, OSError) as e:
            logger.debug("Session validation failed: %s", e)
            return False

    def _save_cookies(self, email: str) -> None:
        """Save session cookies to cache file."""
        try:
            cookies_list = []
            for cookie in self._session.cookies:
                cookies_list.append({
                    "Name": cookie.name,
                    "Value": cookie.value,
                    "Domain": cookie.domain,
                    "Path": cookie.path,
                    "Expires": cookie.expires,
                })

            cache = {
                "Email": email,
                "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                "Cookies": cookies_list,
            }

            self._cookie_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except (OSError, TypeError) as e:
            logger.debug("Cookie save failed: %s", e)

    def _restore_cookies(self, email: str) -> bool:
        """Restore cookies from cache. Returns True if cache was valid."""
        try:
            if not self._cookie_path.exists():
                return False

            cache = json.loads(self._cookie_path.read_text(encoding="utf-8"))

            if cache.get("Email") != email:
                return False

            # Check expiration
            for cookie_data in cache.get("Cookies", []):
                expires = cookie_data.get("Expires")
                if expires and isinstance(expires, (int, float)):
                    if time.time() > expires:
                        return False

            # Restore cookies
            for cookie_data in cache.get("Cookies", []):
                self._session.cookies.set(
                    cookie_data["Name"],
                    cookie_data["Value"],
                    domain=cookie_data.get("Domain", ""),
                    path=cookie_data.get("Path", "/"),
                )

            # Verify required cookies exist
            names = {c.name for c in self._session.cookies}
            return "sid" in names and "uid" in names

        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug("Cookie restore failed: %s", e)
            return False


LOCATION_BEARING_TYPES: tuple[str, ...] = (
    "Open Air / Festival",
    "Event Location",
    "Club",
    "Conference",
    "Radio Channel",
)
"""Source types that carry authoritative location information. When any of
these appears in sources_by_type, the h1-derived location string is
suppressed because the source cache entry is the canonical source."""


_H1_FALLBACK_COUNTRIES: frozenset[str] = frozenset({
    "United States", "USA", "United Kingdom", "UK", "Netherlands", "Germany",
    "Belgium", "Spain", "France", "Italy", "Portugal", "Switzerland", "Austria",
    "Poland", "Czech Republic", "Hungary", "Romania", "Bulgaria", "Greece",
    "Turkey", "Sweden", "Norway", "Denmark", "Finland", "Iceland", "Ireland",
    "Croatia", "Serbia", "Slovenia", "Slovakia", "Ukraine", "Russia",
    "Australia", "New Zealand", "Japan", "South Korea", "China", "India",
    "Thailand", "Vietnam", "Indonesia", "Singapore", "Malaysia", "Philippines",
    "Canada", "Mexico", "Brazil", "Argentina", "Chile", "Colombia", "Peru",
    "Uruguay", "Ecuador", "Venezuela", "South Africa", "Egypt", "Morocco",
    "United Arab Emirates", "UAE", "Israel", "Lebanon", "Saudi Arabia",
})


def _parse_h1_structure(h1_html: str) -> dict:
    """Parse the structured <h1> content from a tracklist page.

    Returns dict with:
        dj_artists: list of (slug, display_name) tuples from /dj/ links before @
        stage_text: str, plain text between @ and first /source/ link
        sources: list of (id, slug, display_name) tuples from /source/ links
        country: str, country parsed from the trailing tail of the h1 (the
            text after the last /source/ link, or the whole post-@ string
            when no source links are present). Empty when the tail does not
            end in a known country name.
        location: str, the remaining middle text from the tail after
            country and trailing ISO date are stripped. Empty when the tail
            carries nothing other than country + date.
        date: str, ISO date (YYYY-MM-DD) captured from the trailing tail of
            the h1. Empty when the tail carries no date. Used as a fallback
            event-date source when the search-results "tracklist date" field
            is missing.
    """
    result: dict = {"stage_text": "", "sources": [], "dj_artists": [],
                    "country": "", "location": "", "date": ""}

    if "@" not in h1_html:
        return result

    before_at, after_at = h1_html.split("@", 1)

    from bs4 import BeautifulSoup

    # DJ anchors in the before-@ fragment
    before_soup = BeautifulSoup(before_at, "html.parser")
    for a in before_soup.select('a[href^="/dj/"]'):
        href_raw = a.get("href", "")
        href = href_raw if isinstance(href_raw, str) else ""
        m = re.match(r"/dj/([^/]+)/", href)
        if not m:
            continue
        result["dj_artists"].append(
            (m.group(1), _html_decode(a.get_text(strip=True)))
        )

    # Source anchors in the after-@ fragment. BS4 gives us the data; a
    # lenient quote-style-agnostic regex over the raw after_at string
    # gives us the character offsets the tail/stage algorithm needs.
    after_soup = BeautifulSoup(after_at, "html.parser")
    sources: list[tuple[str, str, str]] = []
    for a in after_soup.select('a[href^="/source/"]'):
        href_raw = a.get("href", "")
        href = href_raw if isinstance(href_raw, str) else ""
        m = re.match(r"/source/([^/]+)/([^/]+)/", href)
        if not m:
            continue
        sources.append((m.group(1), m.group(2),
                        _html_decode(a.get_text(strip=True))))
    result["sources"] = sources

    source_matches = list(re.finditer(
        r'<a[^>]*href=["\']/source/[^/"\']+/[^/"\']+/[^"\']*["\'][^>]*>[^<]+</a>',
        after_at,
    ))

    first_source = source_matches[0] if source_matches else None
    if first_source:
        plain = after_at[:first_source.start()]
    else:
        plain = after_at

    plain = re.sub(r"<[^>]+>", "", plain).strip().rstrip(",").strip()

    if not plain and first_source:
        # The first content after @ is a source link (e.g. "Resistance").
        # The stage may be that source + trailing text before the next comma
        # (e.g. "Resistance Megastructure"). Strip all tags from after_at,
        # take the first comma-delimited segment, and check whether it
        # differs from any bare source display name. If it does, the source
        # link is part of a compound stage name.
        all_text = re.sub(r"<[^>]+>", "", after_at).strip()
        first_segment = all_text.split(",")[0].strip()
        source_names = {s[2] for s in sources}
        if first_segment and first_segment not in source_names:
            plain = first_segment

    # Tail parsing: text after the last /source/ link (or the full post-@
    # text when no source links are present). Strip HTML, a leading comma
    # left by the preceding link, and a trailing ISO date. If the final
    # comma-segment is a known country, lift it into result["country"];
    # whatever remains is result["location"].
    if source_matches:
        tail_raw = after_at[source_matches[-1].end():]
    else:
        tail_raw = after_at

    tail = re.sub(r"<[^>]+>", "", tail_raw)
    tail = tail.lstrip().lstrip(",").strip()
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})\s*$", tail)
    if date_match:
        result["date"] = date_match.group(1)
    tail = re.sub(r"[,\s]*\d{4}-\d{2}-\d{2}\s*$", "", tail).strip()

    if "," in tail:
        head, _, last = tail.rpartition(",")
        last = last.strip()
        if last in _H1_FALLBACK_COUNTRIES:
            result["country"] = last
            tail = head.strip().rstrip(",").strip()
    elif tail in _H1_FALLBACK_COUNTRIES:
        result["country"] = tail
        tail = ""

    result["location"] = _html_decode(tail)

    # When no source links exist, the "stage" and the tail refer to the same
    # post-@ text; expose the cleaned location as the stage so the trailing
    # country/date does not bleed into stage_text.
    if not source_matches:
        plain = tail

    result["stage_text"] = _html_decode(plain)

    return result


def _extract_genres(html) -> list[str]:
    """Extract genres from itemprop="genre" structured data on the page.

    Accepts raw HTML or an already-parsed BeautifulSoup so export_tracklist
    can share one parse with the other tracklist-page parsers.

    1001TL embeds genre metadata as <meta itemprop="genre" content="..."> tags:
    one tracklist-level genre (near numTracks), plus per-track genres.
    """
    soup = _to_soup(html)
    seen: set[str] = set()
    genres: list[str] = []
    for meta in soup.select('meta[itemprop="genre"]'):
        content = meta.get("content", "")
        if not content:
            continue
        genre = _html_decode(content)
        lower = genre.lower()
        if lower in seen or lower == "tracklist":
            continue
        seen.add(lower)
        genres.append(genre)
    return genres


def _parse_dj_profile(html: str) -> dict:
    """Parse a DJ profile page HTML for artwork, aliases, and group memberships.

    Returns dict with:
        artwork_url: str, og:image URL (empty if placeholder)
        aliases: list of {"slug": str, "name": str}
        member_of: list of {"slug": str, "name": str}
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    artwork_url = ""
    og = soup.select_one('meta[property="og:image"]')
    if og is not None:
        content = og.get("content", "")
        url = content if isinstance(content, str) else ""
        if url and "/images/static/" not in url and "logo" not in url.lower() and "default" not in url:
            artwork_url = _maximize_artwork_url(url)

    def _extract_section(section_header: str) -> list[dict]:
        """Collect /dj/ links from the siblings between this section's
        <div class="h">HEADER</div> and the next <div class="h">, which
        frames every section on the profile page."""
        header = None
        for h in soup.select("div.h"):
            if h.get_text(strip=True) == section_header:
                header = h
                break
        if header is None:
            return []
        entries: list[dict] = []
        seen: set[str] = set()
        for sib in header.find_next_siblings():
            if getattr(sib, "name", None) == "div" and "h" in (sib.get("class") or []):
                break
            for a in sib.select('a[href^="/dj/"]'):
                href_raw = a.get("href", "")
                href = href_raw if isinstance(href_raw, str) else ""
                m = re.match(r"/dj/([^/]+)/index\.html", href)
                if not m:
                    continue
                slug = m.group(1)
                if slug in seen:
                    continue
                seen.add(slug)
                entries.append({
                    "slug": slug,
                    "name": _html_decode(a.get_text(strip=True)),
                })
        return entries

    return {
        "artwork_url": artwork_url,
        "aliases": _extract_section("Aliases"),
        "member_of": _extract_section("Member Of"),
    }


def _extract_dj_slugs(html) -> list[str]:
    """Extract DJ slugs from /dj/<slug>/ or /dj/<slug>/index.html links, deduplicated.

    Accepts raw HTML or an already-parsed BeautifulSoup so export_tracklist
    can share one parse with the other tracklist-page parsers.
    """
    soup = _to_soup(html)
    slugs: list[str] = []
    seen: set[str] = set()
    for a in soup.select('a[href^="/dj/"]'):
        href_raw = a.get("href", "")
        href = href_raw if isinstance(href_raw, str) else ""
        m = re.match(r"/dj/([^/]+)/(?:index\.html)?$", href)
        if not m:
            continue
        slug = m.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
    return slugs


def _to_soup(value):
    """Return a BeautifulSoup for the given value.

    Accepts a raw HTML string or an already-parsed BeautifulSoup. When
    called with a soup, returns it unchanged so the tracklist-page
    parsers can share one parse across export_tracklist without paying
    the cost of reparsing 200 KB of HTML per parser.
    """
    from bs4 import BeautifulSoup
    if isinstance(value, str):
        return BeautifulSoup(value, "html.parser")
    return value


def _maximize_artwork_url(url: str) -> str:
    """Rewrite artwork URL to request the highest available resolution."""
    if not url:
        return url
    # SoundCloud: -t500x500.jpg -> -original.jpg (true source)
    if "sndcdn.com" in url:
        return re.sub(r"-t\d+x\d+\.", "-original.", url)
    # Squarespace: strip ?format=NNNw to get original
    if "squarespace-cdn.com" in url:
        return re.sub(r"\?format=\d+w$", "", url)
    return url


def _is_rate_limited(text: str) -> bool:
    """Check response body for rate limit indicators."""
    lower = text.lower()
    return "sent too many requests" in lower or "captcha to unblock" in lower


def _parse_duration_string(dur_str: str) -> int | None:
    """Parse "1h 15m" or "58m" to minutes."""
    if not dur_str or not dur_str.strip():
        return None
    total = 0
    h_match = re.search(r"(\d+)h", dur_str)
    m_match = re.search(r"(\d+)m", dur_str)
    if h_match:
        total += int(h_match.group(1)) * 60
    if m_match:
        total += int(m_match.group(1))
    return total if total > 0 else None


def _html_decode(text: str) -> str:
    """Decode HTML entities (named, numeric, and hex)."""
    return html_mod.unescape(text)


def _normalize_date(date_str: str) -> str | None:
    """Try to normalize a date string to YYYY-MM-DD."""
    # Already in YYYY-MM-DD format
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str
    # Try common formats
    import datetime
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
