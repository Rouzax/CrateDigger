"""lookup_mbid with the artist's Spotify page from their 1001TL profile.

MusicBrainz can have two artists of exactly the same name: "Argy" is both the
Greek Afterlife DJ and a Welsh DJ, and its search ranks the Welsh one first.
The 1001TL profile links the artist's own Spotify page, and MusicBrainz's URL
lookup returns the artist that page belongs to.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from festival_organizer.fanart import (
    ArtistMbidOverrides,
    MBIDCache,
    lookup_mbid,
    spotify_urls_by_name,
)

SPOTIFY = "https://open.spotify.com/artist/1NaQOKgddaJipUtmptb7GI"
GREEK = "ace06a49-c395-40f6-acaf-3964a8e06431"
WELSH = "ccfc48a4-0fca-4dd2-bd2a-d2d40788b354"


def _resp(status: int, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body or {}
    resp.raise_for_status = MagicMock()
    return resp


def _linked(*artists: tuple[str, str]) -> MagicMock:
    return _resp(
        200,
        {
            "relations": [
                {"type": "free streaming", "artist": {"id": mbid, "name": name}}
                for mbid, name in artists
            ]
        },
    )


def _search(*artists: tuple[str, str]) -> MagicMock:
    return _resp(
        200,
        {
            "artists": [
                {"id": mbid, "name": name, "score": 100} for mbid, name in artists
            ]
        },
    )


@pytest.fixture(autouse=True)
def _no_sleep():
    with patch("festival_organizer.fanart.time.sleep"):
        yield


def _get(*responses: MagicMock):
    return patch("festival_organizer.fanart.requests.get", side_effect=list(responses))


def test_spotify_link_picks_the_artist_the_name_search_gets_wrong(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)
    with _get(_linked((GREEK, "Argy"))) as get:
        assert lookup_mbid("Argy", cache, spotify_url=SPOTIFY) == GREEK
    assert get.call_args.args[0].endswith("/url")
    assert get.call_args.kwargs["params"]["resource"] == SPOTIFY


def test_spotify_link_beats_a_cached_name_match(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)
    cache.put("Argy", WELSH)
    with _get(_linked((GREEK, "Argy"))):
        assert lookup_mbid("Argy", cache, spotify_url=SPOTIFY) == GREEK


def test_spotify_answer_is_cached(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)
    with _get(_linked((GREEK, "Argy"))):
        lookup_mbid("Argy", cache, spotify_url=SPOTIFY)
    with _get() as get:
        assert lookup_mbid("Argy", cache, spotify_url=SPOTIFY) == GREEK
    get.assert_not_called()


def test_spotify_page_musicbrainz_does_not_know_falls_back_to_the_name(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)
    with _get(_resp(404), _search((WELSH, "Argy"))):
        assert lookup_mbid("Argy", cache, spotify_url=SPOTIFY) == WELSH


def test_unknown_spotify_page_is_not_asked_again(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)
    with _get(_resp(404), _search((WELSH, "Argy"))):
        lookup_mbid("Argy", cache, spotify_url=SPOTIFY)
    with _get() as get:
        assert lookup_mbid("Argy", cache, spotify_url=SPOTIFY) == WELSH
    get.assert_not_called()


def test_several_linked_artists_pick_the_named_one(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)
    with _get(_linked(("other", "Someone Else"), (GREEK, "Argy"))):
        assert lookup_mbid("Argy", cache, spotify_url=SPOTIFY) == GREEK


def test_several_linked_artists_none_named_falls_back_to_the_name(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)
    with _get(_linked(("a", "One"), ("b", "Two")), _search((WELSH, "Argy"))):
        assert lookup_mbid("Argy", cache, spotify_url=SPOTIFY) == WELSH


def test_musicbrainz_outage_is_not_cached_for_the_spotify_page(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)
    with _get(*[_resp(503)] * 6):
        assert lookup_mbid("Argy", cache, spotify_url=SPOTIFY) is None
    with _get(_linked((GREEK, "Argy"))):
        assert lookup_mbid("Argy", cache, spotify_url=SPOTIFY) == GREEK


def test_override_still_wins(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(json.dumps({"Argy": "PINNED"}))
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)
    with _get() as get:
        assert (
            lookup_mbid(
                "Argy", MBIDCache(cache_dir=tmp_path), overrides, spotify_url=SPOTIFY
            )
            == "PINNED"
        )
    get.assert_not_called()


def test_without_a_spotify_link_the_name_search_is_unchanged(tmp_path):
    with _get(_search((WELSH, "Argy"))) as get:
        assert lookup_mbid("Argy", MBIDCache(cache_dir=tmp_path)) == WELSH
    assert get.call_args.args[0].endswith("/artist/")


class _DjCache:
    def spotify_url(self, slug: str) -> str:
        return {"argy": SPOTIFY}.get(slug, "")


def test_spotify_urls_pair_names_with_their_slugs():
    assert spotify_urls_by_name(["Argy", "Anyma"], ["argy", "anyma"], _DjCache()) == {
        "Argy": SPOTIFY
    }


def test_spotify_urls_need_aligned_names_and_slugs():
    # A file whose slug tag does not line up with its names cannot say which
    # name a page belongs to.
    assert spotify_urls_by_name(["Argy", "Anyma"], ["argy"], _DjCache()) == {}


def test_spotify_urls_without_a_dj_cache():
    assert spotify_urls_by_name(["Argy"], ["argy"], None) == {}
