"""fanart.tv and MusicBrainz integration for artist artwork.

Downloads HD ClearLOGOs and artist backgrounds from fanart.tv.
Artist images provided by fanart.tv (https://fanart.tv).

Logging:
    Logger: 'festival_organizer.fanart'
    Key events:
        - mbid.lookup (INFO): MusicBrainz artist lookup and result
        - mbid.found (INFO): MBID resolved for artist
        - mbid.miss (INFO): No MusicBrainz match for artist
        - mbid.cache_hit (DEBUG): MBID found in local cache
        - mbid.cache_negative (DEBUG): Negative cache hit (previously not found)
        - download.success (INFO): Image downloaded successfully
        - download.fail (WARNING): Image download failed
        - fanart.retry (DEBUG): fanart.tv 5xx retry
        - musicbrainz.retry (DEBUG): MusicBrainz 503 retry
        - theaudiodb.fallback (DEBUG): Trying TheAudioDB as fallback
        - theaudiodb.fail (DEBUG): TheAudioDB lookup failed
        - attribution (INFO): Required attribution notice
    See docs/logging.md for full guidelines.
"""
import json
import logging
import re
import time
from pathlib import Path
from typing import Callable

import requests

from festival_organizer.cache_ttl import is_fresh, jittered_ttl_seconds
from festival_organizer.normalization import strip_diacritics

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
    """Persistent artist-name-to-MBID mapping with TTL-based expiry.

    Keys are lowercased artist names. Values are dicts with "mbid" and "ts"
    fields. Migrates transparently from the old bare-string format.
    """

    def __init__(self, cache_dir: Path | None = None, ttl_days: int = 90):
        self._dir = cache_dir or (Path.home() / ".cratedigger")
        self._path = self._dir / "mbid_cache.json"
        self._ttl_days = ttl_days
        self._ttl_seconds = ttl_days * 86400
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not load MBID cache: %s", e)
                return
            # Migrate old bare-string format: treat as expired (ts=0)
            for key, value in raw.items():
                if isinstance(value, dict) and "ts" in value:
                    self._data[key] = value
                else:
                    self._data[key] = {"mbid": value, "ts": 0}

    def _save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _is_fresh(self, entry: dict) -> bool:
        return is_fresh(entry, self._ttl_seconds)

    def get(self, artist: str) -> str | None:
        """Return cached MBID or None. Raises KeyError if not cached or expired."""
        key = artist.lower()
        entry = self._data.get(key)
        if entry is None or not self._is_fresh(entry):
            raise KeyError(artist)
        return entry["mbid"]

    def has(self, artist: str) -> bool:
        """True if artist is cached and not expired."""
        key = artist.lower()
        entry = self._data.get(key)
        return entry is not None and self._is_fresh(entry)

    def put(self, artist: str, mbid: str | None) -> None:
        """Cache an artist-to-MBID mapping. None = not found (negative cache)."""
        self._data[artist.lower()] = {
            "mbid": mbid,
            "ts": time.time(),
            "ttl": jittered_ttl_seconds(self._ttl_days),
        }
        self._save()


class ArtistMbidOverrides:
    """User-curated artist-name-to-MBID pins, read-only and never expiring.

    Keys are artist display names, matched case-insensitively. This file is
    owned by the user: the code never writes to it and never promotes
    entries into MBIDCache, keeping curated pins separate from disposable
    cache data.
    """

    _FILENAME = "artist_mbids.json"

    def __init__(self, overrides_dir: Path | None = None):
        self._path = (overrides_dir or (Path.home() / ".cratedigger")) / self._FILENAME
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load artist_mbids.json: %s", e)
            return
        if not isinstance(raw, dict):
            logger.warning("artist_mbids.json must be a JSON object; ignoring")
            return
        self._data = {
            k.lower(): v
            for k, v in raw.items()
            if isinstance(v, str) and v
        }

    def get(self, artist_name: str) -> str | None:
        """Return the pinned MBID for an artist, or None when not pinned."""
        return self._data.get(artist_name.lower())

    def has(self, artist_name: str) -> bool:
        """True when the artist has a pinned MBID override."""
        return artist_name.lower() in self._data


# --- MusicBrainz Client ---

_last_mb_request: float = 0.0


def _mb_rate_limit() -> None:
    """Enforce MusicBrainz 1 req/sec rate limit."""
    global _last_mb_request
    elapsed = time.monotonic() - _last_mb_request
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_mb_request = time.monotonic()


