"""Tests for the self-heal logic in cli_handler._fetch_and_embed.

When chapters_are_identical returns True:
- if TTV=30 per-chapter tags are missing, route through embed_chapters to
  populate them on next identify run (no flag needed).
- if TTV=30 tags are present and TTV=70 tags match, return "up_to_date".
- if regenerate=True, force re-tag via embed_chapters regardless.

These cover the path that currently fails for pre-0.9.9 legacy files.
"""
from unittest.mock import MagicMock, patch

from festival_organizer.tracklists.api import Track, TracklistExport
from festival_organizer.tracklists.cli_handler import _fetch_and_embed


def _make_export() -> TracklistExport:
    """Minimal export with enough chapters to pass the >= 2 gate."""
    return TracklistExport(
        lines=["[00:00] Opener", "[01:00] Second", "[02:00] Third"],
        url="https://www.1001tracklists.com/tracklist/abc/",
        title="Test Set",
        genres=["House"],
        dj_artists=[("testdj", "Test DJ")],
        dj_artwork_url="",
        stage_text="",
        sources_by_type={},
        country="",
        source_type="",
        tracks=[
            Track(start_ms=0, raw_text="Opener", artist_slugs=["testdj"], genres=["House"]),
            Track(start_ms=60000, raw_text="Second", artist_slugs=["guest"], genres=["Techno"]),
            Track(start_ms=120000, raw_text="Third", artist_slugs=["testdj"], genres=["House"]),
        ],
    )


def _make_session() -> MagicMock:
    sess = MagicMock()
    sess.export_tracklist.return_value = _make_export()
    sess._dj_cache = MagicMock()
    sess._dj_cache.canonical_name.side_effect = lambda slug, fallback=None: fallback or slug
    return sess


def _make_config() -> MagicMock:
    cfg = MagicMock()
    cfg.resolve_artist.side_effect = lambda name: name
    return cfg


def _patch_identify_internals(**overrides):
    """Returns a dict of patch contexts keyed by target name."""
    defaults = {
        "extract_existing_chapters": MagicMock(return_value=[object(), object(), object()]),
        "chapters_are_identical": MagicMock(return_value=True),
        "extract_stored_tracklist_info": MagicMock(return_value={
            "url": "https://www.1001tracklists.com/tracklist/abc/",
            "title": "Test Set",
            "id": "abc",
            "date": "",
            "genres": "House",
            "dj_artwork": "",
            "stage": "",
            "venue": "",
            "festival": "",
            "conference": "",
            "radio": "",
            "artists": "Test DJ",
            "country": "",
            "source_type": "",
        }),
        "has_chapter_tags": MagicMock(return_value=True),
        "embed_chapters": MagicMock(return_value=True),
        "trim_chapters_to_duration": lambda chapters, duration: chapters,
    }
    defaults.update(overrides)
    return defaults


def test_up_to_date_when_ttv30_present_and_tags_match(tmp_path):
    """Classic happy path: file already has chapter tags + TTV=70 matches."""
    mocks = _patch_identify_internals(has_chapter_tags=MagicMock(return_value=True))
    fake = tmp_path / "x.mkv"
    fake.write_bytes(b"")
    with patch.multiple(
        "festival_organizer.tracklists.cli_handler",
        extract_existing_chapters=mocks["extract_existing_chapters"],
        chapters_are_identical=mocks["chapters_are_identical"],
        extract_stored_tracklist_info=mocks["extract_stored_tracklist_info"],
        has_chapter_tags=mocks["has_chapter_tags"],
        embed_chapters=mocks["embed_chapters"],
        trim_chapters_to_duration=mocks["trim_chapters_to_duration"],
    ):
        status = _fetch_and_embed(
            _make_session(), "https://x", fake, 126, _make_config(),
            preview=False, quiet=True, language="eng",
            tracklist_id="abc", tracklist_date="",
            duration_seconds=7560, regenerate=False,
        )
    assert status == "up_to_date"
    mocks["embed_chapters"].assert_not_called()


