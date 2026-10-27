"""Deezer artist photos, reached through the artist's MusicBrainz link.

Logging:
    Logger: 'festival_organizer.deezer'
    Key events:
        - enrich.deezer_lookup (INFO): an artist's Deezer photo was resolved
          (route, deezer_id, status); DEBUG for cache hits; WARNING with
          status=unavailable when Deezer or MusicBrainz could not answer
        - enrich.deezer_unresolved (INFO): no Deezer photo for an artist, with
          the overrides path
    See docs/logging.md for full guidelines.
"""

import json
import logging
import re
import time
from pathlib import Path

import requests

from festival_organizer import paths
from festival_organizer.cache_ttl import is_fresh, jittered_ttl_seconds
from festival_organizer.fanart import (
    USER_AGENT,
    MusicBrainzError,
    _fold_name,
    mb_url_relations,
)

logger = logging.getLogger(__name__)

DEEZER_API = "https://api.deezer.com"
# Deezer allows about 50 requests per 5 seconds.
_DEEZER_INTERVAL = 0.2
# Releases compared with an artist's picture; older ones of a prolific artist
# go unchecked.
_RELEASES_CHECKED = 100
# Deezer's code for "no such object" in its error body.
_NOT_FOUND = 800
# Deezer serves artist pictures and release covers from one image store, so a
# picture that is one of the artist's covers carries that cover's image id.
_IMAGE_ID_RE = re.compile(r"/images/(?:artist|cover)/([0-9a-f]{32})/")
# The id of Deezer's blank grey artist placeholder: the md5 of nothing. An
# empty id ("/images/artist//") is the other blank form; it does not match
# _IMAGE_ID_RE at all.
_BLANK_IMAGE_ID = "d41d8cd98f00b204e9800998ecf8427e"

_DEEZER_LINK_RE = re.compile(r"deezer\.com/(?:[a-z]{2}/)?artist/(\d+)")
# Bump when the resolution rules change, so misses recorded by older rules
# are looked up again instead of waiting out their TTL.
DEEZER_RESOLVER_VERSION = 1

_last_request = 0.0


class DeezerError(Exception):
    """Deezer could not answer, so finding nothing is not a real miss."""


