"""Tests for fanart.tv integration (all mocked, no real network calls)."""
import json
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
    download_artist_images,
    FanartError,
    MusicBrainzError,
    FanartAPIError,
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
    artist_dir = tmp_path / ".cratedigger" / "artists" / "Hardwell"
    artist_dir.mkdir(parents=True)
    (artist_dir / "clearlogo.png").write_bytes(b"fake")
    (artist_dir / "fanart.jpg").write_bytes(b"fake")

    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
    assert op.is_needed(Path("/tmp/test.mkv"), mf) is False


def test_fanart_op_needed_when_logo_missing(tmp_path):
    from festival_organizer.operations import FanartOperation
    from festival_organizer.models import MediaFile

    config = MagicMock()
    config.fanart_enabled = True
    config.fanart_project_api_key = "key"
    op = FanartOperation(config, library_root=tmp_path, force=False)

    # Only fanart.jpg exists, clearlogo missing
    artist_dir = tmp_path / ".cratedigger" / "artists" / "Hardwell"
    artist_dir.mkdir(parents=True)
    (artist_dir / "fanart.jpg").write_bytes(b"fake")

    mf = MediaFile(source_path=Path("/tmp/test.mkv"), artist="Hardwell")
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
