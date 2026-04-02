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

import requests

logger = logging.getLogger(__name__)

from festival_organizer.tracklists.scoring import SearchResult

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


class TracklistSession:
    """Manages authenticated session with 1001tracklists.com."""

    def __init__(self, cookie_cache_path: Path | None = None,
                 source_cache=None, dj_cache=None, delay: float = 5):
        self._cookie_path = cookie_cache_path or DEFAULT_COOKIE_PATH
        self._source_cache = source_cache
        self._dj_cache = dj_cache
        self._delay = delay
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        })

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

        results = self._parse_search_results(resp.text)

        if not results and resp.text:
            logger.debug("Search returned HTML (%d chars) but parsed 0 results — site format may have changed", len(resp.text))

        return results

    def export_tracklist(self, tracklist_id: str, full_url: str | None = None) -> TracklistExport:
        """Fetch tracklist data (timestamps + track titles).

        Raises ExportError on failure.
        """
        # First fetch the tracklist page to get the actual URL
        page_url = full_url or f"{BASE_URL}/tracklist/{tracklist_id}/"
        page_resp = self._request("GET", page_url)
        actual_url = page_resp.url  # After redirects

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
        genres = _extract_genres(page_resp.text)
        if genres:
            logger.info("Genres: %s", genres)

        # Parse structured h1 for stage, source, and DJ artist metadata
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", page_resp.text, re.DOTALL)
        stage_text = ""
        dj_artists: list[tuple[str, str]] = []
        sources_by_type: dict[str, list[str]] = {}
        if h1_match:
            h1_info = _parse_h1_structure(h1_match.group(1))
            stage_text = h1_info["stage_text"]
            dj_artists = h1_info["dj_artists"]

            if h1_info["sources"] and self._source_cache:
                for sid, slug, display_name in h1_info["sources"]:
                    if not self._source_cache.get(sid):
                        time.sleep(self._delay)
                        info = self.fetch_source_info(sid, slug)
                        self._source_cache.put(sid, info)
                        logger.info("Cached source: %s = %s (%s)", display_name, info["type"], info["country"])

                sources_by_type = self._source_cache.group_by_type(
                    [s[0] for s in h1_info["sources"]]
                )

        # Fetch DJ profiles and populate cache (skip already-cached DJs)
        dj_artwork_url = ""
        dj_slugs = [slug for slug, _name in dj_artists] if dj_artists else _extract_dj_slugs(page_resp.text)
        dj_name_map = {slug: name for slug, name in dj_artists}
        for i, dj_slug in enumerate(dj_slugs):
            cached = self._dj_cache.get(dj_slug) if self._dj_cache else None
            if cached:
                profile = cached
            else:
                if i > 0:
                    time.sleep(self._delay)
                profile = self._fetch_dj_profile(dj_slug)
                if self._dj_cache:
                    display_name = dj_name_map.get(dj_slug, dj_slug)
                    entry = {"name": display_name, **profile}
                    self._dj_cache.put(dj_slug, entry)
                    logger.info("Cached DJ profile: %s", display_name)
            if i == 0 and profile.get("artwork_url"):
                dj_artwork_url = profile["artwork_url"]
                logger.info("DJ artwork: %s", dj_artwork_url)

        return TracklistExport(
            lines=lines, url=short_url, title=title,
            genres=genres, dj_artists=dj_artists,
            dj_artwork_url=dj_artwork_url,
            stage_text=stage_text, sources_by_type=sources_by_type,
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
        results = []
        seen_ids = set()

        # Split by result items (class may include extra names like "bItm action oItm")
        items = re.split(r'class="bItm\b(?!H)', html)

        for item in items[1:]:  # Skip content before first item
            # Extract title and URL
            link_match = re.search(
                r'<a\s+href="(/tracklist/([^/]+)/[^"]*)"[^>]*>([^<]+)</a>',
                item
            )
            if not link_match:
                continue

            url_path = link_match.group(1)
            tl_id = link_match.group(2)
            title = _html_decode(link_match.group(3).strip())

            # Skip duplicates and pagination
            if tl_id in seen_ids:
                continue
            if title in ("Previous", "Next", "First", "Last"):
                continue
            seen_ids.add(tl_id)

            # Extract duration
            duration_mins = None
            dur_match = re.search(
                r'title="play time"[^>]*>.*?</i>((?:\d+h\s*)?(?:\d+m)?)\s*</div>',
                item, re.DOTALL
            )
            if dur_match:
                duration_mins = _parse_duration_string(dur_match.group(1))

            # Extract date
            date = None
            date_match = re.search(
                r'title="tracklist date"[^>]*>.*?</i>([^<]+)</div>',
                item, re.DOTALL
            )
            if date_match:
                date_str = date_match.group(1).strip()
                # Try to normalize to YYYY-MM-DD
                date = _normalize_date(date_str)

            results.append(SearchResult(
                id=tl_id,
                title=title,
                url=f"{BASE_URL}{url_path}",
                duration_mins=duration_mins,
                date=date,
            ))

        return results

    def fetch_source_info(self, source_id: str, slug: str) -> dict:
        """Fetch metadata from a /source/ page. Returns {name, slug, type, country}."""
        url = f"{BASE_URL}/source/{source_id}/{slug}/index.html"
        resp = self._request("GET", url, max_retries=2)

        type_match = re.search(
            r'<div class="cRow">\s*<div class="mtb5">([^<]+)</div>', resp.text
        )
        source_type = type_match.group(1).strip() if type_match else ""

        flag_match = re.search(
            r'<img[^>]*flags/[^.]+\.png[^>]*alt="([^"]+)"', resp.text
        )
        country = flag_match.group(1).strip() if flag_match else ""

        name_match = re.search(r'<div class="h">\s*([^<]+)', resp.text)
        name = name_match.group(1).strip() if name_match else slug.replace("-", " ").title()

        return {"name": name, "slug": slug, "type": source_type, "country": country}

    def _fetch_dj_profile(self, dj_slug: str) -> dict:
        """Fetch and parse a /dj/ profile page for artwork, aliases, and groups.

        Returns dict with artwork_url, aliases, and member_of.
        On failure returns empty defaults.
        """
        empty = {"artwork_url": "", "aliases": [], "member_of": []}
        try:
            resp = self._request("GET", f"{BASE_URL}/dj/{dj_slug}/index.html", max_retries=2)
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


def _parse_h1_structure(h1_html: str) -> dict:
    """Parse the structured <h1> content from a tracklist page.

    Returns dict with:
        dj_artists: list of (slug, display_name) tuples from /dj/ links before @
        stage_text: str, plain text between @ and first /source/ link
        sources: list of (id, slug, display_name) tuples from /source/ links
    """
    result: dict = {"stage_text": "", "sources": [], "dj_artists": []}

    if "@" not in h1_html:
        return result

    before_at, after_at = h1_html.split("@", 1)

    # Extract /dj/ links from the before-@ part
    dj_pattern = re.compile(
        r'<a[^>]*href="/dj/([^/"]+)/[^"]*"[^>]*>([^<]+)</a>'
    )
    result["dj_artists"] = [
        (m.group(1), _html_decode(m.group(2).strip()))
        for m in dj_pattern.finditer(before_at)
    ]

    source_pattern = re.compile(
        r'<a[^>]*href="/source/([^/]+)/([^/]+)/[^"]*"[^>]*>([^<]+)</a>'
    )
    sources = [(m.group(1), m.group(2), _html_decode(m.group(3).strip()))
               for m in source_pattern.finditer(after_at)]
    result["sources"] = sources

    first_source = source_pattern.search(after_at)
    if first_source:
        plain = after_at[:first_source.start()]
    else:
        plain = after_at

    plain = re.sub(r"<[^>]+>", "", plain).strip().rstrip(",").strip()
    result["stage_text"] = _html_decode(plain)

    return result


def _extract_genres(html: str) -> list[str]:
    """Extract genres from itemprop="genre" structured data on the page.

    1001TL embeds genre metadata as <meta itemprop="genre" content="..."> tags:
    - One tracklist-level genre (near numTracks)
    - Per-track genres for each track in the tracklist
    """
    matches = re.findall(r'<meta\s+itemprop="genre"\s+content="([^"]+)"', html)
    seen = set()
    genres = []
    for genre in matches:
        genre = _html_decode(genre)
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
    # Extract artwork from og:image
    artwork_url = ""
    og_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
    if og_match:
        url = og_match.group(1)
        if "/images/static/" not in url and "logo" not in url.lower() and "default" not in url:
            artwork_url = _maximize_artwork_url(url)

    def _extract_section(section_header: str) -> list[dict]:
        """Extract /dj/ links from c ptb5 blocks following a section header."""
        # Find the header div, then collect links until the next header
        pattern = re.compile(
            r'<div\s+class="h">\s*' + re.escape(section_header) + r'\s*</div>'
            r'(.*?)'
            r'(?:<div\s+class="h">|$)',
            re.DOTALL,
        )
        match = pattern.search(html)
        if not match:
            return []
        block = match.group(1)
        link_pattern = re.compile(
            r'<a\s+href="/dj/([^/"]+)/index\.html"[^>]*>([^<]+)</a>'
        )
        entries = []
        for lm in link_pattern.finditer(block):
            entries.append({
                "slug": lm.group(1),
                "name": _html_decode(lm.group(2).strip()),
            })
        return entries

    aliases = _extract_section("Aliases")
    member_of = _extract_section("Member Of")

    return {"artwork_url": artwork_url, "aliases": aliases, "member_of": member_of}


def _extract_dj_slugs(html: str) -> list[str]:
    """Extract DJ slugs from /dj/<slug>/ or /dj/<slug>/index.html links, deduplicated."""
    matches = re.findall(r'href="/dj/([^/"]+)/(?:index\.html)?"', html)
    seen = set()
    slugs = []
    for slug in matches:
        if slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


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
    # YouTube/Google profile pics: s500 -> s800
    if "yt3.ggpht.com" in url:
        return re.sub(r"=s\d+", "=s800", url)
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
