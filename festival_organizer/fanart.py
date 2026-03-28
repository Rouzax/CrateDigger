"""fanart.tv and MusicBrainz integration for artist artwork.

Downloads HD ClearLOGOs and artist backgrounds from fanart.tv.
Artist images provided by fanart.tv (https://fanart.tv).
"""
import json
import logging
import re
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

FANART_BASE_URL = "https://webservice.fanart.tv/v3.2"
MB_BASE_URL = "https://musicbrainz.org/ws/2"
USER_AGENT = "CrateDigger/1.0 (festival set organizer)"


# --- Exceptions ---

class FanartError(Exception):
    """Base error for fanart operations."""


class MusicBrainzError(FanartError):
    """MusicBrainz lookup failed."""


class FanartAPIError(FanartError):
    """fanart.tv API call failed."""


# --- MBID Cache ---

class MBIDCache:
    """Persistent artist-name-to-MBID mapping.

    Keys are lowercased artist names. Values are MBID strings or None
    (negative cache for artists not found on MusicBrainz).
    """

    def __init__(self, cache_dir: Path | None = None):
        self._dir = cache_dir or (Path.home() / ".cratedigger")
        self._path = self._dir / "mbid_cache.json"
        self._data: dict[str, str | None] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not load MBID cache: %s", e)
                self._data = {}

    def _save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self, artist: str) -> str | None:
        """Return cached MBID or None. Raises KeyError if not cached."""
        key = artist.lower()
        if key not in self._data:
            raise KeyError(artist)
        return self._data[key]

    def has(self, artist: str) -> bool:
        """True if artist is cached (even if MBID is None / negative cache)."""
        return artist.lower() in self._data

    def put(self, artist: str, mbid: str | None) -> None:
        """Cache an artist-to-MBID mapping. None = not found (negative cache)."""
        self._data[artist.lower()] = mbid
        self._save()


# --- MusicBrainz Client ---

_last_mb_request: float = 0.0


def _mb_rate_limit() -> None:
    """Enforce MusicBrainz 1 req/sec rate limit."""
    global _last_mb_request
    elapsed = time.monotonic() - _last_mb_request
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_mb_request = time.monotonic()


def lookup_mbid(artist_name: str, cache: MBIDCache) -> str | None:
    """Look up MusicBrainz ID for an artist name. Uses cache, respects rate limit."""
    if cache.has(artist_name):
        mbid = cache.get(artist_name)
        if mbid:
            logger.debug("MBID cache hit: %s -> %s", artist_name, mbid)
        else:
            logger.debug("MBID cache hit (negative): %s", artist_name)
        return mbid

    logger.info("Looking up MusicBrainz ID for: %s", artist_name)
    mbid = _mb_search(artist_name)
    cache.put(artist_name, mbid)
    if mbid:
        logger.info("Found MBID: %s -> %s", artist_name, mbid)
    else:
        logger.info("No MusicBrainz match for: %s", artist_name)
    return mbid