def lookup_mbid(
    artist_name: str,
    cache: MBIDCache,
    overrides: "ArtistMbidOverrides | None" = None,
) -> str | None:
    """Look up MusicBrainz ID for an artist name.

    Precedence: user override (never expires, never written to) > local
    cache (TTL-bound) > MusicBrainz search. Overrides are returned as-is
    and are NOT promoted into the cache: that keeps the curated file the
    single source of truth and prevents a TTL refresh from stomping a pin.
    """
    if overrides is not None:
        pinned = overrides.get(artist_name)
        if pinned:
            logger.debug("MBID override hit: %s -> %s", artist_name, pinned)
            return pinned

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
    """Query MusicBrainz search API. Returns best-match MBID or None.

    Uses tiered name matching across candidates (score >= 80):
    1. Exact case match
    2. Case-insensitive match
    3. Diacritics-insensitive match
    """
    _mb_rate_limit()

    url = f"{MB_BASE_URL}/artist/"
    # Query without a type filter, then post-filter in code. An AND type:...
    # clause would drop MB entries whose type field is null, which is common
    # for mid-profile DJs whose MB entry has never been type-tagged (e.g.
    # Hannah Laing, score 100 exact match, but type:null -> excluded).
    query = f'artist:"{artist_name}"'
    params = {"query": query, "fmt": "json", "limit": "25"}
    headers = {"User-Agent": USER_AGENT}

    # Reject explicit non-artist types so results don't include record labels,
    # orchestras, characters, etc. Missing type ("" or None) is allowed because
    # real artists often have no type set on MB.
    non_artist_types = {"Orchestra", "Choir", "Character", "Other"}

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

            # Filter: drop non-artist types; require score >= 80.
            candidates = [
                a for a in artists
                if a.get("score", 0) >= 80
                and (a.get("type") or "") not in non_artist_types
            ]
            if not candidates:
                logger.debug("Best match score %d < 80 for '%s'",
                             artists[0].get("score", 0), artist_name)
                return None

            # Tier 1: exact case match
            for a in candidates:
                if a.get("name") == artist_name:
                    logger.debug("MBID exact match: '%s' -> %s", a["name"], a["id"])
                    return a["id"]

            # Tier 2: case-insensitive match
            query_lower = artist_name.lower()
            for a in candidates:
                if a.get("name", "").lower() == query_lower:
                    logger.debug("MBID case-insensitive match: '%s' -> %s", a["name"], a["id"])
                    return a["id"]

            # Tier 3: diacritics-insensitive match
            query_stripped = strip_diacritics(artist_name).lower()
            for a in candidates:
                if strip_diacritics(a.get("name", "")).lower() == query_stripped:
                    logger.debug("MBID diacritics match: '%s' -> %s", a["name"], a["id"])
                    return a["id"]

            logger.debug("No name match in %d candidates for '%s'",
                         len(candidates), artist_name)
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

def _image_sort_key(img: dict) -> tuple[int, str]:
    """Sort key: likes first, then newest added date as tiebreaker."""
    return (int(img.get("likes", "0")), img.get("added", ""))


def pick_best_logo(images: list[dict]) -> dict | None:
    """Pick the best HD ClearLOGO — prefer English or language-neutral, highest likes, newest."""
    if not images:
        return None
    preferred = [img for img in images if img.get("lang") in ("en", "")]
    pool = preferred if preferred else images
    return max(pool, key=_image_sort_key)


def pick_best_background(images: list[dict]) -> dict | None:
    """Pick the best artist background — highest likes, newest as tiebreaker."""
    if not images:
        return None
    return max(images, key=_image_sort_key)


# --- TheAudioDB Client (fallback) ---

AUDIODB_BASE_URL = "https://www.theaudiodb.com/api/v1/json/123"


def fetch_audiodb_artist(mbid: str) -> dict | None:
    """Fetch artist data from TheAudioDB by MusicBrainz ID. Returns artist dict or None."""
    url = f"{AUDIODB_BASE_URL}/artist-mb.php"
    params = {"i": mbid}

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        artists = data.get("artists")
        if artists:
            return artists[0]
        return None
    except requests.RequestException as e:
        logger.debug("TheAudioDB lookup failed for MBID %s: %s", mbid, e)
        return None


def _audiodb_best_fanart(artist: dict) -> str | None:
    """Pick the best fanart URL from TheAudioDB artist data.

    Priority: strArtistFanart (1280px) > strArtistThumb (700px square).
    """
    for field in ("strArtistFanart", "strArtistFanart2", "strArtistFanart3", "strArtistThumb"):
        url = artist.get(field)
        if url:
            return url
    return None


def _audiodb_best_logo(artist: dict) -> str | None:
    """Pick the logo URL from TheAudioDB artist data."""
    return artist.get("strArtistLogo") or None


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
        logger.info("Downloaded: %s -> %s", url, output_path)
        return True
    except requests.RequestException as e:
        logger.warning("Failed to download %s: %s", url, e)
        return False


# --- Artist Splitting ---

_SEPARATORS = re.compile(r"\s+(?:&|B2B|b2b|vs\.?|x)\s+", re.IGNORECASE)


