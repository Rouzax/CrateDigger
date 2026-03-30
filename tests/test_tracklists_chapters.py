"""Tests for chapter XML generation and parsing."""
import logging
import subprocess as subprocess_mod
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch, MagicMock

from festival_organizer.tracklists.chapters import (
    normalize_timestamp,
    parse_tracklist_lines,
    build_chapter_xml,
    chapters_are_identical,
    extract_existing_chapters,
    embed_chapters,
    Chapter,
)
import pytest


# --- normalize_timestamp ---

def test_normalize_timestamp_mm_ss():
    assert normalize_timestamp("5:30") == "00:05:30.000"


def test_normalize_timestamp_mm_ss_padded():
    assert normalize_timestamp("05:30") == "00:05:30.000"


def test_normalize_timestamp_hh_mm_ss():
    assert normalize_timestamp("1:15:30") == "01:15:30.000"


def test_normalize_timestamp_with_millis():
    assert normalize_timestamp("1:15:30.5") == "01:15:30.500"


def test_normalize_timestamp_full_millis():
    assert normalize_timestamp("01:15:30.123") == "01:15:30.123"


def test_normalize_timestamp_invalid():
    with pytest.raises(ValueError):
        normalize_timestamp("invalid")


# --- parse_tracklist_lines ---

def test_parse_tracklist_lines_basic():
    lines = [
        "[03:45] Artist1 - Track One",
        "[07:20] Artist2 - Track Two",
        "[12:00] Artist3 - Track Three",
    ]
    chapters = parse_tracklist_lines(lines)
    assert len(chapters) == 3
    assert chapters[0].timestamp == "00:03:45.000"
    assert chapters[0].title == "Artist1 - Track One"
    assert chapters[2].timestamp == "00:12:00.000"


def test_parse_tracklist_lines_hh_mm_ss():
    lines = ["[1:05:30] Artist - Late Track"]
    chapters = parse_tracklist_lines(lines)
    assert len(chapters) == 1
    assert chapters[0].timestamp == "01:05:30.000"


def test_parse_tracklist_lines_empty():
    assert parse_tracklist_lines([]) == []
    assert parse_tracklist_lines(["", "  ", ""]) == []


def test_parse_tracklist_lines_no_timestamps_raises():
    lines = [
        "1. Artist1 - Track One",
        "2. Artist2 - Track Two",
    ]
    with pytest.raises(ValueError, match="no timestamps"):
        parse_tracklist_lines(lines)


def test_parse_tracklist_lines_custom_language():
    lines = ["[00:00] First Track"]
    chapters = parse_tracklist_lines(lines, language="dut")
    assert chapters[0].language == "dut"


# --- build_chapter_xml ---

def test_build_chapter_xml_structure():
    chapters = [
        Chapter(timestamp="00:03:45.000", title="Track One"),
        Chapter(timestamp="00:07:20.000", title="Track Two"),
    ]
    xml_str = build_chapter_xml(chapters)

    # Should be valid XML
    root = ET.fromstring(xml_str)
    assert root.tag == "Chapters"

    edition = root.find("EditionEntry")
    assert edition is not None

    atoms = edition.findall("ChapterAtom")
    assert len(atoms) == 2

    # First chapter
    assert atoms[0].find("ChapterTimeStart").text == "00:03:45.000"
    assert atoms[0].find("ChapterDisplay/ChapterString").text == "Track One"
    assert atoms[0].find("ChapterDisplay/ChapterLanguage").text == "eng"

    # UIDs should be present and unique
    uid1 = atoms[0].find("ChapterUID").text
    uid2 = atoms[1].find("ChapterUID").text
    assert uid1 != uid2


def test_build_chapter_xml_escapes_special_chars():
    chapters = [Chapter(timestamp="00:00:00.000", title="Artist & Other <Live>")]
    xml_str = build_chapter_xml(chapters)
    # Should be parseable (ET handles escaping)
    root = ET.fromstring(xml_str)
    title = root.find(".//ChapterString").text
    assert title == "Artist & Other <Live>"


# --- chapters_are_identical ---

def test_chapters_identical_same():
    a = [Chapter("00:03:45.000", "Track One"), Chapter("00:07:20.000", "Track Two")]
    b = [Chapter("00:03:45.000", "Track One"), Chapter("00:07:20.000", "Track Two")]
    assert chapters_are_identical(a, b) is True


def test_chapters_identical_different_count():
    a = [Chapter("00:03:45.000", "Track One")]
    b = [Chapter("00:03:45.000", "Track One"), Chapter("00:07:20.000", "Track Two")]
    assert chapters_are_identical(a, b) is False


def test_chapters_identical_different_timestamp():
    a = [Chapter("00:03:45.000", "Track One")]
    b = [Chapter("00:03:50.000", "Track One")]
    assert chapters_are_identical(a, b) is False


def test_chapters_identical_different_title():
    a = [Chapter("00:03:45.000", "Track One")]
    b = [Chapter("00:03:45.000", "Track Two")]
    assert chapters_are_identical(a, b) is False


def test_chapters_identical_none_existing():
    b = [Chapter("00:03:45.000", "Track One")]
    assert chapters_are_identical(None, b) is False


def test_chapters_identical_millis_ignored():
    a = [Chapter("00:03:45.123", "Track")]
    b = [Chapter("00:03:45.456", "Track")]
    # Same to mm:ss precision
    assert chapters_are_identical(a, b) is True


# --- extract_existing_chapters error logging ---

