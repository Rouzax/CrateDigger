"""Tests for chapter XML generation and parsing."""
import logging
import subprocess as subprocess_mod
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from festival_organizer.tracklists.chapters import (
    normalize_timestamp,
    parse_tracklist_lines,
    build_chapter_xml,
    build_tags_xml,
    chapters_are_identical,
    extract_existing_chapters,
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


# --- build_tags_xml ---

def test_build_tags_xml_structure():
    xml_str = build_tags_xml(
        "https://www.1001tracklists.com/tracklist/1g6g22ut/",
        "Artist @ Festival 2025"
    )
    root = ET.fromstring(xml_str)
    assert root.tag == "Tags"

    tag = root.find("Tag")
    ttv = tag.find("Targets/TargetTypeValue")
    assert ttv.text == "70"

    # Find URL and title
    simples = tag.findall("Simple")
    names = {s.find("Name").text: s.find("String").text for s in simples}
    assert names["1001TRACKLISTS_URL"] == "https://www.1001tracklists.com/tracklist/1g6g22ut/"
    assert names["1001TRACKLISTS_TITLE"] == "Artist @ Festival 2025"


def test_build_tags_xml_url_only():
    xml_str = build_tags_xml("https://www.1001tracklists.com/tracklist/abc123/")
    root = ET.fromstring(xml_str)
    simples = root.findall(".//Simple")
    assert len(simples) == 1
    assert simples[0].find("Name").text == "1001TRACKLISTS_URL"


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
