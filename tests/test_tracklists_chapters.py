"""Tests for chapter XML generation and parsing."""
import logging
import subprocess as subprocess_mod
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock

from festival_organizer.tracklists.chapters import (
    normalize_timestamp,
    _timestamp_to_seconds,
    parse_tracklist_lines,
    build_chapter_xml,
    chapters_are_identical,
    extract_existing_chapters,
    embed_chapters,
    trim_chapters_to_duration,
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


# --- _timestamp_to_seconds ---

def test_timestamp_to_seconds_zero():
    assert _timestamp_to_seconds("00:00:00.000") == 0.0


def test_timestamp_to_seconds_minutes():
    assert _timestamp_to_seconds("00:03:45.000") == 225.0


def test_timestamp_to_seconds_hours():
    assert _timestamp_to_seconds("01:30:00.000") == 5400.0


def test_timestamp_to_seconds_millis():
    assert _timestamp_to_seconds("00:00:01.500") == 1.5


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


# --- mashup filtering ---

def test_parse_tracklist_filters_mashup_at_start():
    """Mashup stack at the start: [00:00] and [00:01] are <5s apart, drop [00:00]."""
    lines = [
        "[00:00] Mashup Intro Track",
        "[00:01] Real First Track",
        "[01:16] Second Track",
    ]
    chapters = parse_tracklist_lines(lines)
    assert len(chapters) == 2
    assert chapters[0].title == "Real First Track"
    assert chapters[0].timestamp == "00:00:01.000"
    assert chapters[1].title == "Second Track"


def test_parse_tracklist_filters_mashup_mid_set():
    """Mashup in the middle of a set."""
    lines = [
        "[10:00] Track A",
        "[15:00] Mashup Component",
        "[15:02] Real Track B",
        "[20:00] Track C",
    ]
    chapters = parse_tracklist_lines(lines)
    assert len(chapters) == 3
    assert chapters[0].title == "Track A"
    assert chapters[1].title == "Real Track B"
    assert chapters[2].title == "Track C"


def test_parse_tracklist_filters_chain_of_close_chapters():
    """Three chapters within threshold: only the last survives."""
    lines = [
        "[00:00] Layer 1",
        "[00:01] Layer 2",
        "[00:03] Actual Track",
        "[05:00] Next Track",
    ]
    chapters = parse_tracklist_lines(lines)
    assert len(chapters) == 2
    assert chapters[0].title == "Actual Track"
    assert chapters[1].title == "Next Track"


def test_parse_tracklist_keeps_chapters_at_threshold():
    """Chapters exactly 5s apart are kept (threshold is strictly less than)."""
    lines = [
        "[00:00] Track One",
        "[00:05] Track Two",
        "[05:00] Track Three",
    ]
    chapters = parse_tracklist_lines(lines)
    assert len(chapters) == 3


def test_parse_tracklist_no_filter_normal_tracklist():
    """Normal tracklist with no close pairs is unchanged."""
    lines = [
        "[03:45] Artist1 - Track One",
        "[07:20] Artist2 - Track Two",
        "[12:00] Artist3 - Track Three",
    ]
    chapters = parse_tracklist_lines(lines)
    assert len(chapters) == 3
    assert chapters[0].title == "Artist1 - Track One"


def test_parse_tracklist_mashup_filter_logs(caplog):
    """Mashup filtering logs dropped chapters at INFO."""
    lines = [
        "[00:00] Mashup Intro",
        "[00:01] Real Track",
        "[05:00] Next Track",
    ]
    with caplog.at_level(logging.INFO, logger="festival_organizer.tracklists.chapters"):
        parse_tracklist_lines(lines)
    assert "Mashup Intro" in caplog.text


# --- trim_chapters_to_duration ---

def _chs(*seconds: float) -> list[Chapter]:
    """Build chapters from seconds: _chs(0, 60, 120) -> 3 chapters at those times."""
    out = []
    for s in seconds:
        h, rem = divmod(int(s), 3600)
        m, sec = divmod(rem, 60)
        out.append(Chapter(timestamp=f"{h:02d}:{m:02d}:{sec:02d}.000", title=f"Track {s:.0f}s"))
    return out


def test_trim_no_duration_passes_through():
    chapters = _chs(0, 60, 120)
    assert trim_chapters_to_duration(chapters, None) == chapters


def test_trim_duration_covers_all_no_change():
    chapters = _chs(0, 60, 120)
    # Duration well past last chapter
    assert trim_chapters_to_duration(chapters, 300.0) == chapters


def test_trim_drops_chapters_past_end():
    # Video is 100s long; chapters at 0, 60, 120, 180 should keep only first two
    chapters = _chs(0, 60, 120, 180)
    result = trim_chapters_to_duration(chapters, 100.0)
    assert len(result) == 2
    assert result[0].title == "Track 0s"
    assert result[1].title == "Track 60s"


def test_trim_drops_chapter_within_epsilon():
    # Chapter at 99s, duration 100s, default epsilon 2s -> cutoff 98s -> drop 99s chapter
    chapters = _chs(0, 60, 99)
    result = trim_chapters_to_duration(chapters, 100.0)
    assert len(result) == 2
    assert all(ch.title != "Track 99s" for ch in result)


def test_trim_keeps_chapter_before_epsilon():
    # Chapter at 90s, duration 100s, epsilon 2s -> cutoff 98s -> keep 90s chapter
    chapters = _chs(0, 60, 90)
    result = trim_chapters_to_duration(chapters, 100.0)
    assert len(result) == 3


def test_trim_logs_when_dropping(caplog):
    chapters = _chs(0, 60, 120, 180)
    with caplog.at_level(logging.INFO, logger="festival_organizer.tracklists.chapters"):
        trim_chapters_to_duration(chapters, 100.0)
    assert "Trimmed 2 chapters" in caplog.text
    assert "duration=100.0s" in caplog.text


def test_trim_no_log_when_nothing_dropped(caplog):
    chapters = _chs(0, 60, 120)
    with caplog.at_level(logging.INFO, logger="festival_organizer.tracklists.chapters"):
        trim_chapters_to_duration(chapters, 300.0)
    assert "Trimmed" not in caplog.text


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


# --- build_chapter_xml return_uids ---

def test_build_chapter_xml_default_return_is_string():
    """Backwards-compat: default call returns just the XML string."""
    from festival_organizer.tracklists.chapters import Chapter, build_chapter_xml
    result = build_chapter_xml([Chapter(timestamp="00:00:00.000", title="Intro")])
    assert isinstance(result, str)
    assert "<Chapters>" in result


def test_build_chapter_xml_return_uids_tuple_shape():
    """return_uids=True yields (xml_str, [uids])."""
    from festival_organizer.tracklists.chapters import Chapter, build_chapter_xml
    chapters = [
        Chapter(timestamp="00:00:00.000", title="A"),
        Chapter(timestamp="00:01:00.000", title="B"),
        Chapter(timestamp="00:02:00.000", title="C"),
    ]
    xml_str, uids = build_chapter_xml(chapters, return_uids=True)
    assert isinstance(xml_str, str)
    assert isinstance(uids, list)
    assert len(uids) == 3
    assert all(isinstance(u, int) and u > 0 for u in uids)


def test_build_chapter_xml_uids_match_xml():
    """The returned UIDs are the same ones embedded in the generated XML."""
    import xml.etree.ElementTree as ET
    from festival_organizer.tracklists.chapters import Chapter, build_chapter_xml
    chapters = [
        Chapter(timestamp="00:00:00.000", title="A"),
        Chapter(timestamp="00:01:00.000", title="B"),
    ]
    xml_str, uids = build_chapter_xml(chapters, return_uids=True)
    root = ET.fromstring(xml_str[xml_str.index("<Chapters>"):])
    atoms = root.findall(".//ChapterAtom")
    xml_uids = [int(a.find("ChapterUID").text) for a in atoms]
    assert xml_uids == uids


def test_build_chapter_xml_uids_are_stable_across_calls():
    """Deterministic ChapterUIDs: same input always produces same UIDs so
    re-enrichment is byte-idempotent when source data is unchanged."""
    from festival_organizer.tracklists.chapters import Chapter, build_chapter_xml
    chapters = [
        Chapter(timestamp="00:00:00.000", title="Intro"),
        Chapter(timestamp="00:03:30.000", title="Second Track [LABEL]"),
        Chapter(timestamp="00:07:15.000", title="Third"),
    ]
    _, uids_a = build_chapter_xml(chapters, return_uids=True)
    _, uids_b = build_chapter_xml(chapters, return_uids=True)
    assert uids_a == uids_b, "ChapterUIDs must be deterministic across calls"


def test_build_chapter_xml_uid_depends_on_both_ts_and_title():
    """Different (timestamp, title) must produce different UIDs."""
    from festival_organizer.tracklists.chapters import Chapter, build_chapter_xml
    # Same title, different timestamp
    _, uids_a = build_chapter_xml([Chapter(timestamp="00:00:00.000", title="A")], return_uids=True)
    _, uids_b = build_chapter_xml([Chapter(timestamp="00:01:00.000", title="A")], return_uids=True)
    assert uids_a != uids_b
    # Same timestamp, different title
    _, uids_c = build_chapter_xml([Chapter(timestamp="00:00:00.000", title="B")], return_uids=True)
    assert uids_a != uids_c


def test_build_chapter_xml_uid_is_positive():
    """Matroska requires ChapterUID > 0. Our hash-based UIDs must satisfy that."""
    from festival_organizer.tracklists.chapters import Chapter, build_chapter_xml
    chapters = [Chapter(timestamp=f"00:0{i}:00.000", title=f"t{i}") for i in range(10)]
    _, uids = build_chapter_xml(chapters, return_uids=True)
    assert all(u > 0 for u in uids)
