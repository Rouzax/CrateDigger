"""Tests for fanart.tv integration (all mocked, no real network calls)."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from festival_organizer.fanart import (
    MBIDCache,
    fetch_artist_images,
    lookup_mbid,
    pick_best_background,
    pick_best_logo,
    split_artists,
)

# --- split_artists tests ---


def test_split_artists_single():
    assert split_artists("Hardwell") == ["Hardwell"]


def test_split_artists_ampersand():
    assert split_artists("Martin Garrix & Alesso") == ["Martin Garrix", "Alesso"]


def test_split_artists_b2b():
    assert split_artists("Adam Beyer B2B Cirez D") == ["Adam Beyer", "Cirez D"]


def test_split_artists_triple():
    result = split_artists("Axwell & Sebastian Ingrosso & Steve Angello")
    assert result == ["Axwell", "Sebastian Ingrosso", "Steve Angello"]


def test_split_artists_parenthetical():
    result = split_artists("Everything Always (Dom Dolla & John Summit)")
    assert result == ["Dom Dolla", "John Summit"]


def test_split_artists_vs():
    assert split_artists("Armin vs Vini Vici") == ["Armin", "Vini Vici"]


def test_split_artists_respects_groups():
    groups = {"dimitri vegas & like mike"}
    result = split_artists("Dimitri Vegas & Like Mike", groups=groups)
    assert result == ["Dimitri Vegas & Like Mike"]


def test_split_artists_splits_non_groups():
    groups = {"dimitri vegas & like mike"}
    result = split_artists("Armin van Buuren & KIKI", groups=groups)
    assert result == ["Armin van Buuren", "KIKI"]


# --- MBIDCache tests ---


def test_mbid_cache_put_get():
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        cache.put("Hardwell", "abc-123")
        assert cache.get("Hardwell") == "abc-123"


def test_mbid_cache_case_insensitive():
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        cache.put("hardwell", "abc-123")
        assert cache.get("HARDWELL") == "abc-123"
        assert cache.has("Hardwell")


def test_mbid_cache_negative():
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        cache.put("Unknown DJ", None)
        assert cache.has("Unknown DJ")
        assert cache.get("Unknown DJ") is None


def test_mbid_cache_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        assert not cache.has("Nobody")
        with pytest.raises(KeyError):
            cache.get("Nobody")


def test_mbid_cache_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        cache1 = MBIDCache(cache_dir=Path(tmp))
        cache1.put("Hardwell", "abc-123")
        cache1.put("ALOK", "def-456")

        # New instance should load from disk
        cache2 = MBIDCache(cache_dir=Path(tmp))
        assert cache2.get("Hardwell") == "abc-123"
        assert cache2.get("ALOK") == "def-456"


def test_mbid_cache_uses_platformdirs_cache_dir(tmp_path):
    from festival_organizer.fanart import MBIDCache

    with patch("festival_organizer.fanart.paths") as mock_paths:
        mock_paths.cache_dir.return_value = tmp_path
        mock_paths.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True),
            p,
        )[1]
        cache = MBIDCache()
        cache.put("Tiesto", "abc-123")
    assert (tmp_path / "mbid_cache.json").is_file()


def test_artist_mbid_overrides_uses_data_dir(tmp_path):
    from festival_organizer.fanart import ArtistMbidOverrides

    override_file = tmp_path / "artist_mbids.json"
    override_file.write_text('{"Tiesto": "tiesto-mbid"}')
    with patch("festival_organizer.fanart.paths") as mock_paths:
        mock_paths.artist_mbids_file.return_value = override_file
        overrides = ArtistMbidOverrides()
    assert overrides.get("Tiesto") == "tiesto-mbid"


# --- Image selection tests ---


def test_pick_best_logo_prefers_english():
    images = [
        {"id": "1", "url": "http://a.jpg", "lang": "de", "likes": "50"},
        {"id": "2", "url": "http://b.jpg", "lang": "en", "likes": "30"},
        {"id": "3", "url": "http://c.jpg", "lang": "en", "likes": "40"},
    ]
    best = pick_best_logo(images)
    assert best["id"] == "3"  # English with most likes


def test_pick_best_logo_falls_back_to_empty_lang():
    images = [
        {"id": "1", "url": "http://a.jpg", "lang": "de", "likes": "50"},
        {"id": "2", "url": "http://b.jpg", "lang": "", "likes": "30"},
    ]
    best = pick_best_logo(images)
    assert best["id"] == "2"  # Empty lang preferred over foreign


def test_pick_best_logo_all_foreign():
    images = [
        {"id": "1", "url": "http://a.jpg", "lang": "de", "likes": "50"},
        {"id": "2", "url": "http://b.jpg", "lang": "fr", "likes": "70"},
    ]
    best = pick_best_logo(images)
    assert best["id"] == "2"  # Highest likes when no preferred lang


def test_pick_best_logo_empty():
    assert pick_best_logo([]) is None


def test_pick_best_background_by_likes():
    images = [
        {"id": "1", "url": "http://a.jpg", "likes": "10"},
        {"id": "2", "url": "http://b.jpg", "likes": "99"},
        {"id": "3", "url": "http://c.jpg", "likes": "50"},
    ]
    best = pick_best_background(images)
    assert best["id"] == "2"


def test_pick_best_background_empty():
    assert pick_best_background([]) is None


# --- MusicBrainz lookup tests ---


def test_lookup_mbid_cache_hit():
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        cache.put("Hardwell", "abc-123")
        result = lookup_mbid("Hardwell", cache)
        assert result == "abc-123"


def test_lookup_mbid_cache_negative_hit():
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        cache.put("Nobody", None)
        result = lookup_mbid("Nobody", cache)
        assert result is None


def test_mbid_cache_expired_entry_is_miss():
    """Expired entry should act as cache miss."""
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp), ttl_days=0)
        cache.put("Hardwell", "abc-123")
        assert not cache.has("Hardwell")
        with pytest.raises(KeyError):
            cache.get("Hardwell")


def test_mbid_cache_migrates_old_format():
    """Old bare-string format entries are treated as expired."""
    with tempfile.TemporaryDirectory() as tmp:
        cache_file = Path(tmp) / "mbid_cache.json"
        cache_file.write_text('{"hardwell": "abc-123", "nobody": null}')
        cache = MBIDCache(cache_dir=Path(tmp), ttl_days=90)
        # Old entries have ts=0, so they're expired
        assert not cache.has("Hardwell")
        # But putting a fresh entry works
        cache.put("Hardwell", "new-456")
        assert cache.has("Hardwell")
        assert cache.get("Hardwell") == "new-456"


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_api_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "artists": [{"id": "abc-123", "score": 100, "name": "Hardwell"}]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        result = lookup_mbid("Hardwell", cache)
        assert result == "abc-123"
        assert cache.get("Hardwell") == "abc-123"


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_low_score(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "artists": [{"id": "abc-123", "score": 50, "name": "Hard Well"}]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        result = lookup_mbid("Hardwell", cache)
        assert result is None
        assert cache.get("Hardwell") is None  # Negative cached


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_exact_case_preferred(mock_get):
    """Exact case match is preferred over higher-scored case mismatch (FISHER scenario)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "artists": [
            {"id": "wrong-india", "score": 100, "name": "India Fisher"},
            {"id": "wrong-fisher", "score": 93, "name": "Fisher"},
            {"id": "correct-fisher", "score": 88, "name": "FISHER"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        result = lookup_mbid("FISHER", cache)
        assert result == "correct-fisher"


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_case_insensitive_fallback(mock_get):
    """Case-insensitive match used when no exact case match exists."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "artists": [
            {"id": "wrong-other", "score": 100, "name": "DJ Alesso"},
            {"id": "correct-alesso", "score": 95, "name": "Alesso"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        result = lookup_mbid("alesso", cache)
        assert result == "correct-alesso"


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_diacritics_match(mock_get):
    """Diacritics-insensitive match finds accented artist names."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "artists": [
            {"id": "correct-tiesto", "score": 100, "name": "Ti\u00ebsto"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        result = lookup_mbid("Tiesto", cache)
        assert result == "correct-tiesto"


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_matches_unicode_hyphen_in_name(mock_get):
    """MusicBrainz spells A-Trak with U+2010 HYPHEN; 1001TL gives U+002D.

    NFD, NFKD and NFKC all leave those two codepoints distinct, so the
    diacritics tier cannot bridge them and the artist stayed unresolved
    even though MusicBrainz returned it as an exact score-100 hit.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "artists": [{"id": "mbid-atrak", "score": 100, "name": "A‐Trak"}]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        assert lookup_mbid("A-Trak", cache) == "mbid-atrak"


def _mb_response(artists):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"artists": artists}
    resp.raise_for_status = MagicMock()
    return resp


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_matches_via_alias(mock_get):
    """MusicBrainz renamed Kanye West to 'Ye'; the old name survives only as
    an alias, so matching the canonical name alone never finds the artist."""
    mock_get.return_value = _mb_response(
        [
            {
                "id": "mbid-ye",
                "score": 100,
                "name": "Ye",
                "aliases": [{"name": "Kanye West"}, {"name": "Kanye"}],
            }
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        assert lookup_mbid("Kanye West", cache) == "mbid-ye"


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_alias_match_must_be_exact(mock_get):
    """A composite alias that merely contains the query must not match.

    MusicBrainz lists '¥$, Kanye West & Ty Dolla $ign' as an alias of the
    duo '¥$'. A substring rule would bind Kanye West to that duo's MBID.
    """
    mock_get.return_value = _mb_response(
        [
            {
                "id": "mbid-yen-dollar",
                "score": 100,
                "name": "¥$",
                "aliases": [{"name": "¥$, Kanye West & Ty Dolla $ign"}],
            }
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        assert lookup_mbid("Kanye West", cache) is None


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_prefers_canonical_name_over_alias(mock_get):
    """An exact canonical-name hit wins over another candidate's alias."""
    mock_get.return_value = _mb_response(
        [
            {
                "id": "mbid-alias-holder",
                "score": 100,
                "name": "Someone Else",
                "aliases": [{"name": "Hardwell"}],
            },
            {"id": "mbid-hardwell", "score": 100, "name": "Hardwell"},
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        assert lookup_mbid("Hardwell", cache) == "mbid-hardwell"


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_query_searches_alias_field(mock_get):
    """The search must ask for alias hits, not just name hits.

    'Kanye West' returns only a tribute band and a collaboration when the
    query is restricted to artist:, so the alias field is what surfaces 'Ye'.
    """
    mock_get.return_value = _mb_response([])
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        lookup_mbid("Kanye West", cache)
    query = mock_get.call_args.kwargs["params"]["query"]
    assert 'artist:"Kanye West"' in query
    assert 'alias:"Kanye West"' in query


@patch("festival_organizer.fanart.time.sleep")
@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_does_not_cache_a_rate_limited_lookup(mock_get, _sleep):
    """A 503 that outlives its retries must not be remembered as 'not found'.

    Caching it writes a negative entry with a jittered 90-day TTL, so one
    MusicBrainz outage silently strips IDs from every artist in that run
    and keeps doing so for months. Leaving it uncached retries next run.
    """
    resp = MagicMock()
    resp.status_code = 503
    mock_get.return_value = resp

    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        assert lookup_mbid("Some Artist", cache) is None
        assert not cache.has("Some Artist")


@patch("festival_organizer.fanart.time.sleep")
@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_still_caches_a_genuine_miss(mock_get, _sleep):
    """A clean 'no such artist' answer is still negative-cached."""
    mock_get.return_value = _mb_response([])

    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        assert lookup_mbid("Nobody At All", cache) is None
        assert cache.has("Nobody At All")


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_never_resolves_the_id_placeholder(mock_get):
    """On 1001Tracklists, ID means "nobody knows", not an artist name.

    MusicBrainz has a real artist called exactly "ID" (techno producer
    Eddy L.), so a search would return an exact tier-1 hit and stamp every
    unidentified track with a real person's identity.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        assert lookup_mbid("ID", cache) is None
    mock_get.assert_not_called()


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_id_placeholder_is_case_insensitive(mock_get):
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        assert lookup_mbid("id", cache) is None
        assert lookup_mbid(" ID ", cache) is None
    mock_get.assert_not_called()


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_still_resolves_the_real_artist_id_id(mock_get):
    """The name ID ID belongs to a real MusicBrainz artist, not the guard."""
    mock_get.return_value = _mb_response(
        [{"id": "mbid-id-id", "score": 100, "name": "ID ID"}]
    )
    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        assert lookup_mbid("ID ID", cache) == "mbid-id-id"


@patch("festival_organizer.fanart.requests.get")
def test_lookup_mbid_no_name_match_returns_none(mock_get):
    """Returns None when no candidate name matches the query."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "artists": [
            {"id": "wrong-1", "score": 100, "name": "India Fisher"},
            {"id": "wrong-2", "score": 95, "name": "Eddie Fisher"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    with tempfile.TemporaryDirectory() as tmp:
        cache = MBIDCache(cache_dir=Path(tmp))
        result = lookup_mbid("FISHER", cache)
        assert result is None
        assert cache.get("FISHER") is None  # Negative cached


# --- fanart.tv API tests ---


@patch("festival_organizer.fanart.requests.get")
def test_fetch_artist_images_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "hdmusiclogo": [
            {"id": "1", "url": "http://logo.png", "lang": "en", "likes": "10"}
        ],
        "artistbackground": [{"id": "2", "url": "http://bg.jpg", "likes": "20"}],
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = fetch_artist_images("abc-123", "project-key", "personal-key")
    assert result is not None
    assert len(result["hdmusiclogo"]) == 1
    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args
    assert call_kwargs[1]["headers"]["api-key"] == "project-key"
    assert call_kwargs[1]["headers"]["client-key"] == "personal-key"


@patch("festival_organizer.fanart.requests.get")
def test_fetch_artist_images_404(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp

    result = fetch_artist_images("abc-123", "key")
    assert result is None


@patch("festival_organizer.fanart.requests.get")
def test_fetch_artist_images_no_personal_key(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    fetch_artist_images("abc-123", "project-key")
    headers = mock_get.call_args[1]["headers"]
    assert "api-key" in headers
    assert "client-key" not in headers


@patch("festival_organizer.fanart.time.sleep")
@patch("festival_organizer.fanart.requests.get")
def test_fetch_artist_images_logs_request_exception_retry(mock_get, _sleep, caplog):
    """RequestException retry branch logs DEBUG symmetric with 5xx retry branch."""
    import logging as _logging

    import requests as _requests

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = MagicMock()
    mock_get.side_effect = [_requests.ConnectionError("conn reset"), mock_resp]

    with caplog.at_level(_logging.DEBUG, logger="festival_organizer.fanart"):
        fetch_artist_images("abc-123", "project-key")
    joined = "\n".join(r.message for r in caplog.records)
    assert "fanart.api:" in joined
    assert "status=failed" in joined
    assert "conn reset" in joined
    assert "attempt=1" in joined


# --- FanartOperation tests ---


def test_fanart_op_not_needed_when_disabled():
    from festival_organizer.models import MediaFile
    from festival_organizer.operations import FanartOperation

    config = MagicMock()
    config.fanart_enabled = False
    config.fanart_project_api_key = "key"
    op = FanartOperation(config, library_root=Path("/tmp"), force=False)
    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
    assert op.is_needed(Path("/tmp/test.mkv"), mf) is False


def test_fanart_op_not_needed_when_no_key():
    from festival_organizer.models import MediaFile
    from festival_organizer.operations import FanartOperation

    config = MagicMock()
    config.fanart_enabled = True
    config.fanart_project_api_key = ""
    op = FanartOperation(config, library_root=Path("/tmp"), force=False)
    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
    assert op.is_needed(Path("/tmp/test.mkv"), mf) is False


def test_fanart_op_not_needed_when_images_exist(tmp_path):
    from festival_organizer.models import MediaFile
    from festival_organizer.operations import FanartOperation

    config = MagicMock()
    config.fanart_enabled = True
    config.fanart_project_api_key = "key"
    config.dj_cache = None
    op = FanartOperation(config, library_root=tmp_path, force=False)

    # Create existing images (folder key is the slugified artist name)
    artist_dir = tmp_path / "artists" / "hardwell"
    artist_dir.mkdir(parents=True)
    (artist_dir / "clearlogo.png").write_bytes(b"fake")
    (artist_dir / "fanart.jpg").write_bytes(b"fake")

    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
    with patch("festival_organizer.operations.paths.cache_dir", return_value=tmp_path):
        assert op.is_needed(Path("/tmp/test.mkv"), mf) is False


def test_fanart_op_needed_when_logo_missing(tmp_path):
    from festival_organizer.models import MediaFile
    from festival_organizer.operations import FanartOperation

    config = MagicMock()
    config.fanart_enabled = True
    config.fanart_project_api_key = "key"
    op = FanartOperation(config, library_root=tmp_path, force=False)

    # Only fanart.jpg exists, clearlogo missing
    artist_dir = tmp_path / "artists" / "Hardwell"
    artist_dir.mkdir(parents=True)
    (artist_dir / "fanart.jpg").write_bytes(b"fake")

    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
    with patch("festival_organizer.operations.paths.cache_dir", return_value=tmp_path):
        assert op.is_needed(Path("/tmp/test.mkv"), mf) is True


def test_fanart_op_deduplicates_artists(tmp_path):
    from festival_organizer.models import MediaFile
    from festival_organizer.operations import FanartOperation

    config = MagicMock()
    config.fanart_enabled = True
    config.fanart_project_api_key = "key"
    op = FanartOperation(config, library_root=tmp_path, force=False)

    # Mark artist as completed
    op._completed_artists.add("Hardwell")

    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
    assert op.is_needed(Path("/tmp/test.mkv"), mf) is False
