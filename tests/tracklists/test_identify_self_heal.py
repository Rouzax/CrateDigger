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
        "has_album_artist_display_tags": MagicMock(return_value=True),
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
        has_album_artist_display_tags=mocks["has_album_artist_display_tags"],
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
        has_album_artist_display_tags=mocks["has_album_artist_display_tags"],
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


def test_self_heal_triggers_when_album_artist_display_missing(tmp_path):
    """Pre-0.12.4 file: chapters + TTV=30 + 1001TL_ARTISTS all match stored,
    but _DISPLAY/_SLUGS were never written. Must re-embed via the stored URL,
    not print 'Up to date' and not force a 1001TL re-search."""
    mocks = _patch_identify_internals(
        has_chapter_tags=MagicMock(return_value=True),
        has_album_artist_display_tags=MagicMock(return_value=False),
    )
    fake = tmp_path / "x.mkv"
    fake.write_bytes(b"")
    with patch.multiple(
        "festival_organizer.tracklists.cli_handler",
        extract_existing_chapters=mocks["extract_existing_chapters"],
        chapters_are_identical=mocks["chapters_are_identical"],
        extract_stored_tracklist_info=mocks["extract_stored_tracklist_info"],
        has_chapter_tags=mocks["has_chapter_tags"],
        has_album_artist_display_tags=mocks["has_album_artist_display_tags"],
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


def test_album_artist_check_skipped_when_no_dj_artists(tmp_path):
    """If the export carries no dj_artists, the album tags aren't applicable,
    so their absence must not force a re-embed."""
    session = _make_session()
    export = session.export_tracklist.return_value
    export.dj_artists = []  # no-op self-heal
    mocks = _patch_identify_internals(
        has_chapter_tags=MagicMock(return_value=True),
        has_album_artist_display_tags=MagicMock(return_value=False),
    )
    fake = tmp_path / "x.mkv"
    fake.write_bytes(b"")
    with patch.multiple(
        "festival_organizer.tracklists.cli_handler",
        extract_existing_chapters=mocks["extract_existing_chapters"],
        chapters_are_identical=mocks["chapters_are_identical"],
        extract_stored_tracklist_info=mocks["extract_stored_tracklist_info"],
        has_chapter_tags=mocks["has_chapter_tags"],
        has_album_artist_display_tags=mocks["has_album_artist_display_tags"],
        embed_chapters=mocks["embed_chapters"],
        trim_chapters_to_duration=mocks["trim_chapters_to_duration"],
    ):
        status = _fetch_and_embed(
            session, "https://x", fake, 126, _make_config(),
            preview=False, quiet=True, language="eng",
            tracklist_id="abc", tracklist_date="",
            duration_seconds=7560, regenerate=False,
        )
    assert status == "up_to_date"
    mocks["embed_chapters"].assert_not_called()


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
        has_album_artist_display_tags=mocks["has_album_artist_display_tags"],
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
        has_album_artist_display_tags=mocks["has_album_artist_display_tags"],
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


def test_set_genres_capped_via_config_genre_top_n(tmp_path):
    """_fetch_and_embed honours config.tracklists_settings.genre_top_n, capping
    the set-level CRATEDIGGER_1001TL_GENRES to top-N per-track genres."""
    from unittest.mock import MagicMock, patch
    from festival_organizer.tracklists.api import Track, TracklistExport
    from festival_organizer.tracklists.cli_handler import _fetch_and_embed

    # Tracks produce 7 distinct genres with varying frequency.
    tracks = [
        Track(start_ms=i * 60000, raw_text=f"Artist{i} - T{i}",
              artist_slugs=[f"a{i}"], genres=[g])
        for i, g in enumerate([
            "House", "House", "Tech House", "Tech House", "Trance",
            "Mainstage", "Techno", "Progressive", "Hard Dance",
        ])
    ]
    export = TracklistExport(
        lines=[f"[{i:02d}:00] t{i}" for i in range(len(tracks))],
        url="https://www.1001tracklists.com/tracklist/abc/",
        title="Test",
        genres=["House", "Tech House", "Trance", "Mainstage", "Techno",
                "Progressive", "Hard Dance"],  # 7 genres flat
        dj_artists=[("test", "Test")],
        tracks=tracks,
    )

    session = MagicMock()
    session.export_tracklist.return_value = export
    session._dj_cache = MagicMock()

    config = MagicMock()
    config.tracklists_settings = {"genre_top_n": 3}  # cap at 3
    config.resolve_artist = lambda n: n

    captured: dict = {}

    def fake_embed(filepath, chapters, **kwargs):
        captured["genres"] = kwargs.get("genres")
        return True

    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")

    with patch("festival_organizer.tracklists.cli_handler.parse_tracklist_lines",
               return_value=[MagicMock(timestamp=f"00:{i:02d}:00.000", title=f"t{i}")
                             for i in range(len(tracks))]), \
         patch("festival_organizer.tracklists.cli_handler.trim_chapters_to_duration",
               side_effect=lambda chs, dur: chs), \
         patch("festival_organizer.tracklists.cli_handler.extract_existing_chapters",
               return_value=None), \
         patch("festival_organizer.tracklists.cli_handler.chapters_are_identical",
               return_value=False), \
         patch("festival_organizer.tracklists.cli_handler.embed_chapters",
               side_effect=fake_embed), \
         patch("festival_organizer.tracklists.cli_handler.extract_tracklist_id",
               return_value="abc"):
        _fetch_and_embed(session, "https://x", fake_mkv, 0, config,
                         preview=False, quiet=True, language="eng",
                         tracklist_id="abc", tracklist_date=None,
                         duration_seconds=None, regenerate=False)

    # Top 3 by frequency: House (2), Tech House (2), Trance (1)
    # (ties broken by first-appearance order)
    assert captured["genres"] == ["House", "Tech House", "Trance"]


def test_set_genres_uncapped_when_config_zero(tmp_path):
    """genre_top_n=0 disables the cap; full export.genres flows through."""
    from unittest.mock import MagicMock, patch
    from festival_organizer.tracklists.api import Track, TracklistExport
    from festival_organizer.tracklists.cli_handler import _fetch_and_embed

    tracks = [Track(start_ms=0, raw_text="A - t", artist_slugs=["a"], genres=["X"])]
    export = TracklistExport(
        lines=["[00:00] t"], url="https://x", title="T",
        genres=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],  # 10 genres
        dj_artists=[("test", "Test")], tracks=tracks,
    )
    session = MagicMock()
    session.export_tracklist.return_value = export
    session._dj_cache = MagicMock()
    config = MagicMock()
    config.tracklists_settings = {"genre_top_n": 0}
    config.resolve_artist = lambda n: n

    captured: dict = {}
    def fake_embed(filepath, chapters, **kwargs):
        captured["genres"] = kwargs.get("genres")
        return True

    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")
    with patch("festival_organizer.tracklists.cli_handler.parse_tracklist_lines",
               return_value=[MagicMock(timestamp="00:00:00.000", title="t")]), \
         patch("festival_organizer.tracklists.cli_handler.trim_chapters_to_duration",
               side_effect=lambda chs, dur: chs), \
         patch("festival_organizer.tracklists.cli_handler.extract_existing_chapters",
               return_value=None), \
         patch("festival_organizer.tracklists.cli_handler.chapters_are_identical",
               return_value=False), \
         patch("festival_organizer.tracklists.cli_handler.embed_chapters",
               side_effect=fake_embed), \
         patch("festival_organizer.tracklists.cli_handler.extract_tracklist_id",
               return_value="abc"):
        _fetch_and_embed(session, "https://x", fake_mkv, 0, config,
                         preview=False, quiet=True, language="eng",
                         tracklist_id="abc", tracklist_date=None,
                         duration_seconds=None, regenerate=False)

    # Cap disabled — we keep whatever the flat scrape produced.
    assert captured["genres"] == export.genres