def _mb_search(artist_name: str) -> str | None:
    """Query MusicBrainz search API. Returns best-match MBID or None."""
    _mb_rate_limit()

    url = f"{MB_BASE_URL}/artist/"
    params = {"query": f'artist:"{artist_name}"', "fmt": "json", "limit": "5"}
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 503:
                wait = 2 ** attempt + 1
                logger.debug("MusicBrainz 503, retrying in %ds", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            artists = data.get("artists", [])
            if not artists:
                return None
            best = artists[0]
            score = best.get("score", 0)
            if score >= 80:
                return best["id"]
            logger.debug("Best match score %d < 80 for '%s'", score, artist_name)
            return None
        except requests.RequestException as e:
            if attempt < 2:
                time.sleep(2 ** attempt + 1)
                continue
            raise MusicBrainzError(f"MusicBrainz lookup failed for '{artist_name}': {e}") from e
    return None


# --- fanart.tv Client ---

def fetch_artist_images(
    mbid: str, project_api_key: str, personal_api_key: str = "",
) -> dict | None:
    """Fetch artist images from fanart.tv API v3.2. Returns parsed JSON or None on 404."""
    url = f"{FANART_BASE_URL}/music/{mbid}"
    headers = {"api-key": project_api_key}
    if personal_api_key:
        headers["client-key"] = personal_api_key

    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 404:
                return None
            if resp.status_code >= 500:
                wait = 2 ** attempt + 1
                logger.debug("fanart.tv %d, retrying in %ds", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt < 2:
                time.sleep(2 ** attempt + 1)
                continue
            raise FanartAPIError(f"fanart.tv request failed for MBID {mbid}: {e}") from e
    return None


# --- Image Selection ---

def pick_best_logo(images: list[dict]) -> dict | None:
    """Pick the best HD ClearLOGO — prefer English or language-neutral, highest likes."""
    if not images:
        return None
    preferred = [img for img in images if img.get("lang") in ("en", "")]
    pool = preferred if preferred else images
    return max(pool, key=lambda img: int(img.get("likes", "0")))


def pick_best_background(images: list[dict]) -> dict | None:
    """Pick the best artist background — highest likes."""
    if not images:
        return None
    return max(images, key=lambda img: int(img.get("likes", "0")))


# --- Image Download ---

def _download_image(url: str, output_path: Path) -> bool:
    """Download an image URL to disk. Returns True on success."""
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.debug("Downloaded: %s -> %s", url, output_path)
        return True
    except requests.RequestException as e:
        logger.warning("Failed to download %s: %s", url, e)
        return False


# --- Artist Splitting ---

_SEPARATORS = re.compile(r"\s+(?:&|B2B|b2b|vs\.?|x)\s+", re.IGNORECASE)


def split_artists(name: str) -> list[str]:
    """Split B2B/duo artist names into individual artists for fanart lookup.

    "Martin Garrix & Alesso" -> ["Martin Garrix", "Alesso"]
    "Everything Always (Dom Dolla & John Summit)" -> ["Dom Dolla", "John Summit"]
    "Hardwell" -> ["Hardwell"]
    """
    # Parenthetical: look up inner artists
    paren_match = re.match(r"^.+?\s*\((.+)\)\s*$", name)
    if paren_match:
        inner = paren_match.group(1)
        return _SEPARATORS.split(inner)
    parts = _SEPARATORS.split(name)
    return [p.strip() for p in parts if p.strip()]


# --- Download Orchestrator ---

_attribution_logged = False


def download_artist_images(
    artist_name: str,
    artist_dir: Path,
    project_api_key: str,
    personal_api_key: str = "",
    cache: MBIDCache | None = None,
    force: bool = False,
) -> tuple[bool, bool]:
    """Download clearlogo and fanart for one artist.

    Returns (logo_downloaded, bg_downloaded).
    """
    global _attribution_logged
    if not _attribution_logged:
        logger.info("Artist images provided by fanart.tv (https://fanart.tv)")
        _attribution_logged = True

    logo_path = artist_dir / "clearlogo.png"
    fanart_path = artist_dir / "fanart.jpg"

    need_logo = force or not logo_path.exists()
    need_bg = force or not fanart_path.exists()

    if not need_logo and not need_bg:
        return (False, False)

    if cache is None:
        cache = MBIDCache()

    mbid = lookup_mbid(artist_name, cache)
    if not mbid:
        return (False, False)

    data = fetch_artist_images(mbid, project_api_key, personal_api_key)
    if not data:
        return (False, False)

    logo_ok = False
    bg_ok = False

    if need_logo:
        logo = pick_best_logo(data.get("hdmusiclogo", []))
        if logo:
            logo_ok = _download_image(logo["url"], logo_path)

    if need_bg:
        bg = pick_best_background(data.get("artistbackground", []))
        if bg:
            bg_ok = _download_image(bg["url"], fanart_path)

    return (logo_ok, bg_ok)
