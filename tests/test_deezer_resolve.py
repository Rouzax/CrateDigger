"""resolve_deezer_photo: an artist's MBID to their Deezer photo.

MusicBrainz links an artist to their Deezer page, sometimes to several (an
alias's page, an empty duplicate). There is no name search: an artist without
a MusicBrainz link gets no Deezer photo.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from festival_organizer.deezer import (
    DeezerCache,
    DeezerError,
    DeezerOverrides,
    deezer_id_from_url,
    resolve_deezer_photo,
)
from festival_organizer.fanart import MusicBrainzError

MBID = "7377ee25-0000-0000-0000-000000000000"
PHOTO = "https://cdn-images.dzcdn.net/images/artist/e71e56891f8a5bf21c9b78ce31d70a8c/1000x1000-000000-80-0-0.jpg"
OTHER_PHOTO = "https://cdn-images.dzcdn.net/images/artist/65b41f3a5cbf7816e38d8136ac9728f3/1000x1000-000000-80-0-0.jpg"
BLANK = "https://cdn-images.dzcdn.net/images/artist/d41d8cd98f00b204e9800998ecf8427e/1000x1000-000000-80-0-0.jpg"


def _artist(deezer_id: int, name: str, fans: int, picture: str) -> dict:
    return {"id": deezer_id, "name": name, "nb_fan": fans, "picture_xl": picture}


class _Deezer:
    """Stands in for deezer_artist and photo_url over a fixed catalogue."""

    def __init__(self, artists: dict[int, dict], covers: frozenset[str] = frozenset()):
        self.artists = artists
        self.covers = covers
        self.asked: list[int] = []

    def artist(self, deezer_id: int) -> dict | None:
        self.asked.append(deezer_id)
        return self.artists.get(deezer_id)

    def photo(self, artist: dict) -> str:
        picture = artist["picture_xl"]
        return "" if picture == BLANK or picture in self.covers else picture


@pytest.fixture
def cache(tmp_path):
    return DeezerCache(cache_dir=tmp_path)


@pytest.fixture
def no_overrides(tmp_path):
    return DeezerOverrides(overrides_dir=tmp_path / "none")


def _run(name, mbid, cache, overrides, links, deezer: _Deezer):
    with (
        patch("festival_organizer.deezer.mb_url_relations", return_value=links) as mb,
        patch("festival_organizer.deezer.deezer_artist", side_effect=deezer.artist),
        patch("festival_organizer.deezer.photo_url", side_effect=deezer.photo),
    ):
        return resolve_deezer_photo(name, mbid, cache, overrides), mb


def test_single_link_with_photo(cache, no_overrides):
    deezer = _Deezer({56125: _artist(56125, "FISHER", 87716, PHOTO)})
    photo, _ = _run(
        "FISHER",
        MBID,
        cache,
        no_overrides,
        ["https://www.deezer.com/artist/56125"],
        deezer,
    )
    assert photo == PHOTO
    entry = cache.get(MBID)
    assert entry is not None
    assert entry["deezer_id"] == 56125
    assert entry["route"] == "linked"


def test_multi_link_prefers_exact_name_then_fans(cache, no_overrides):
    # MusicBrainz links Marlon Hoffstadt's own page and his DJ Daddy Trance one.
    deezer = _Deezer(
        {
            147146942: _artist(147146942, "DJ Daddy Trance", 2662, OTHER_PHOTO),
            3926781: _artist(3926781, "Marlon Hoffstadt", 14188, PHOTO),
        }
    )
    links = [
        "https://www.deezer.com/artist/147146942",
        "https://www.deezer.com/artist/3926781",
    ]
    photo, _ = _run("Marlon Hoffstadt", MBID, cache, no_overrides, links, deezer)
    assert photo == PHOTO


def test_multi_link_without_a_name_match_takes_most_fans(cache, no_overrides):
    deezer = _Deezer(
        {
            1: _artist(1, "Someone", 10, OTHER_PHOTO),
            2: _artist(2, "Someone Else", 500, PHOTO),
        }
    )
    links = ["https://www.deezer.com/artist/1", "https://www.deezer.com/artist/2"]
    photo, _ = _run("Neither", MBID, cache, no_overrides, links, deezer)
    assert photo == PHOTO


def test_multi_link_skips_blank_duplicate(cache, no_overrides):
    # Gunna: a duplicate page with Deezer's blank picture, and his own page.
    deezer = _Deezer(
        {
            259396492: _artist(259396492, "Gunna", 134, BLANK),
            4344192: _artist(4344192, "Gunna", 739573, PHOTO),
        }
    )
    links = [
        "https://www.deezer.com/artist/259396492",
        "https://www.deezer.com/artist/4344192",
    ]
    photo, _ = _run("Gunna", MBID, cache, no_overrides, links, deezer)
    assert photo == PHOTO


def test_link_without_photo_is_a_cached_miss(cache, no_overrides):
    deezer = _Deezer(
        {468677: _artist(468677, "Bart Skils", 9493, OTHER_PHOTO)},
        frozenset({OTHER_PHOTO}),
    )
    photo, _ = _run(
        "Bart Skils",
        MBID,
        cache,
        no_overrides,
        ["https://www.deezer.com/artist/468677"],
        deezer,
    )
    assert photo == ""
    entry = cache.get(MBID)
    assert entry is not None
    assert entry["picture_url"] == ""


def test_no_mbid_is_empty_without_requests(cache, no_overrides):
    deezer = _Deezer({})
    photo, mb = _run("Everything Always", None, cache, no_overrides, [], deezer)
    assert photo == ""
    mb.assert_not_called()


def test_no_deezer_link_is_a_cached_miss(cache, no_overrides):
    deezer = _Deezer({})
    photo, _ = _run(
        "Tall Paul",
        MBID,
        cache,
        no_overrides,
        ["https://www.discogs.com/artist/1"],
        deezer,
    )
    assert photo == ""
    entry = cache.get(MBID)
    assert entry is not None
    assert entry["deezer_id"] is None


def test_deezer_error_is_not_cached(cache, no_overrides):
    with (
        patch(
            "festival_organizer.deezer.mb_url_relations",
            return_value=["https://www.deezer.com/artist/56125"],
        ),
        patch(
            "festival_organizer.deezer.deezer_artist", side_effect=DeezerError("Quota")
        ),
    ):
        assert resolve_deezer_photo("FISHER", MBID, cache, no_overrides) is None
    assert cache.get(MBID) is None


def test_musicbrainz_outage_is_not_cached(cache, no_overrides):
    with patch(
        "festival_organizer.deezer.mb_url_relations",
        side_effect=MusicBrainzError("503"),
    ):
        assert resolve_deezer_photo("FISHER", MBID, cache, no_overrides) is None
    assert cache.get(MBID) is None


def test_cache_hit_makes_no_requests(cache, no_overrides):
    cache.put(MBID, 56125, PHOTO, "linked")
    deezer = _Deezer({})
    photo, mb = _run("FISHER", MBID, cache, no_overrides, [], deezer)
    assert photo == PHOTO
    mb.assert_not_called()
    assert deezer.asked == []


def test_override_id_wins_and_skips_musicbrainz(cache, tmp_path):
    (tmp_path / "artist_deezer_ids.json").write_text(json.dumps({"fisher": 56125}))
    overrides = DeezerOverrides(overrides_dir=tmp_path)
    deezer = _Deezer({56125: _artist(56125, "FISHER", 87716, PHOTO)})
    photo, mb = _run("FISHER", None, cache, overrides, [], deezer)
    assert photo == PHOTO
    mb.assert_not_called()


def test_override_null_pins_no_image(cache, tmp_path):
    (tmp_path / "artist_deezer_ids.json").write_text(json.dumps({"FISHER": None}))
    overrides = DeezerOverrides(overrides_dir=tmp_path)
    deezer = _Deezer({56125: _artist(56125, "FISHER", 87716, PHOTO)})
    photo, mb = _run(
        "FISHER",
        MBID,
        cache,
        overrides,
        ["https://www.deezer.com/artist/56125"],
        deezer,
    )
    assert photo == ""
    mb.assert_not_called()
    assert deezer.asked == []


def test_miss_from_an_older_resolver_is_retried(cache):
    cache.put(MBID, None, "", "linked")
    cache._data[MBID]["rv"] = 0
    assert cache.get(MBID) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.deezer.com/artist/56125",
        "https://www.deezer.com/en/artist/56125",
        "https://www.deezer.com/artist/56125/",
        "http://deezer.com/artist/56125",
    ],
)
def test_deezer_link_url_forms(url):
    assert deezer_id_from_url(url) == 56125


def test_non_deezer_url_is_none():
    assert deezer_id_from_url("https://open.spotify.com/artist/56125") is None


def test_mb_url_relations_lists_every_link():
    from festival_organizer import fanart

    body = {
        "relations": [
            {"url": {"resource": "https://www.deezer.com/artist/56125"}},
            {"url": {"resource": "https://open.spotify.com/artist/x"}},
            {"type": "member of band"},
        ]
    }
    resp = MagicMock(status_code=200)
    resp.json.return_value = body
    with (
        patch("festival_organizer.fanart.requests.get", return_value=resp) as get,
        patch("festival_organizer.fanart.time.sleep"),
    ):
        assert fanart.mb_url_relations(MBID) == [
            "https://www.deezer.com/artist/56125",
            "https://open.spotify.com/artist/x",
        ]
    assert get.call_args.kwargs["params"]["inc"] == "url-rels"


def test_unavailable_is_none_not_empty(cache, no_overrides):
    with patch(
        "festival_organizer.deezer.mb_url_relations",
        side_effect=MusicBrainzError("503"),
    ):
        assert resolve_deezer_photo("FISHER", MBID, cache, no_overrides) is None


def test_payload_without_id_does_not_crash(cache, no_overrides):
    deezer = _Deezer({56125: {"name": "FISHER", "nb_fan": 1, "picture_xl": PHOTO}})
    photo, _ = _run(
        "FISHER",
        MBID,
        cache,
        no_overrides,
        ["https://www.deezer.com/artist/56125"],
        deezer,
    )
    assert photo == PHOTO
    entry = cache.get(MBID)
    assert entry is not None
    assert entry["deezer_id"] == 56125


def test_pinned_page_answer_is_cached(cache, tmp_path):
    (tmp_path / "artist_deezer_ids.json").write_text(json.dumps({"Bart Skils": 468677}))
    overrides = DeezerOverrides(overrides_dir=tmp_path)
    cover = _Deezer(
        {468677: _artist(468677, "Bart Skils", 9493, OTHER_PHOTO)},
        frozenset({OTHER_PHOTO}),
    )
    _run("Bart Skils", None, cache, overrides, [], cover)
    again = _Deezer({})
    photo, _ = _run("Bart Skils", None, cache, overrides, [], again)
    assert photo == ""
    assert again.asked == []


def test_found_photo_logs_the_fan_count(cache, no_overrides, caplog):
    import logging

    deezer = _Deezer({56125: _artist(56125, "FISHER", 87716, PHOTO)})
    with caplog.at_level(logging.INFO, logger="festival_organizer.deezer"):
        _run(
            "FISHER",
            MBID,
            cache,
            no_overrides,
            ["https://www.deezer.com/artist/56125"],
            deezer,
        )
    assert any("fans=87716" in m for m in caplog.messages)