def _throttle() -> None:
    global _last_request
    wait = _last_request + _DEEZER_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _get(path: str, params: dict | None = None) -> dict | None:
    """GET a Deezer API path; None when Deezer has no such object.

    Deezer reports quota and query errors with HTTP 200 and an ``error``
    object, so the body is checked as well as the status.
    """
    _throttle()
    try:
        resp = requests.get(
            f"{DEEZER_API}/{path}",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
        body = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise DeezerError(f"{path}: {e}") from e
    if not isinstance(body, dict):
        raise DeezerError(f"{path}: not a JSON object")
    error = body.get("error")
    if error:
        if isinstance(error, dict) and error.get("code") == _NOT_FOUND:
            return None
        raise DeezerError(f"{path}: {error}")
    return body


def deezer_artist(deezer_id: int) -> dict | None:
    """The Deezer artist object, or None when Deezer has no such artist.

    Raises DeezerError when Deezer cannot be asked.
    """
    return _get(f"artist/{deezer_id}")


def photo_url(artist: dict) -> str:
    """The artist's ``picture_xl`` when it is a photo of them, else "".

    Rejects Deezer's blank placeholder and a picture that is one of the
    artist's own release covers. Raises DeezerError when the releases cannot
    be had, so an unanswered check is retried rather than settled.
    """
    picture = str(artist.get("picture_xl") or "")
    found = _IMAGE_ID_RE.search(picture)
    if found is None or found.group(1) == _BLANK_IMAGE_ID:
        return ""
    releases = _get(f"artist/{artist.get('id')}/albums", {"limit": _RELEASES_CHECKED})
    covers = {
        m.group(1)
        for album in (releases or {}).get("data", [])
        if (m := _IMAGE_ID_RE.search(str(album.get("cover_xl") or "")))
    }
    return "" if found.group(1) in covers else picture


def deezer_id_from_url(url: str) -> int | None:
    """The Deezer artist id in a deezer.com artist link, else None."""
    found = _DEEZER_LINK_RE.search(url)
    return int(found.group(1)) if found else None


class DeezerCache:
    """Persistent MBID-to-Deezer-photo mapping with TTL-based expiry.

    Keyed by MBID because the photo is reached through the artist's
    MusicBrainz links. A miss (no link, or no real photo) is cached too, so
    it is not asked again before the TTL; a lookup Deezer or MusicBrainz
    could not answer is never cached.
    """

    def __init__(self, cache_dir: Path | None = None, ttl_days: int = 90):
        directory = cache_dir if cache_dir is not None else paths.cache_dir()
        self._path = directory / "deezer_cache.json"
        self._ttl_days = ttl_days
        self._ttl_seconds = ttl_days * 86400
        self._data: dict[str, dict] = {}
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = raw
            except (json.JSONDecodeError, OSError) as e:
                logger.warning('deezer.cache: status=load_error error="%s"', e)

    def get(self, mbid: str) -> dict | None:
        """The fresh entry for an MBID, or None."""
        entry = self._data.get(mbid)
        if entry is None or not is_fresh(entry, self._ttl_seconds):
            return None
        if (
            not entry.get("picture_url")
            and entry.get("rv", 0) < DEEZER_RESOLVER_VERSION
        ):
            return None
        return entry

    def put(
        self, mbid: str, deezer_id: int | None, picture_url: str, route: str
    ) -> None:
        self._data[mbid] = {
            "deezer_id": deezer_id,
            "picture_url": picture_url,
            "route": route,
            "ts": time.time(),
            "ttl": jittered_ttl_seconds(self._ttl_days),
            "rv": DEEZER_RESOLVER_VERSION,
        }
        paths.ensure_parent(self._path)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


class DeezerOverrides:
    """User-curated artist-name-to-Deezer-id pins, read-only and never expiring.

    Keys are artist display names, matched case-insensitively. A name mapped
    to null pins "no Deezer photo", so the next image source is used.
    """

    def __init__(self, overrides_dir: Path | None = None):
        self._path = (
            overrides_dir / "artist_deezer_ids.json"
            if overrides_dir is not None
            else paths.artist_deezer_ids_file()
        )
        self._data: dict[str, int | None] = {}
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning('deezer.overrides: status=load_error error="%s"', e)
            return
        if not isinstance(raw, dict):
            logger.warning("deezer.overrides: status=invalid_format expected=dict")
            return
        for name, value in raw.items():
            if value is None or (
                isinstance(value, int) and not isinstance(value, bool)
            ):
                self._data[str(name).lower()] = value

    def has(self, artist_name: str) -> bool:
        return artist_name.lower() in self._data

    def get(self, artist_name: str) -> int | None:
        return self._data.get(artist_name.lower())


def _best_photo(artist_name: str, deezer_ids: list[int]) -> tuple[int | None, str]:
    """(deezer_id, photo URL) of the linked page to use, or (None, "").

    Among pages with a real photo: the one named like the artist, then the
    one with the most fans. Raises DeezerError when Deezer cannot be asked.
    """
    candidates: list[tuple[dict, str]] = []
    for deezer_id in deezer_ids:
        artist = deezer_artist(deezer_id)
        if artist is None:
            continue
        photo = photo_url(artist)
        if photo:
            candidates.append((artist, photo))
    if not candidates:
        return (deezer_ids[0] if deezer_ids else None), ""
    wanted = _fold_name(artist_name)
    artist, photo = max(
        candidates,
        key=lambda c: (
            _fold_name(str(c[0].get("name", ""))) == wanted,
            c[0].get("nb_fan") or 0,
        ),
    )
    return int(artist["id"]), photo


def resolve_deezer_photo(
    artist_name: str,
    mbid: str | None,
    cache: DeezerCache,
    overrides: DeezerOverrides,
) -> str:
    """The artist's Deezer photo URL, or "" when there is none to use.

    Precedence: user override > cache > the Deezer pages the artist's
    MusicBrainz entry links. There is no search by name: Deezer has many
    artists of one name and its fan count cannot tell them apart.
    """
    try:
        if overrides.has(artist_name):
            pinned = overrides.get(artist_name)
            if pinned is None:
                return ""
            _, photo = _best_photo(artist_name, [pinned])
            logger.info(
                'enrich.deezer_lookup: artist="%s" route=override deezer_id=%d status=%s',
                artist_name,
                pinned,
                "found" if photo else "no_photo",
            )
            return photo
        if not mbid:
            return ""
        cached = cache.get(mbid)
        if cached is not None:
            logger.debug(
                'enrich.deezer_lookup: artist="%s" route=cache deezer_id=%s',
                artist_name,
                cached.get("deezer_id"),
            )
            return str(cached.get("picture_url") or "")
        ids = [
            i
            for url in mb_url_relations(mbid)
            if (i := deezer_id_from_url(url)) is not None
        ]
        deezer_id, photo = _best_photo(artist_name, list(dict.fromkeys(ids)))
    except (DeezerError, MusicBrainzError) as e:
        logger.warning(
            'enrich.deezer_lookup: artist="%s" status=unavailable error="%s"',
            artist_name,
            e,
        )
        return ""
    cache.put(mbid, deezer_id, photo, "linked")
    if photo:
        logger.info(
            'enrich.deezer_lookup: artist="%s" route=linked deezer_id=%d status=found',
            artist_name,
            deezer_id,
        )
    else:
        logger.info(
            'enrich.deezer_unresolved: artist="%s" deezer_id=%s overrides_path=%s',
            artist_name,
            deezer_id if deezer_id is not None else "",
            paths.artist_deezer_ids_file(),
        )
    return photo
