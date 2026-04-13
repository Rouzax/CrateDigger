"""ChapterMbidsOperation: orchestrate extract → compute → merge → write."""
from pathlib import Path
from unittest.mock import patch

from festival_organizer.models import MediaFile
from festival_organizer.operations import ChapterMbidsOperation


def _make_mf():
    return MediaFile(
        source_path=Path("test.mkv"),
        artist="Test",
        festival="TML",
        year="2024",
        content_type="festival_set",
    )


def test_is_needed_false_without_matroska_extension(tmp_path):
    op = ChapterMbidsOperation()
    (tmp_path / "foo.mp4").write_bytes(b"")
    assert op.is_needed(tmp_path / "foo.mp4", _make_mf()) is False


def test_is_needed_true_for_mkv(tmp_path):
    op = ChapterMbidsOperation()
    (tmp_path / "foo.mkv").write_bytes(b"")
    assert op.is_needed(tmp_path / "foo.mkv", _make_mf()) is True


def test_is_needed_true_for_webm(tmp_path):
    op = ChapterMbidsOperation()
    (tmp_path / "foo.webm").write_bytes(b"")
    assert op.is_needed(tmp_path / "foo.webm", _make_mf()) is True


def test_execute_writes_mbids_aligned_with_names(tmp_path):
    existing = {
        111: {
            "PERFORMER": "Afrojack & Oliver Heldens",
            "PERFORMER_SLUGS": "afrojack|oliver-heldens",
            "PERFORMER_NAMES": "Afrojack|Oliver Heldens",
            "TITLE": "Happy",
        },
        222: {
            "PERFORMER": "Afrojack vs. Mystery ID vs. Tiësto",
            "PERFORMER_SLUGS": "afrojack|mystery-id|tiesto",
            "PERFORMER_NAMES": "Afrojack|Mystery ID|Tiësto",
        },
    }

    def fake_lookup(name, cache, overrides=None):
        return {"Afrojack": "A", "Oliver Heldens": "O", "Tiësto": "T"}.get(name)

    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")

    with patch("festival_organizer.operations._extract_chapter_tags_by_uid",
               return_value=existing), \
         patch("festival_organizer.operations.write_chapter_mbid_tags") as write_fn, \
         patch("festival_organizer.operations.lookup_mbid", side_effect=fake_lookup):
        op = ChapterMbidsOperation()
        result = op.execute(mkv, _make_mf())

    assert result.status == "done"
    write_fn.assert_called_once()
    call_args = write_fn.call_args
    _, merged_chapter_tags = call_args.args
    # MBIDs must be present and aligned.
    assert merged_chapter_tags[111]["MUSICBRAINZ_ARTISTIDS"] == "A|O"
    assert merged_chapter_tags[222]["MUSICBRAINZ_ARTISTIDS"] == "A||T"
    # Existing tags MUST be preserved (they would be wiped if we passed only the MBID dict).
    assert merged_chapter_tags[111]["PERFORMER"] == "Afrojack & Oliver Heldens"
    assert merged_chapter_tags[111]["PERFORMER_NAMES"] == "Afrojack|Oliver Heldens"
    assert merged_chapter_tags[111]["PERFORMER_SLUGS"] == "afrojack|oliver-heldens"
    assert merged_chapter_tags[111]["TITLE"] == "Happy"
    assert merged_chapter_tags[222]["PERFORMER"] == "Afrojack vs. Mystery ID vs. Tiësto"


def test_execute_skipped_when_no_chapter_tags(tmp_path):
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    with patch("festival_organizer.operations._extract_chapter_tags_by_uid",
               return_value={}), \
         patch("festival_organizer.operations.write_chapter_mbid_tags") as write_fn:
        op = ChapterMbidsOperation()
        result = op.execute(mkv, _make_mf())
    assert result.status == "skipped"
    write_fn.assert_not_called()


def test_execute_skipped_when_no_performer_names(tmp_path):
    # Legacy file: chapter tags exist but none carry PERFORMER_NAMES.
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    with patch("festival_organizer.operations._extract_chapter_tags_by_uid",
               return_value={111: {"PERFORMER": "Afrojack"}}), \
         patch("festival_organizer.operations.write_chapter_mbid_tags") as write_fn:
        op = ChapterMbidsOperation()
        result = op.execute(mkv, _make_mf())
    assert result.status == "skipped"
    write_fn.assert_not_called()


def test_execute_skipped_when_mbids_already_current(tmp_path):
    existing = {
        111: {
            "PERFORMER_NAMES": "Afrojack",
            "MUSICBRAINZ_ARTISTIDS": "A",
        },
    }
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    with patch("festival_organizer.operations._extract_chapter_tags_by_uid",
               return_value=existing), \
         patch("festival_organizer.operations.write_chapter_mbid_tags") as write_fn, \
         patch("festival_organizer.operations.lookup_mbid", return_value="A"):
        op = ChapterMbidsOperation()
        result = op.execute(mkv, _make_mf())
    assert result.status == "skipped"
    write_fn.assert_not_called()


def test_force_rewrites_even_when_mbids_already_match(tmp_path):
    existing = {
        111: {
            "PERFORMER_NAMES": "Afrojack",
            "MUSICBRAINZ_ARTISTIDS": "A",
        },
    }
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    with patch("festival_organizer.operations._extract_chapter_tags_by_uid",
               return_value=existing), \
         patch("festival_organizer.operations.write_chapter_mbid_tags") as write_fn, \
         patch("festival_organizer.operations.lookup_mbid", return_value="A"):
        op = ChapterMbidsOperation(force=True)
        result = op.execute(mkv, _make_mf())
    assert result.status == "done"
    write_fn.assert_called_once()


def test_force_rewrites_when_stale_mbids_present(tmp_path):
    existing = {
        111: {
            "PERFORMER_NAMES": "Afrojack",
            "MUSICBRAINZ_ARTISTIDS": "STALE",
        },
    }
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    with patch("festival_organizer.operations._extract_chapter_tags_by_uid",
               return_value=existing), \
         patch("festival_organizer.operations.write_chapter_mbid_tags") as write_fn, \
         patch("festival_organizer.operations.lookup_mbid", return_value="FRESH"):
        op = ChapterMbidsOperation()
        result = op.execute(mkv, _make_mf())
    assert result.status == "done"
    _, merged = write_fn.call_args.args
    assert merged[111]["MUSICBRAINZ_ARTISTIDS"] == "FRESH"
