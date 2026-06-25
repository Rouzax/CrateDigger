"""Tests for the content-aware self-heal predicate chapter_tags_need_refresh."""

from pathlib import Path
from unittest.mock import patch

from festival_organizer.tracklists.api import Track
from festival_organizer.tracklists.chapters import (
    Chapter,
    build_chapter_xml,
    chapter_tags_need_refresh,
)
from festival_organizer.tracklists.overlays import (
    AssembledChapter,
    build_chapter_tags_from_assembled,
    combined_title,
)


def _track(raw_text, slugs, names, title, label=""):
    return Track(
        start_ms=0,
        raw_text=raw_text,
        artist_slugs=slugs,
        artist_names=names,
        genres=[],
        title=title,
        label=label,
    )


def _build():
    """One chapter: anchor with a folded 'w/' overlay (a mashup append)."""
    primary = _track(
        "House Of Pain - Jump Around",
        ["house-of-pain"],
        ["House Of Pain"],
        "Jump Around",
    )
    overlay = _track(
        "Cloonee - Stephanie (HNTR VIP)",
        ["cloonee"],
        ["Cloonee"],
        "Stephanie (HNTR VIP)",
    )
    ac = AssembledChapter(
        start_ms=0,
        title=combined_title([primary, overlay]),
        primary=primary,
        contributors=[overlay],
    )
    chapters = [Chapter(timestamp="00:00:00.000", title=ac.title, language="eng")]
    _, uids = build_chapter_xml(chapters, return_uids=True)
    desired = build_chapter_tags_from_assembled([ac], uids, mashup_metadata=True)
    return [ac], chapters, uids[0], desired[uids[0]]


def test_no_refresh_when_embedded_matches_desired():
    assembled, chapters, uid, desired_block = _build()
    with patch(
        "festival_organizer.mkv_tags.extract_chapter_tags_by_uid",
        return_value={uid: dict(desired_block)},
    ):
        assert not chapter_tags_need_refresh(
            Path("x.mkv"), assembled, chapters, mashup_metadata=True
        )


def test_refresh_when_embedded_title_is_truncated():
    """Old (buggy) embed carried only the base track in the single-value tags."""
    assembled, chapters, uid, desired_block = _build()
    stale = dict(desired_block)
    stale["CRATEDIGGER_TRACK_TITLE"] = "Jump Around"  # missing 'vs. Stephanie ...'
    stale["CRATEDIGGER_TRACK_PERFORMER"] = "House Of Pain"  # missing 'vs. Cloonee'
    with patch(
        "festival_organizer.mkv_tags.extract_chapter_tags_by_uid",
        return_value={uid: stale},
    ):
        assert chapter_tags_need_refresh(
            Path("x.mkv"), assembled, chapters, mashup_metadata=True
        )


def test_no_refresh_when_only_enrich_managed_mbids_differ():
    """MUSICBRAINZ_ARTISTIDS is enrich-managed and not produced here; its presence
    on the embedded block must not flag the chapter as stale (else every enriched
    file would thrash)."""
    assembled, chapters, uid, desired_block = _build()
    embedded = dict(desired_block)
    embedded["MUSICBRAINZ_ARTISTIDS"] = "mbid-1|mbid-2"
    with patch(
        "festival_organizer.mkv_tags.extract_chapter_tags_by_uid",
        return_value={uid: embedded},
    ):
        assert not chapter_tags_need_refresh(
            Path("x.mkv"), assembled, chapters, mashup_metadata=True
        )


def test_no_refresh_when_nothing_to_compare():
    assert not chapter_tags_need_refresh(Path("x.mkv"), None, [], mashup_metadata=True)
