"""Tests for fanart.tv integration (all mocked, no real network calls)."""
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from festival_organizer.fanart import (
    MBIDCache,
    split_artists,
    pick_best_logo,
    pick_best_background,
    lookup_mbid,
    fetch_artist_images,
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
        "hdmusiclogo": [{"id": "1", "url": "http://logo.png", "lang": "en", "likes": "10"}],
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
    assert "fanart.tv request failed" in joined
    assert "conn reset" in joined
    assert "attempt 1/3" in joined


# --- FanartOperation tests ---

def test_fanart_op_not_needed_when_disabled():
    from festival_organizer.operations import FanartOperation
    from festival_organizer.models import MediaFile

    config = MagicMock()
    config.fanart_enabled = False
    config.fanart_project_api_key = "key"
    op = FanartOperation(config, library_root=Path("/tmp"), force=False)
    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
    assert op.is_needed(Path("/tmp/test.mkv"), mf) is False


def test_fanart_op_not_needed_when_no_key():
    from festival_organizer.operations import FanartOperation
    from festival_organizer.models import MediaFile

    config = MagicMock()
    config.fanart_enabled = True
    config.fanart_project_api_key = ""
    op = FanartOperation(config, library_root=Path("/tmp"), force=False)
    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
    assert op.is_needed(Path("/tmp/test.mkv"), mf) is False


def test_fanart_op_not_needed_when_images_exist(tmp_path):
    from festival_organizer.operations import FanartOperation
    from festival_organizer.models import MediaFile

    config = MagicMock()
    config.fanart_enabled = True
    config.fanart_project_api_key = "key"
    op = FanartOperation(config, library_root=tmp_path, force=False)

    # Create existing images
    artist_dir = tmp_path / "artists" / "Hardwell"
    artist_dir.mkdir(parents=True)
    (artist_dir / "clearlogo.png").write_bytes(b"fake")
    (artist_dir / "fanart.jpg").write_bytes(b"fake")

    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
    with patch("festival_organizer.operations.paths.cache_dir", return_value=tmp_path):
        assert op.is_needed(Path("/tmp/test.mkv"), mf) is False


def test_fanart_op_needed_when_logo_missing(tmp_path):
    from festival_organizer.operations import FanartOperation
    from festival_organizer.models import MediaFile

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
    from festival_organizer.operations import FanartOperation
    from festival_organizer.models import MediaFile

    config = MagicMock()
    config.fanart_enabled = True
    config.fanart_project_api_key = "key"
    op = FanartOperation(config, library_root=tmp_path, force=False)

    # Mark artist as completed
    op._completed_artists.add("Hardwell")

    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
    assert op.is_needed(Path("/tmp/test.mkv"), mf) is False
