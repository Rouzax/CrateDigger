"""Tests for tracklist query building."""
from pathlib import Path
import pytest
from festival_organizer.tracklists.query import (
    build_search_query,
    detect_tracklist_source,
    extract_tracklist_id,
)


def test_build_search_query_strips_extension():
    result = build_search_query(Path("2025 - AMF - Sub Zero Project.mkv"))
    assert ".mkv" not in result
    assert "Sub Zero Project" in result


def test_build_search_query_strips_youtube_id():
    result = build_search_query(Path("Artist live at Festival 2025 [dQw4w9WgXcQ].mkv"))
    assert "dQw4w9WgXcQ" not in result
    assert "Artist" in result


def test_build_search_query_strips_scene_tags():
    result = build_search_query(Path("glastonbury.2016.coldplay.1080p.hdtv.x264-verum.mkv"))
    assert "1080p" not in result
    assert "hdtv" not in result


def test_build_search_query_converts_separators():
    result = build_search_query(Path("Artist_Name-Festival.2025.mkv"))
    assert "_" not in result
    # separators become spaces


def test_build_search_query_strips_noise():
    result = build_search_query(Path("Martin Garrix Full Set AMF 2024.mkv"))
    assert "Full Set" not in result


def test_build_search_query_normalizes_unicode_slashes():
    """Unicode fraction slashes (KI⧸KI) should become spaces."""
    result = build_search_query(Path("Armin van Buuren & KI⧸KI live at AMF 2025 [WownWX6HUTs].mkv"))
    assert "⧸" not in result
    assert "KI" in result


def test_detect_tracklist_source_url():
    result = detect_tracklist_source("https://www.1001tracklists.com/tracklist/1g6g22ut/test.html")
    assert result["type"] == "url"
    assert "1001tracklists" in result["value"]


def test_detect_tracklist_source_id():
    result = detect_tracklist_source("1g6g22ut")
    assert result["type"] == "id"
    assert result["value"] == "1g6g22ut"


def test_detect_tracklist_source_search():
    result = detect_tracklist_source("Martin Garrix AMF 2024")
    assert result["type"] == "search"


def test_detect_tracklist_source_id_too_short():
    result = detect_tracklist_source("abc")
    assert result["type"] == "search"  # too short for ID


def test_extract_tracklist_id():
    assert extract_tracklist_id("https://www.1001tracklists.com/tracklist/1g6g22ut/sub-zero-project.html") == "1g6g22ut"


def test_extract_tracklist_id_short_url():
    assert extract_tracklist_id("https://www.1001tracklists.com/tracklist/qv6kl89/") == "qv6kl89"


def test_extract_tracklist_id_invalid():
    with pytest.raises(ValueError):
        extract_tracklist_id("https://example.com/not-a-tracklist")


from festival_organizer.tracklists.query import expand_aliases_in_query


def test_expand_aliases_replaces_abbreviation():
    aliases = {"amf": "Amsterdam Music Festival"}
    result = expand_aliases_in_query("Armin van Buuren live at AMF 2025", aliases)
    assert "Amsterdam Music Festival" in result
    assert "AMF" not in result


def test_expand_aliases_case_insensitive():
    aliases = {"edc": "Electric Daisy Carnival"}
    result = expand_aliases_in_query("Tiesto EDC Las Vegas", aliases)
    assert "Electric Daisy Carnival" in result


def test_expand_aliases_no_match_unchanged():
    aliases = {"amf": "Amsterdam Music Festival"}
    result = expand_aliases_in_query("Hardwell Tomorrowland 2025", aliases)
    assert result == "Hardwell Tomorrowland 2025"


def test_expand_aliases_word_boundary():
    """Should not replace partial word matches."""
    aliases = {"ed": "Something"}
    result = expand_aliases_in_query("Red Rocks 2025", aliases)
    assert result == "Red Rocks 2025"  # "ed" in "Red" should NOT match