def test_self_heal_triggers_when_ttv30_missing(tmp_path):
    """Legacy file: chapters match, TTV=30 absent → must re-run embed_chapters."""
    mocks = _patch_identify_internals(has_chapter_tags=MagicMock(return_value=False))
    fake = tmp_path / "x.mkv"
    fake.write_bytes(b"")
    with patch.multiple(
        "festival_organizer.tracklists.cli_handler",
        extract_existing_chapters=mocks["extract_existing_chapters"],
        chapters_are_identical=mocks["chapters_are_identical"],
        extract_stored_tracklist_info=mocks["extract_stored_tracklist_info"],
        has_chapter_tags=mocks["has_chapter_tags"],
        embed_chapters=mocks["embed_chapters"],
        trim_chapters_to_duration=mocks["trim_chapters_to_duration"],
    ):
        status = _fetch_and_embed(
            _make_session(), "https://x", fake, 126, _make_config(),
            preview=False, quiet=True, language="eng",
            tracklist_id="abc", tracklist_date="",
            duration_seconds=7560, regenerate=False,
        )
    assert status == "updated"
    mocks["embed_chapters"].assert_called_once()


def test_regenerate_forces_retag_even_when_up_to_date(tmp_path):
    """--regenerate/--fresh must force re-tag even if nothing visibly differs."""
    mocks = _patch_identify_internals(has_chapter_tags=MagicMock(return_value=True))
    fake = tmp_path / "x.mkv"
    fake.write_bytes(b"")
    with patch.multiple(
        "festival_organizer.tracklists.cli_handler",
        extract_existing_chapters=mocks["extract_existing_chapters"],
        chapters_are_identical=mocks["chapters_are_identical"],
        extract_stored_tracklist_info=mocks["extract_stored_tracklist_info"],
        has_chapter_tags=mocks["has_chapter_tags"],
        embed_chapters=mocks["embed_chapters"],
        trim_chapters_to_duration=mocks["trim_chapters_to_duration"],
    ):
        status = _fetch_and_embed(
            _make_session(), "https://x", fake, 126, _make_config(),
            preview=False, quiet=True, language="eng",
            tracklist_id="abc", tracklist_date="",
            duration_seconds=7560, regenerate=True,
        )
    assert status == "updated"
    mocks["embed_chapters"].assert_called_once()


def test_ttv70_tag_diff_also_routes_through_embed_chapters(tmp_path):
    """When a TTV=70 tag differs, embed_chapters should handle it (not a
    partial write that leaves TTV=30 stale)."""
    stored = {
        "url": "https://www.1001tracklists.com/tracklist/abc/",
        "title": "Old Title",  # differs from export
        "id": "abc",
        "date": "",
        "genres": "House",
        "dj_artwork": "",
        "stage": "",
        "venue": "",
        "festival": "",
        "conference": "",
        "radio": "",
        "artists": "Test DJ",
        "country": "",
        "source_type": "",
    }
    mocks = _patch_identify_internals(
        has_chapter_tags=MagicMock(return_value=True),
        extract_stored_tracklist_info=MagicMock(return_value=stored),
    )
    fake = tmp_path / "x.mkv"
    fake.write_bytes(b"")
    with patch.multiple(
        "festival_organizer.tracklists.cli_handler",
        extract_existing_chapters=mocks["extract_existing_chapters"],
        chapters_are_identical=mocks["chapters_are_identical"],
        extract_stored_tracklist_info=mocks["extract_stored_tracklist_info"],
        has_chapter_tags=mocks["has_chapter_tags"],
        embed_chapters=mocks["embed_chapters"],
        trim_chapters_to_duration=mocks["trim_chapters_to_duration"],
    ):
        status = _fetch_and_embed(
            _make_session(), "https://x", fake, 126, _make_config(),
            preview=False, quiet=True, language="eng",
            tracklist_id="abc", tracklist_date="",
            duration_seconds=7560, regenerate=False,
        )
    assert status == "updated"
    mocks["embed_chapters"].assert_called_once()