def test_extract_chapters_failure_logged(tmp_path, caplog):
    """Chapter extraction failure is logged at debug level."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")

    with patch("festival_organizer.tracklists.chapters.metadata.MKVEXTRACT_PATH", "/usr/bin/mkvextract"):
        with patch("festival_organizer.tracklists.chapters.subprocess.run",
                   side_effect=subprocess_mod.SubprocessError("timeout")):
            with caplog.at_level(logging.DEBUG, logger="festival_organizer.tracklists.chapters"):
                result = extract_existing_chapters(video)
    assert result is None
    assert "timeout" in caplog.text


# --- embed_chapters ---

def test_embed_chapters_uses_merged_tags(tmp_path):
    """embed_chapters uses write_merged_tags for 1001TL tags."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    chapters = [Chapter("00:03:45.000", "Track One")]

    with patch("festival_organizer.tracklists.chapters.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.tracklists.chapters.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            with patch("festival_organizer.tracklists.chapters.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = embed_chapters(
                    video, chapters,
                    tracklist_url="https://example.com/tracklist/abc123/",
                    tracklist_title="Artist @ Festival",
                )

    assert result is True
    mock_run.assert_called_once()
    assert "--chapters" in mock_run.call_args[0][0]
    mock_wmt.assert_called_once()
    tags_dict = mock_wmt.call_args[0][1]
    assert 70 in tags_dict
    assert tags_dict[70]["CRATEDIGGER_1001TL_URL"] == "https://example.com/tracklist/abc123/"
    assert tags_dict[70]["CRATEDIGGER_1001TL_TITLE"] == "Artist @ Festival"


def test_embed_chapters_writes_all_new_tag_names(tmp_path):
    """embed_chapters writes all tags with CRATEDIGGER_1001TL_ prefix."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    chapters = [Chapter("00:03:45.000", "Track One")]

    with patch("festival_organizer.tracklists.chapters.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.tracklists.chapters.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            with patch("festival_organizer.tracklists.chapters.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                embed_chapters(
                    video, chapters,
                    tracklist_url="https://example.com/tracklist/abc123/",
                    tracklist_title="Artist @ Festival",
                    tracklist_id="12345",
                    tracklist_date="2025-01-01",
                    genres=["Trance", "House"],
                    dj_artwork_url="https://dj.jpg",
                )

    tags_dict = mock_wmt.call_args[0][1]
    tags = tags_dict[70]
    assert tags["CRATEDIGGER_1001TL_URL"] == "https://example.com/tracklist/abc123/"
    assert tags["CRATEDIGGER_1001TL_TITLE"] == "Artist @ Festival"
    assert tags["CRATEDIGGER_1001TL_ID"] == "12345"
    assert tags["CRATEDIGGER_1001TL_DATE"] == "2025-01-01"
    assert tags["CRATEDIGGER_1001TL_GENRES"] == "Trance|House"
    assert tags["CRATEDIGGER_1001TL_DJ_ARTWORK"] == "https://dj.jpg"
    # Ensure old names are NOT used
    assert "1001TRACKLISTS_URL" not in tags


def test_extract_stored_tracklist_info_reads_new_tags(tmp_path):
    """extract_stored_tracklist_info reads CRATEDIGGER_1001TL_* tags."""
    from festival_organizer.tracklists.chapters import extract_stored_tracklist_info

    new_tags_xml = ET.Element("Tags")
    tag = ET.SubElement(new_tags_xml, "Tag")
    targets = ET.SubElement(tag, "Targets")
    ttv = ET.SubElement(targets, "TargetTypeValue")
    ttv.text = "70"
    for name, value in [
        ("CRATEDIGGER_1001TL_URL", "https://new-url.com"),
        ("CRATEDIGGER_1001TL_TITLE", "New Title"),
        ("CRATEDIGGER_1001TL_ID", "abc123"),
    ]:
        simple = ET.SubElement(tag, "Simple")
        n = ET.SubElement(simple, "Name")
        n.text = name
        s = ET.SubElement(simple, "String")
        s.text = value

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")

    with patch("festival_organizer.tracklists.chapters.extract_all_tags", return_value=new_tags_xml):
        result = extract_stored_tracklist_info(video)

    assert result is not None
    assert result["url"] == "https://new-url.com"
    assert result["title"] == "New Title"
    assert result["id"] == "abc123"


def test_extract_stored_tracklist_info_reads_old_tags(tmp_path):
    """extract_stored_tracklist_info still reads old 1001TRACKLISTS_* tags."""
    from festival_organizer.tracklists.chapters import extract_stored_tracklist_info

    old_tags_xml = ET.Element("Tags")
    tag = ET.SubElement(old_tags_xml, "Tag")
    targets = ET.SubElement(tag, "Targets")
    ttv = ET.SubElement(targets, "TargetTypeValue")
    ttv.text = "70"
    for name, value in [
        ("1001TRACKLISTS_URL", "https://old-url.com"),
        ("1001TRACKLISTS_TITLE", "Old Title"),
    ]:
        simple = ET.SubElement(tag, "Simple")
        n = ET.SubElement(simple, "Name")
        n.text = name
        s = ET.SubElement(simple, "String")
        s.text = value

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")

    with patch("festival_organizer.tracklists.chapters.extract_all_tags", return_value=old_tags_xml):
        result = extract_stored_tracklist_info(video)

    assert result is not None
    assert result["url"] == "https://old-url.com"
    assert result["title"] == "Old Title"