def split_artists(name: str, groups: set[str] | None = None) -> list[str]:
    """Split B2B/duo artist names into individual artists for fanart lookup.

    "Martin Garrix & Alesso" -> ["Martin Garrix", "Alesso"]
    "Everything Always (Dom Dolla & John Summit)" -> ["Dom Dolla", "John Summit"]
    "Hardwell" -> ["Hardwell"]

    If *groups* is provided and the name (case-insensitive) is in the set,
    return it unsplit so the group is treated as a single artist.
    """
    if groups and name.lower() in groups:
        return [name]
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
    prefetched_mbid: str | None = None,
    prefetched_data: dict | None = None,
) -> tuple[bool, bool]:
    """Download clearlogo and fanart for one artist.

    Source priority:
    1. fanart.tv (HD logos + 1920px backgrounds)
    2. TheAudioDB fallback (logos + 1280px fanart / 700px thumbs)

    Returns (logo_downloaded, bg_downloaded).

    Pass prefetched_mbid and prefetched_data to avoid redundant API calls
    when the caller has already looked up the MBID and fetched images.
    """
    global _attribution_logged
    if not _attribution_logged:
        logger.info("Artist images provided by fanart.tv (https://fanart.tv) "
                     "and TheAudioDB (https://www.theaudiodb.com)")
        _attribution_logged = True

    logo_path = artist_dir / "clearlogo.png"
    fanart_path = artist_dir / "fanart.jpg"

    need_logo = force or not logo_path.exists()
    need_bg = force or not fanart_path.exists()

    if not need_logo and not need_bg:
        return (False, False)

    if cache is None:
        cache = MBIDCache()

    mbid = prefetched_mbid or lookup_mbid(artist_name, cache)
    if not mbid:
        return (False, False)

    logo_ok = False
    bg_ok = False

    # --- Source 1: fanart.tv ---
    data = prefetched_data or fetch_artist_images(mbid, project_api_key, personal_api_key)
    if data:
        if need_logo:
            logo = pick_best_logo(data.get("hdmusiclogo", []))
            if logo:
                logo_ok = _download_image(logo["url"], logo_path)

        if need_bg:
            bg = pick_best_background(data.get("artistbackground", []))
            if bg:
                bg_ok = _download_image(bg["url"], fanart_path)

    # --- Source 2: TheAudioDB fallback for anything still missing ---
    still_need_logo = need_logo and not logo_ok
    still_need_bg = need_bg and not bg_ok

    if still_need_logo or still_need_bg:
        logger.debug("Trying TheAudioDB fallback for %s", artist_name)
        audiodb = fetch_audiodb_artist(mbid)
        if audiodb:
            if still_need_logo:
                logo_url = _audiodb_best_logo(audiodb)
                if logo_url:
                    logo_ok = _download_image(logo_url, logo_path)

            if still_need_bg:
                bg_url = _audiodb_best_fanart(audiodb)
                if bg_url:
                    bg_ok = _download_image(bg_url, fanart_path)

    return (logo_ok, bg_ok)


def resolve_mbids_aligned(
    names: list[str],
    resolver: Callable[[str], str | None],
) -> list[str]:
    """Resolve artist names to MBIDs, preserving positional alignment.

    Resolver is called at most once per unique name. Missing MBIDs become
    empty strings so pipe-joined output stays slot-aligned with `names`.
    Unresolved names are logged once at WARNING, not once per occurrence.

    Used by `compute_chapter_mbid_tags` (per-chapter PERFORMER_NAMES) and
    by AlbumArtistMbidsOperation (album-level CRATEDIGGER_1001TL_ARTISTS).
    """
    unique: dict[str, str | None] = {}
    for name in names:
        if name and name not in unique:
            unique[name] = resolver(name)

    for name, mbid in unique.items():
        if mbid is None:
            logger.warning(
                "No MBID resolved for artist: %r (add to ~/.cratedigger/artist_mbids.json)",
                name,
            )

    return ["" if (m := unique.get(name)) is None else m for name in names]


def compute_chapter_mbid_tags(
    chapter_tags: dict[int, dict[str, str]],
    resolver: Callable[[str], str | None],
) -> dict[int, dict[str, str]]:
    """Build a per-chapter MUSICBRAINZ_ARTISTIDS map from PERFORMER_NAMES.

    Delegates the per-name dedupe / resolve / log-once / empty-slot logic
    to `resolve_mbids_aligned`. Retains the chapter-shape iteration so
    callers keep a simple per-uid contract.

    Chapters without PERFORMER_NAMES are skipped (legacy files must be
    re-identified first, not half-enriched).
    """
    all_names = [
        name
        for entry in chapter_tags.values()
        for name in (entry.get("PERFORMER_NAMES") or "").split("|")
        if name
    ]
    mbid_by_name = dict(zip(all_names, resolve_mbids_aligned(all_names, resolver)))

    result: dict[int, dict[str, str]] = {}
    for uid, entry in chapter_tags.items():
        names_str = entry.get("PERFORMER_NAMES")
        if not names_str:
            continue
        mbids = [mbid_by_name.get(name, "") for name in names_str.split("|")]
        result[uid] = {"MUSICBRAINZ_ARTISTIDS": "|".join(mbids)}
    return result
