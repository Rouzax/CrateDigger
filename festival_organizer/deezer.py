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

import logging
import re
import time

import requests

from festival_organizer.fanart import USER_AGENT

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
