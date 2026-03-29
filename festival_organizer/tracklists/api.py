"""1001Tracklists API — session management, search, and tracklist export."""
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
    event_artwork_url: str = ""
    genres: list[str] = field(default_factory=list)
    dj_artwork_url: str = ""


class TracklistSession:
    """Manages authenticated session with 1001tracklists.com."""

    def __init__(self, cookie_cache_path: Path | None = None):
        self._cookie_path = cookie_cache_path or DEFAULT_COOKIE_PATH
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

        if duration_minutes > 0:
            data["duration"] = str(max(1, duration_minutes - 3))

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

        # Normalize URL to short form
        short_url = f"{BASE_URL}/tracklist/{tracklist_id}/"

        # Extract enrichment metadata from page HTML
        event_artwork_url = _extract_event_artwork(page_resp.text)
        genres = _extract_genres(page_resp.text)
        dj_slugs = _extract_dj_slugs(page_resp.text)
        if event_artwork_url:
            logger.info("Event artwork: %s", event_artwork_url)
        if genres:
            logger.info("Genres: %s", genres)

        # Fetch DJ artwork from first DJ's profile page
        dj_artwork_url = ""
        if dj_slugs:
            dj_artwork_url = self._fetch_dj_artwork(dj_slugs[0])
            if dj_artwork_url:
                logger.info("DJ artwork: %s", dj_artwork_url)

        return TracklistExport(
            lines=lines, url=short_url, title=title,
            event_artwork_url=event_artwork_url, genres=genres,
            dj_artwork_url=dj_artwork_url,
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

    def _fetch_dj_artwork(self, dj_slug: str) -> str:
        """Fetch og:image from a /dj/ profile page. Returns URL or empty string."""
        try:
            resp = self._request("GET", f"{BASE_URL}/dj/{dj_slug}/index.html", max_retries=2)
            m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', resp.text)
            if m:
                url = m.group(1)
                # Skip default/placeholder images
                if "default" not in url:
                    return url
        except TracklistError:
            logger.debug("Failed to fetch DJ page for %s", dj_slug)
        return ""

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


_NAV_GENRES = frozenset({
    "electronic", "house", "techno", "trance", "bass", "dubstep",
    "drum-and-bass", "hardstyle", "hardcore",
})


def _extract_event_artwork(html: str) -> str:
    """Extract event artwork URL from og:image meta tag or artworkTop CSS."""
    # Try og:image first
    m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
    if m:
        return m.group(1)
    # Fallback: artworkTop background-image in CSS (cdn.1001tracklists.com artwork)
    m = re.search(r"#artworkTop\s*\{[^}]*background-image:\s*url\('([^']+)'\)", html)
    if m:
        return m.group(1)
    # Also try Medium-size artwork variant
    m = re.search(
        r"url\('(https://cdn\.1001tracklists\.com/images/artworks/[^']*-Medium\.[^']+)'\)",
        html,
    )
    if m:
        return m.group(1)
    return ""


def _extract_genres(html: str) -> list[str]:
    """Extract genre slugs from /genre/<slug>/ links, deduplicate, filter nav genres."""
    matches = re.findall(r'href="/genre/([^/]+)/"', html)
    seen = set()
    genres = []
    for slug in matches:
        lower = slug.lower()
        if lower in seen or lower in _NAV_GENRES:
            continue
        seen.add(lower)
        # Convert slug to title case: "melodic-house-techno" -> "Melodic House Techno"
        genres.append(slug.replace("-", " ").title())
    return genres


def _extract_dj_slugs(html: str) -> list[str]:
    """Extract DJ slugs from /dj/<slug>/ links, deduplicated, preserving order."""
    matches = re.findall(r'href="/dj/([^/]+)/"', html)
    seen = set()
    slugs = []
    for slug in matches:
        if slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


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
    """Decode common HTML entities."""
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&apos;", "'")
    return text


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
