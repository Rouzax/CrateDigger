from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

from PIL import Image

from festival_organizer.models import MediaFile
from festival_organizer.operations import (
    NfoOperation,
    ArtOperation,
    PosterOperation,
    CoverEmbedOperation,
    OrganizeOperation,
    AlbumPosterOperation,
    FanartOperation,
    _resolve_poster_fields,
)
from festival_organizer.config import load_config, Config, DEFAULT_CONFIG


def _win_normcase(s: str) -> str:
    return s.replace("/", "\\").lower()


def _make_mf(**kwargs: Any) -> MediaFile:
    defaults: dict[str, Any] = dict(
        source_path=Path("test.mkv"),
        artist="Test",
        festival="TML",
        year="2024",
        content_type="festival_set",
    )
    defaults.update(kwargs)
    return MediaFile(**defaults)


def _stub_generate_album_poster(**kwargs):
    """Stand-in for generate_album_poster in mocked tests.

    Honors the real contract (generate_album_poster always writes output_path) so
    the folder-stamp injection that runs after it has a file to stamp.
    """
    out = Path(kwargs["output_path"])
    out.write_bytes(b"\xff\xd8\xff\xd9")
    return out


def test_nfo_op_needed_when_missing(tmp_path):
    """NFO operation needed when .nfo file doesn't exist."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = NfoOperation(load_config())
    assert op.is_needed(video, _make_mf()) is True


def test_nfo_op_not_needed_when_exists(tmp_path):
    """NFO operation not needed when .nfo content matches current MediaFile."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()
    config = load_config()
    from festival_organizer.nfo import generate_nfo

    generate_nfo(mf, video, config)
    op = NfoOperation(config)
    assert op.is_needed(video, mf) is False


def test_nfo_op_needed_when_forced(tmp_path):
    """NFO operation needed when forced, even if .nfo exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()
    config = load_config()
    from festival_organizer.nfo import generate_nfo

    generate_nfo(mf, video, config)
    op = NfoOperation(config, force=True)
    assert op.is_needed(video, mf) is True


def test_nfo_op_needed_when_artist_changed(tmp_path):
    """NFO regenerated when artist list changes."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    config = load_config()
    from festival_organizer.nfo import generate_nfo

    generate_nfo(_make_mf(artists=["Artist A"]), video, config)
    op = NfoOperation(config)
    assert op.is_needed(video, _make_mf(artists=["Artist B"])) is True


def test_nfo_op_needed_when_genre_added(tmp_path):
    """NFO regenerated when genres change."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    config = load_config()
    from festival_organizer.nfo import generate_nfo

    generate_nfo(_make_mf(), video, config)
    op = NfoOperation(config)
    assert op.is_needed(video, _make_mf(genres=["Techno"])) is True


def test_nfo_op_needed_when_stage_changed(tmp_path):
    """NFO regenerated when stage changes."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    config = load_config()
    from festival_organizer.nfo import generate_nfo

    generate_nfo(_make_mf(stage="Mainstage"), video, config)
    op = NfoOperation(config)
    assert op.is_needed(video, _make_mf(stage="Freedom")) is True


def test_nfo_op_skipped_when_only_dateadded_differs(tmp_path):
    """NFO not regenerated when only dateadded timestamp differs."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()
    config = load_config()
    from festival_organizer.nfo import generate_nfo

    generate_nfo(mf, video, config, dateadded="2020-01-01 00:00:00")
    op = NfoOperation(config)
    assert op.is_needed(video, mf) is False


def test_nfo_op_needed_when_dj_cache_adds_group_member(tmp_path):
    """NFO regenerated when DJ cache introduces new group member tags."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    config = load_config()
    mf = _make_mf(artists=["Gaia"])
    from festival_organizer.nfo import generate_nfo

    generate_nfo(mf, video, config)

    dj_cache = MagicMock()
    dj_cache.derive_group_members.return_value = {
        "Gaia": ["Armin van Buuren", "Benno de Goeij"]
    }
    op = NfoOperation(config, dj_cache=dj_cache)
    assert op.is_needed(video, mf) is True


def test_nfo_op_preserves_dateadded_on_regen(tmp_path):
    """Regenerated NFO keeps the original dateadded timestamp."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    config = load_config()
    original_ts = "2023-06-15 14:30:00"
    from festival_organizer.nfo import generate_nfo
    import xml.etree.ElementTree as ET

    generate_nfo(_make_mf(stage="Mainstage"), video, config, dateadded=original_ts)
    op = NfoOperation(config)
    op.execute(video, _make_mf(stage="Freedom"))
    root = ET.fromstring((tmp_path / "test.nfo").read_text(encoding="utf-8"))
    assert root.find("dateadded").text == original_ts


def test_nfo_op_needed_when_nfo_is_corrupt(tmp_path):
    """Corrupt NFO file triggers regeneration."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test.nfo").write_text("<<<not xml>>>")
    op = NfoOperation(load_config())
    assert op.is_needed(video, _make_mf()) is True


def test_art_op_needed_when_missing(tmp_path):
    """Art operation needed when thumb doesn't exist."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = ArtOperation()
    assert op.is_needed(video, _make_mf()) is True


def test_art_op_not_needed_when_exists(tmp_path):
    """Art operation not needed when thumb exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    op = ArtOperation()
    assert op.is_needed(video, _make_mf()) is False


def test_poster_op_needed_when_thumb_exists_but_poster_missing(tmp_path):
    """Poster operation needed when thumb exists but poster doesn't."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    op = PosterOperation(load_config())
    assert op.is_needed(video, _make_mf()) is True


def test_poster_op_not_needed_when_stamp_matches(tmp_path):
    """Skip when the sidecar stamp equals the current resolved inputs."""
    from festival_organizer.poster import build_cover_stamp, inject_poster_stamp

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    poster = tmp_path / "test-poster.jpg"
    Image.new("RGB", (1000, 1500), (10, 10, 10)).save(str(poster), "JPEG")
    cfg = load_config()
    op = PosterOperation(cfg)
    mf = _make_mf()
    inject_poster_stamp(
        poster,
        build_cover_stamp(
            **_resolve_poster_fields(mf, cfg), artists_1001tl=mf.artists_1001tl
        ),
    )
    assert op.is_needed(video, mf) is False


def test_poster_op_needed_when_stamp_absent(tmp_path):
    """Poster exists but carries no stamp (older CrateDigger) -> re-render."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    poster = tmp_path / "test-poster.jpg"
    Image.new("RGB", (1000, 1500), (10, 10, 10)).save(str(poster), "JPEG")
    assert PosterOperation(load_config()).is_needed(video, _make_mf()) is True


def test_poster_op_non_matroska_needed_when_unstamped(tmp_path):
    """Non-Matroska poster without a stamp now regenerates (to add the stamp)."""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    poster = tmp_path / "test-poster.jpg"
    Image.new("RGB", (1000, 1500), (10, 10, 10)).save(str(poster), "JPEG")  # no stamp
    assert PosterOperation(load_config()).is_needed(video, _make_mf()) is True


def test_poster_op_non_matroska_not_needed_when_stamp_matches(tmp_path):
    """Non-Matroska poster carrying a matching stamp is up to date."""
    from festival_organizer.poster import build_cover_stamp, inject_poster_stamp

    video = tmp_path / "test.mp4"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    poster = tmp_path / "test-poster.jpg"
    Image.new("RGB", (1000, 1500), (10, 10, 10)).save(str(poster), "JPEG")
    cfg = load_config()
    mf = _make_mf()
    inject_poster_stamp(
        poster,
        build_cover_stamp(
            **_resolve_poster_fields(mf, cfg), artists_1001tl=mf.artists_1001tl
        ),
    )
    assert PosterOperation(cfg).is_needed(video, mf) is False


def test_poster_op_execute_stamps_non_matroska(tmp_path):
    """execute() stamps a non-Matroska sidecar, so a second run is a no-op."""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"")
    Image.new("RGB", (1280, 720), (50, 60, 90)).save(str(tmp_path / "test-thumb.jpg"))
    cfg = load_config()
    op = PosterOperation(cfg)
    mf = _make_mf()
    assert op.execute(video, mf).status == "done"
    assert op.is_needed(video, mf) is False


def test_poster_op_needed_when_field_changes(tmp_path):
    from festival_organizer.poster import build_cover_stamp, inject_poster_stamp

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    poster = tmp_path / "test-poster.jpg"
    Image.new("RGB", (1000, 1500), (10, 10, 10)).save(str(poster), "JPEG")
    cfg = load_config()
    old = _resolve_poster_fields(_make_mf(artist="Old"), cfg)
    inject_poster_stamp(poster, build_cover_stamp(**old, artists_1001tl=[]))
    assert PosterOperation(cfg).is_needed(video, _make_mf(artist="New")) is True


def test_poster_op_not_needed_when_no_thumb(tmp_path):
    """Poster operation not needed when no thumb available."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = PosterOperation(load_config())
    assert op.is_needed(video, _make_mf()) is False


def _run_poster_and_capture_festival(tmp_path, mf):
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    with patch("festival_organizer.poster.generate_set_poster") as gen:
        PosterOperation(load_config()).execute(video, mf)
    return gen.call_args.kwargs["festival"]


def _run_poster_and_capture_kwargs(tmp_path, mf):
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    with patch("festival_organizer.poster.generate_set_poster") as gen:
        PosterOperation(load_config()).execute(video, mf)
    return gen.call_args.kwargs


def test_resolve_poster_fields_uses_display_artist_and_edition_slot():
    cfg = load_config()
    mf = _make_mf(
        artist="afrojack",
        display_artist="AFROJACK",
        place="UMF",
        edition="",
        stage="Mainstage",
        date="2026-03-29",
        year="2026",
    )
    f = _resolve_poster_fields(mf, cfg)
    assert f["artist"] == "AFROJACK"
    assert f["stage"] == "Mainstage"
    assert f["date"] == "2026-03-29"
    assert f["year"] == "2026"
    assert "venue" in f and "festival" in f


def test_resolve_poster_fields_drops_venue_when_place_is_venue():
    cfg = load_config()
    mf = _make_mf(place="Some Club", place_kind="venue", venue="Some Club")
    assert _resolve_poster_fields(mf, cfg)["venue"] == ""


def test_poster_festival_slot_uses_place_for_festival(tmp_path):
    """Festival set: mf.place fills the headline slot."""
    mf = _make_mf(
        festival="Tomorrowland",
        venue="Some Venue",
        location="Some Location",
        title="Artist @ Stage, TML",
        place="Tomorrowland",
        place_kind="festival",
    )
    assert _run_poster_and_capture_festival(tmp_path, mf) == "Tomorrowland"


def test_poster_festival_slot_uses_place_for_venue(tmp_path):
    """Concert at a linked venue: mf.place holds the venue and fills the slot."""
    mf = _make_mf(
        festival="",
        venue="Alexandra Palace London",
        location="ignored freeform",
        title="Fred again.. @ USB002",
        place="Alexandra Palace London",
        place_kind="venue",
    )
    assert _run_poster_and_capture_festival(tmp_path, mf) == "Alexandra Palace London"


def test_poster_festival_slot_uses_place_for_location(tmp_path):
    """Freeform location: mf.place carries the canonical location."""
    mf = _make_mf(
        festival="",
        venue="",
        location="Some Unlinked Venue",
        title="Artist @ Stage",
        place="Some Unlinked Venue",
        place_kind="location",
    )
    assert _run_poster_and_capture_festival(tmp_path, mf) == "Some Unlinked Venue"


def test_poster_venue_subline_suppressed_when_place_kind_is_venue(tmp_path):
    """When place_kind=venue the venue is already in the slot; subline is blank."""
    mf = _make_mf(
        festival="",
        venue="Red Rocks Amphitheatre",
        stage="",
        title="Martin Garrix @ Red Rocks",
        place="Red Rocks Amphitheatre",
        place_kind="venue",
    )
    kwargs = _run_poster_and_capture_kwargs(tmp_path, mf)
    assert kwargs["festival"] == "Red Rocks Amphitheatre"
    assert kwargs["venue"] == ""


def test_poster_venue_subline_suppressed_when_place_kind_is_location(tmp_path):
    """place_kind=location also suppresses the venue subline (same slot)."""
    mf = _make_mf(
        festival="",
        venue="Some Bar",
        location="Some Bar, Berlin",
        stage="",
        title="irrelevant",
        place="Some Bar, Berlin",
        place_kind="location",
    )
    kwargs = _run_poster_and_capture_kwargs(tmp_path, mf)
    assert kwargs["festival"] == "Some Bar, Berlin"
    assert kwargs["venue"] == ""


def test_poster_venue_subline_rendered_when_place_kind_is_festival(tmp_path):
    """Real festival in the slot: venue still renders as a subline."""
    mf = _make_mf(
        festival="Amsterdam Music Festival",
        venue="Johan Cruijff ArenA Amsterdam",
        stage="Mainstage",
        title="irrelevant",
        place="Amsterdam Music Festival",
        place_kind="festival",
    )
    kwargs = _run_poster_and_capture_kwargs(tmp_path, mf)
    assert kwargs["festival"] == "Amsterdam Music Festival"
    assert kwargs["venue"] == "Johan Cruijff ArenA Amsterdam"


def test_poster_festival_slot_uses_edition_display(tmp_path):
    """When mf.edition matches a known edition, the slot uses 'Place Edition'."""
    mf = _make_mf(
        festival="Tomorrowland",
        edition="Winter",
        place="Tomorrowland",
        place_kind="festival",
        title="irrelevant",
    )
    cfg = load_config()
    cfg._data["place_config"] = {"Tomorrowland": {"editions": {"Winter": {}}}}
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    with patch("festival_organizer.poster.generate_set_poster") as gen:
        PosterOperation(cfg).execute(video, mf)
    assert gen.call_args.kwargs["festival"] == "Tomorrowland Winter"


def test_organize_op_needed_when_not_at_target(tmp_path):
    """Organize operation needed when file is not at target location."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    target = tmp_path / "Artist" / "test.mkv"
    op = OrganizeOperation(target=target)
    assert op.is_needed(video, _make_mf()) is True


def test_organize_op_not_needed_when_at_target(tmp_path):
    """Organize operation not needed when file is already at target."""
    target = tmp_path / "Artist" / "test.mkv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")
    op = OrganizeOperation(target=target)
    assert op.is_needed(target, _make_mf()) is False


def test_organize_op_needed_for_case_only_rename(tmp_path):
    """Canonical-casing rename (e.g. Alok -> ALOK) must still run.

    On case-insensitive filesystems (NTFS, APFS default) Path.resolve()
    normalises both sides to the same string; is_needed must not treat that
    as "already at target".
    """
    source = tmp_path / "2025 - Alok - EDC.mkv"
    source.write_bytes(b"")
    target = tmp_path / "2025 - ALOK - EDC.mkv"
    op = OrganizeOperation(target=target)
    assert op.is_needed(source, _make_mf()) is True


def test_organize_op_not_needed_for_prefix_case():
    """e:\\ vs E:\\ prefix difference is not a real rename."""
    with (
        patch("festival_organizer.paths.os.sep", "\\"),
        patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase),
    ):
        source = Path("e:\\Data\\AMF\\2024 - Marlon Hoffstadt - AMF.mkv")
        target = Path("E:\\Data\\AMF\\2024 - Marlon Hoffstadt - AMF.mkv")
        root = Path("E:\\Data")
        op = OrganizeOperation(target=target, output_root=root)
        assert op.is_needed(source, _make_mf()) is False


def test_organize_op_case_only_rename_executes_without_collision_suffix(tmp_path):
    """Case-only rename lands on the exact target, not on a (1) variant.

    resolve_collision must recognise that the 'colliding' target is the
    source file itself on a case-insensitive fs and allow the rename.
    Simulated here by monkey-patching Path.samefile so the scenario works
    on Linux too.
    """
    source = tmp_path / "alok.mkv"
    source.write_bytes(b"payload")
    target = tmp_path / "ALOK.mkv"
    # On a case-sensitive fs these are distinct files. Create the "collision"
    # and teach samefile to treat it as identical to the source, matching
    # case-insensitive fs behaviour.
    target.write_bytes(b"payload")

    real_samefile = Path.samefile

    def fake_samefile(self, other):
        a = str(self).lower()
        b = str(other).lower()
        if a == b:
            return True
        return real_samefile(self, other)

    with patch.object(Path, "samefile", fake_samefile):
        op = OrganizeOperation(target=target, action="rename")
        assert op.is_needed(source, _make_mf()) is True
        result = op.execute(source, _make_mf())

    assert result.status == "done"
    assert op.target == target
    # No (1) sibling was produced.
    assert not (tmp_path / "ALOK (1).mkv").exists()


def test_album_poster_needed_when_missing(tmp_path):
    """Album poster needed when folder.jpg doesn't exist."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = AlbumPosterOperation(config=load_config())
    assert op.is_needed(video, _make_mf()) is True


def test_album_poster_not_needed_when_stamp_matches(tmp_path):
    """Folder poster is up to date when folder.jpg carries the matching stamp."""
    from festival_organizer.poster import inject_poster_stamp

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    folder_jpg = tmp_path / "folder.jpg"
    folder_jpg.write_bytes(b"\xff\xd8\xff\xd9")
    op = AlbumPosterOperation(config=load_config())
    mf = _make_mf()
    inject_poster_stamp(folder_jpg, op._expected_folder_stamp(mf, tmp_path))
    assert op.is_needed(video, mf) is False


def test_album_poster_needed_when_unstamped(tmp_path):
    """Existing folder.jpg with no stamp (pre-stamp libraries) regenerates once."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "folder.jpg").write_bytes(b"\xff\xd8\xff\xd9")  # valid JPEG, no stamp
    op = AlbumPosterOperation(config=load_config())
    assert op.is_needed(video, _make_mf()) is True


def test_album_poster_needed_when_stamp_mismatch(tmp_path):
    """Folder poster regenerates when the rendered identity changed (stamp mismatch)."""
    from festival_organizer.poster import inject_poster_stamp

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    folder_jpg = tmp_path / "folder.jpg"
    folder_jpg.write_bytes(b"\xff\xd8\xff\xd9")
    op = AlbumPosterOperation(config=load_config())
    inject_poster_stamp(
        folder_jpg, op._expected_folder_stamp(_make_mf(artist="Old Name"), tmp_path)
    )
    assert op.is_needed(video, _make_mf(artist="New Name")) is True


def test_album_poster_regenerates_on_version_bump(tmp_path, monkeypatch):
    """Bumping FOLDER_POSTER_VERSION invalidates existing folder-poster stamps."""
    from festival_organizer import poster as poster_mod
    from festival_organizer.poster import inject_poster_stamp

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    folder_jpg = tmp_path / "folder.jpg"
    folder_jpg.write_bytes(b"\xff\xd8\xff\xd9")
    op = AlbumPosterOperation(config=load_config())
    mf = _make_mf()
    inject_poster_stamp(folder_jpg, op._expected_folder_stamp(mf, tmp_path))
    assert op.is_needed(video, mf) is False
    monkeypatch.setattr(
        poster_mod, "FOLDER_POSTER_VERSION", poster_mod.FOLDER_POSTER_VERSION + 1
    )
    assert op.is_needed(video, mf) is True


def test_album_poster_execute_parses_filenames(tmp_path):
    """Album poster execute() correctly passes config to parse_filename."""
    video = tmp_path / "2024 - Tomorrowland - Bicep.mkv"
    video.write_bytes(b"")
    (tmp_path / "2024 - Tomorrowland - Bicep-thumb.jpg").write_bytes(b"\xff\xd8")
    op = AlbumPosterOperation(config=load_config())
    mf = _make_mf(festival="Tomorrowland", artist="Bicep", year="2024")
    with patch(
        "festival_organizer.poster.generate_album_poster",
        side_effect=_stub_generate_album_poster,
    ):
        result = op.execute(video, mf)
    assert result.status == "done"


def test_album_poster_fanart_multi_artist_returns_none(tmp_path):
    """Fanart background skipped for multi-artist folders."""
    (tmp_path / "2024 - TML - Artist1.mkv").write_bytes(b"")
    (tmp_path / "2024 - TML - Artist2.mkv").write_bytes(b"")
    lib = tmp_path / "lib"
    lib.mkdir()
    op = AlbumPosterOperation(config=load_config(), library_root=lib)
    result = op._find_fanart_background(tmp_path, "Artist1")
    assert result is None


def test_album_poster_fanart_single_artist_finds_image(tmp_path):
    """Fanart background returned for single-artist folder."""
    (tmp_path / "2024 - TML - Bicep.mkv").write_bytes(b"")
    (tmp_path / "2024 - TML - Bicep WE2.mkv").write_bytes(b"")
    fanart = tmp_path / "artists" / "bicep" / "fanart.jpg"
    fanart.parent.mkdir(parents=True)
    fanart.write_bytes(b"\xff\xd8")
    op = AlbumPosterOperation(config=load_config(), library_root=tmp_path)
    with patch("festival_organizer.operations.paths.cache_dir", return_value=tmp_path):
        result = op._find_fanart_background(tmp_path, "Bicep")
    assert result == fanart


def test_album_poster_fanart_single_artist_dash_we(tmp_path):
    """Dash-separated WE suffix doesn't split artist detection."""
    (tmp_path / "2024 - TML - Bicep - WE1.mkv").write_bytes(b"")
    (tmp_path / "2024 - TML - Bicep - WE2.mkv").write_bytes(b"")
    fanart = tmp_path / "artists" / "bicep" / "fanart.jpg"
    fanart.parent.mkdir(parents=True)
    fanart.write_bytes(b"\xff\xd8")
    op = AlbumPosterOperation(config=load_config(), library_root=tmp_path)
    with patch("festival_organizer.operations.paths.cache_dir", return_value=tmp_path):
        result = op._find_fanart_background(tmp_path, "Bicep")
    assert result == fanart


def test_album_poster_dedup_same_folder(tmp_path):
    """Album poster skips second file in same folder after first completes."""
    video1 = tmp_path / "2024 - TML - Bicep - WE1.mkv"
    video2 = tmp_path / "2024 - TML - Bicep - WE2.mkv"
    video1.write_bytes(b"")
    video2.write_bytes(b"")
    op = AlbumPosterOperation(config=load_config(), force=True)
    mf = _make_mf(festival="TML", artist="Bicep", year="2024")
    # First file: needed
    assert op.is_needed(video1, mf) is True
    # Simulate execute completing
    with patch(
        "festival_organizer.poster.generate_album_poster",
        side_effect=_stub_generate_album_poster,
    ):
        op.execute(video1, mf)
    # Second file in same folder: not needed
    assert op.is_needed(video2, mf) is False


def test_album_poster_dedup_different_folders(tmp_path):
    """Album poster processes both files when in different folders."""
    folder1 = tmp_path / "Artist1"
    folder2 = tmp_path / "Artist2"
    folder1.mkdir()
    folder2.mkdir()
    video1 = folder1 / "2024 - TML - Artist1.mkv"
    video2 = folder2 / "2024 - TML - Artist2.mkv"
    video1.write_bytes(b"")
    video2.write_bytes(b"")
    op = AlbumPosterOperation(config=load_config(), force=True)
    mf1 = _make_mf(artist="Artist1")
    mf2 = _make_mf(artist="Artist2")
    with patch(
        "festival_organizer.poster.generate_album_poster",
        side_effect=_stub_generate_album_poster,
    ):
        op.execute(video1, mf1)
    # Different folder: still needed
    assert op.is_needed(video2, mf2) is True


def test_album_poster_type_from_artist_flat_layout():
    """artist_flat layout: {artist} -> artist poster type."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "artist_flat"
    op = AlbumPosterOperation(config=config)
    mf = _make_mf(place="Test", place_kind="festival")
    assert op._get_folder_poster_type(mf) == "artist"


def test_album_poster_type_from_place_flat_layout():
    """place_flat layout: {festival} -> festival poster type."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_flat"
    op = AlbumPosterOperation(config=config)
    mf = _make_mf(place="Tomorrowland", place_kind="festival")
    assert op._get_folder_poster_type(mf) == "festival"


def test_album_poster_type_nested_segments():
    """artist_nested layout: {artist}/{festival}/{year} -> per-segment types."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "artist_nested"
    op = AlbumPosterOperation(config=config)
    segments = op._get_layout_segments("festival_set")
    assert segments == ["artist", "festival", "year"]


def _stamp_type(folder_jpg: Path):
    from festival_organizer.poster import read_poster_stamp

    raw = read_poster_stamp(folder_jpg)
    return raw.decode().split("\x1f")[1] if raw else None


def test_album_poster_layout_levels_place_nested(tmp_path):
    """place_nested {place}/{year}/{artist}: each depth typed, parents tracked."""
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_nested"
    artist = tmp_path / "EDC Las Vegas" / "2025" / "Tiesto"
    artist.mkdir(parents=True)
    video = artist / "2025 - EDC Las Vegas - Tiesto.mkv"
    video.write_bytes(b"")
    op = AlbumPosterOperation(config=config, library_root=tmp_path)
    mf = _make_mf(
        place="EDC Las Vegas", place_kind="festival", artist="Tiesto", year="2025"
    )
    assert [(f.name, t, p) for f, t, p in op._layout_levels(video, mf)] == [
        ("EDC Las Vegas", "festival", None),
        ("2025", "year", "festival"),
        ("Tiesto", "artist", "year"),
    ]


def test_album_poster_layout_levels_artist_nested(tmp_path):
    """artist_nested {artist}/{place}/{year}: year's parent is the place."""
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "artist_nested"
    year = tmp_path / "Tiesto" / "EDC Las Vegas" / "2025"
    year.mkdir(parents=True)
    video = year / "2025 - EDC Las Vegas - Tiesto.mkv"
    video.write_bytes(b"")
    op = AlbumPosterOperation(config=config, library_root=tmp_path)
    mf = _make_mf(
        place="EDC Las Vegas", place_kind="festival", artist="Tiesto", year="2025"
    )
    assert [(f.name, t, p) for f, t, p in op._layout_levels(video, mf)] == [
        ("Tiesto", "artist", None),
        ("EDC Las Vegas", "festival", "artist"),
        ("2025", "year", "festival"),
    ]


def test_album_poster_generates_all_levels(tmp_path):
    """execute writes a stamped folder.jpg at every level with the right type."""
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_nested"
    artist = tmp_path / "EDC Las Vegas" / "2025" / "Tiesto"
    artist.mkdir(parents=True)
    video = artist / "2025 - EDC Las Vegas - Tiesto.mkv"
    video.write_bytes(b"")
    op = AlbumPosterOperation(config=config, library_root=tmp_path)
    mf = _make_mf(
        place="EDC Las Vegas", place_kind="festival", artist="Tiesto", year="2025"
    )
    with patch(
        "festival_organizer.poster.generate_album_poster",
        side_effect=_stub_generate_album_poster,
    ):
        assert op.execute(video, mf).status == "done"
    levels = op._layout_levels(video, mf)
    assert [t for _, t, _ in levels] == ["festival", "year", "artist"]
    for folder, ptype, _ in levels:
        fj = folder / "folder.jpg"
        assert fj.exists(), f"missing {fj}"
        assert _stamp_type(fj) == ptype


def test_year_level_stamp_name_place_vs_artist():
    """Year folder is named/edition'd by its parent: place -> place+edition, artist -> artist."""
    op = AlbumPosterOperation(config=load_config())
    mf = _make_mf(place="EDC", artist="Tiesto", edition="Winter")
    assert op._level_stamp_fields("year", "festival", "2025", mf) == {
        "poster_type": "year",
        "name": "EDC",
        "year": "2025",
        "edition": "Winter",
    }
    assert op._level_stamp_fields("year", "artist", "2025", mf) == {
        "poster_type": "year",
        "name": "Tiesto",
        "year": "2025",
        "edition": "",
    }


def test_album_poster_regenerates_on_artwork_change(tmp_path, monkeypatch):
    """An artist folder poster regenerates when its DJ artwork changes (bg fingerprint)."""
    from festival_organizer import paths as paths_mod
    from festival_organizer.poster import inject_poster_stamp

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    folder_jpg = tmp_path / "folder.jpg"
    folder_jpg.write_bytes(b"\xff\xd8\xff\xd9")
    art_dir = tmp_path / "art"
    art_dir.mkdir()
    (art_dir / "dj-artwork.jpg").write_bytes(b"x" * 100)
    monkeypatch.setattr(paths_mod, "artist_cache_dir", lambda key: art_dir)

    op = AlbumPosterOperation(
        config=load_config()
    )  # artist_flat default -> artist poster
    mf = _make_mf()
    inject_poster_stamp(folder_jpg, op._expected_folder_stamp(mf, tmp_path))
    assert op.is_needed(video, mf) is False

    # Refreshed artwork (different size) -> fingerprint changes -> regenerate.
    (art_dir / "dj-artwork.jpg").write_bytes(b"x" * 200)
    assert op.is_needed(video, mf) is True


def test_bg_fingerprint_empty_for_year():
    """Year folders render a gradient (no background image) -> no fingerprint overhead."""
    op = AlbumPosterOperation(config=load_config())
    assert op._expected_bg_fingerprint("year", _make_mf()) == ""


def test_album_poster_type_place_nested_segments():
    """place_nested: {festival}/{year}/{artist} -> per-segment types."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_nested"
    op = AlbumPosterOperation(config=config)
    segments = op._get_layout_segments("festival_set")
    assert segments == ["festival", "year", "artist"]


def test_album_poster_type_mixed_segment_place_wins():
    """Mixed segment {artist} - {place} -> place wins (higher priority)."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(
        {
            **DEFAULT_CONFIG,
            "layouts": {
                **DEFAULT_CONFIG["layouts"],
                "custom": {"festival_set": "{artist} - {place}"},
            },
        }
    )
    config._data["default_layout"] = "custom"
    op = AlbumPosterOperation(config=config)
    mf = _make_mf(place="Tomorrowland", place_kind="festival")
    assert op._get_folder_poster_type(mf) == "festival"


def test_album_poster_segment_for_folder_depth(tmp_path):
    """Correct poster type at each folder depth in nested layout."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "artist_nested"
    op = AlbumPosterOperation(config=config, library_root=tmp_path)
    mf = _make_mf(place="Tomorrowland", place_kind="festival")
    # Template: {artist}/{festival}/{year}; the file lives at the deepest (year) folder.
    video = tmp_path / "Tiësto" / "Tomorrowland" / "2025" / "x.mkv"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"")
    types = {f.name: t for f, t, _ in op._layout_levels(video, mf)}
    assert types["Tiësto"] == "artist"
    assert types["Tomorrowland"] == "festival"
    assert types["2025"] == "year"


def test_layout_levels_bounded_to_layout_depth(tmp_path):
    """Regression: the per-level walk is bounded by the layout depth, not by where
    a .cratedigger marker lives, so posters are never generated above the library."""
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_nested"
    # File is nested under extra ancestors; library_root points far above them.
    video = tmp_path / "a" / "b" / "EDC Las Vegas" / "2025" / "Tiesto" / "x.mkv"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"")
    op = AlbumPosterOperation(config=config, library_root=tmp_path)
    mf = _make_mf(
        place="EDC Las Vegas", place_kind="festival", artist="Tiesto", year="2025"
    )
    levels = op._layout_levels(video, mf)
    # Exactly the 3 layout folders; the "a"/"b" ancestors are never touched.
    assert [f.name for f, _, _ in levels] == ["EDC Las Vegas", "2025", "Tiesto"]
    assert [t for _, t, _ in levels] == ["festival", "year", "artist"]


def test_get_folder_poster_type_returns_festival_for_festival_kind():
    """place_kind='festival' on a place_flat layout yields 'festival' poster type."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_flat"
    op = AlbumPosterOperation(config=config)
    mf = _make_mf(place="Tomorrowland", place_kind="festival")
    assert op._get_folder_poster_type(mf) == "festival"


def test_get_folder_poster_type_returns_festival_for_venue_kind():
    """place_kind='venue' still routes through the festival poster pipeline."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_flat"
    op = AlbumPosterOperation(config=config)
    mf = _make_mf(place="Printworks", place_kind="venue")
    assert op._get_folder_poster_type(mf) == "festival"


def test_get_folder_poster_type_returns_festival_for_location_kind():
    """place_kind='location' still routes through the festival poster pipeline."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_flat"
    op = AlbumPosterOperation(config=config)
    mf = _make_mf(place="Some Bar, Berlin", place_kind="location")
    assert op._get_folder_poster_type(mf) == "festival"


def test_get_folder_poster_type_returns_artist_for_artist_fallback():
    """place_kind='artist' overrides the layout's place segment to 'artist' poster type."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_flat"
    op = AlbumPosterOperation(config=config)
    mf = _make_mf(place="Fred again..", place_kind="artist")
    assert op._get_folder_poster_type(mf) == "artist"


def test_priority_chain_uses_place_background_priority():
    """The poster pipeline reads place_background_priority for festival/place posters."""
    cfg = load_config()
    op = AlbumPosterOperation(cfg, library_root=Path("/tmp"))
    chain = op._get_priority_chain_for_poster_type("festival")
    assert chain == ["curated_logo", "gradient"]


def test_priority_chain_artist_returns_artist_chain():
    """Artist poster_type uses artist_background_priority."""
    cfg = load_config()
    op = AlbumPosterOperation(cfg, library_root=Path("/tmp"))
    chain = op._get_priority_chain_for_poster_type("artist")
    assert chain == ["dj_artwork", "fanart_tv", "gradient"]


def test_priority_chain_year_returns_year_chain():
    """Year poster_type uses year_background_priority."""
    cfg = load_config()
    op = AlbumPosterOperation(cfg, library_root=Path("/tmp"))
    chain = op._get_priority_chain_for_poster_type("year")
    assert chain == ["gradient"]


def test_album_poster_hero_text_uses_mf_place(tmp_path):
    """Album poster hero/festival slot equals mf.place, regardless of place_kind."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_flat"
    folder = tmp_path / "Alexandra Palace"
    folder.mkdir()
    video = folder / "2024 - Alexandra Palace - Fred again...mkv"
    video.write_bytes(b"")
    op = AlbumPosterOperation(config=config, force=True)
    mf = _make_mf(
        festival="",
        artist="Fred again..",
        place="Alexandra Palace",
        place_kind="venue",
        year="2024",
    )
    with patch("festival_organizer.poster.generate_album_poster") as gen:
        op.execute(video, mf)
    assert gen.call_args.kwargs["festival"] == "Alexandra Palace"


def test_album_poster_color_lookup_uses_canonical_place(tmp_path):
    """Brand color lookup keys on mf.place, not mf.festival."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(
        {
            **DEFAULT_CONFIG,
            "default_layout": "place_flat",
            "place_config": {"Tomorrowland": {"color": "#9B1B5A"}},
        }
    )
    folder = tmp_path / "Tomorrowland"
    folder.mkdir()
    video = folder / "2024 - Tomorrowland - Tiesto.mkv"
    video.write_bytes(b"")
    op = AlbumPosterOperation(config=config, force=True)
    mf = _make_mf(
        festival="",
        artist="Tiesto",
        place="Tomorrowland",
        place_kind="festival",
        year="2024",
    )
    with patch("festival_organizer.poster.generate_album_poster") as gen:
        with patch(
            "festival_organizer.poster._hex_to_rgb", return_value=(0x9B, 0x1B, 0x5A)
        ) as hexer:
            op.execute(video, mf)
    hexer.assert_called_with("#9B1B5A")
    assert gen.call_args.kwargs["override_color"] == (0x9B, 0x1B, 0x5A)


def test_set_poster_subline_skipped_when_venue_is_place(tmp_path):
    """When place_kind=venue, the venue is in the festival slot, so the subline must not repeat it."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    mf = _make_mf(
        festival="",
        artist="Fred again..",
        venue="Printworks",
        place="Printworks",
        place_kind="venue",
        title="irrelevant",
    )
    with patch("festival_organizer.poster.generate_set_poster") as gen:
        PosterOperation(load_config()).execute(video, mf)
    kwargs = gen.call_args.kwargs
    assert kwargs["festival"] == "Printworks"
    assert kwargs["venue"] == ""


def test_album_poster_config_priority_defaults():
    """Default poster settings have correct priority chains."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    ps = config.poster_settings
    assert ps["artist_background_priority"] == ["dj_artwork", "fanart_tv", "gradient"]
    assert ps["place_background_priority"] == ["curated_logo", "gradient"]
    assert ps["year_background_priority"] == ["gradient"]


def test_album_poster_execute_uses_layout_based_type(tmp_path):
    """Execute uses layout template to determine poster type, not folder scanning."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    # artist_flat layout — should always be "artist" type regardless of folder contents
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "artist_flat"
    lib = tmp_path / "lib"
    (lib / ".cratedigger").mkdir(parents=True)

    # Create a folder with multiple different "artists" in filenames
    # Old code would detect multi-artist → festival style
    # New code should use layout template → artist style
    folder = lib / "Tiësto"
    folder.mkdir()
    (folder / "2024 - AMF - Tiësto.mkv").write_bytes(b"")
    (folder / "2024 - AMF - Tiësto-thumb.jpg").write_bytes(b"\xff\xd8")
    video = folder / "2024 - AMF - Tiësto.mkv"

    op = AlbumPosterOperation(config=config, library_root=lib, force=True)
    mf = _make_mf(artist="Tiësto", festival="AMF", year="2024")

    with patch("festival_organizer.poster.generate_album_poster") as mock_gen:
        op.execute(video, mf)
        # hero_text should be the artist (artist-type poster)
        call_kwargs = mock_gen.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        assert kwargs.get("hero_text") == "Tiësto"


def test_album_poster_execute_festival_layout_no_hero_text(tmp_path):
    """Festival layout poster should NOT have hero_text (artist name)."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_flat"
    lib = tmp_path / "lib"
    (lib / ".cratedigger").mkdir(parents=True)

    folder = lib / "Tomorrowland"
    folder.mkdir()
    (folder / "2024 - Tomorrowland - Tiësto.mkv").write_bytes(b"")
    (folder / "2024 - Tomorrowland - Tiësto-thumb.jpg").write_bytes(b"\xff\xd8")
    video = folder / "2024 - Tomorrowland - Tiësto.mkv"

    op = AlbumPosterOperation(config=config, library_root=lib, force=True)
    mf = _make_mf(artist="Tiësto", festival="Tomorrowland", year="2024")

    with patch("festival_organizer.poster.generate_album_poster") as mock_gen:
        op.execute(video, mf)
        call_kwargs = mock_gen.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        # Festival poster should not have artist as hero_text
        assert kwargs.get("hero_text") is None


def test_album_poster_warms_caches_for_unused_sources(tmp_path):
    """Album poster warms fanart_tv and DJ artwork caches even for festival layout."""
    from festival_organizer.config import Config, DEFAULT_CONFIG

    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "place_flat"
    lib = tmp_path / "lib"
    (lib / ".cratedigger").mkdir(parents=True)

    folder = lib / "Tomorrowland"
    folder.mkdir()
    (folder / "2024 - Tomorrowland - Tiesto.mkv").write_bytes(b"")
    video = folder / "2024 - Tomorrowland - Tiesto.mkv"

    op = AlbumPosterOperation(config=config, library_root=lib, force=True)
    mf = _make_mf(artist="Tiesto", festival="Tomorrowland", year="2024")

    with patch(
        "festival_organizer.poster.generate_album_poster",
        side_effect=_stub_generate_album_poster,
    ):
        with patch.object(
            op, "_try_background_source", wraps=op._try_background_source
        ) as mock_try:
            with patch.object(op, "_warm_dj_artwork_cache") as mock_warm:
                op.execute(video, mf)

    # Festival priority is [curated_logo, gradient]; fanart_tv should be
    # called via _try_background_source, DJ artwork via _warm_dj_artwork_cache
    called_sources = [call.args[0] for call in mock_try.call_args_list]
    assert "fanart_tv" in called_sources
    mock_warm.assert_called_once_with(folder)


def test_keyboard_interrupt_propagates_from_nfo(tmp_path):
    """KeyboardInterrupt during NFO generation propagates, not swallowed."""
    import pytest

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()
    op = NfoOperation(load_config())

    with patch("festival_organizer.nfo.generate_nfo", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            op.execute(video, mf)


# --- Sidecar move tests (Issue 2.4) ---


def test_organize_moves_nfo_sidecar(tmp_path):
    """Organize moves .nfo sidecar along with the video."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    video = src / "2024 - AMF - Tiësto.mkv"
    video.write_bytes(b"video")
    nfo = src / "2024 - AMF - Tiësto.nfo"
    nfo.write_text("<nfo/>")

    target = dst / "Tiësto - AMF - 2024.mkv"
    op = OrganizeOperation(target=target)
    result = op.execute(video, _make_mf())

    assert result.status == "done"
    # Video moved
    assert target.exists()
    assert not video.exists()
    # NFO sidecar moved and renamed to match new stem
    assert (dst / "Tiësto - AMF - 2024.nfo").exists()
    assert not nfo.exists()


def test_organize_moves_dash_suffixed_sidecars(tmp_path):
    """Organize moves -poster.jpg and -thumb.jpg sidecars."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    video = src / "2024 - AMF - Tiësto.mkv"
    video.write_bytes(b"video")
    poster = src / "2024 - AMF - Tiësto-poster.jpg"
    poster.write_bytes(b"\xff\xd8poster")
    thumb = src / "2024 - AMF - Tiësto-thumb.jpg"
    thumb.write_bytes(b"\xff\xd8thumb")

    target = dst / "Tiësto - AMF - 2024.mkv"
    op = OrganizeOperation(target=target)
    result = op.execute(video, _make_mf())

    assert result.status == "done"
    assert (dst / "Tiësto - AMF - 2024-poster.jpg").exists()
    assert (dst / "Tiësto - AMF - 2024-thumb.jpg").exists()
    assert not poster.exists()
    assert not thumb.exists()


def test_organize_moves_subtitle_sidecars(tmp_path):
    """Organize moves .srt, .ass, .sub, .idx subtitle sidecars."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    video = src / "set.mkv"
    video.write_bytes(b"video")
    for ext in (".srt", ".ass", ".sub", ".idx"):
        (src / f"set{ext}").write_text("subtitle")

    target = dst / "set.mkv"
    op = OrganizeOperation(target=target)
    result = op.execute(video, _make_mf())

    assert result.status == "done"
    for ext in (".srt", ".ass", ".sub", ".idx"):
        assert (dst / f"set{ext}").exists()
        assert not (src / f"set{ext}").exists()


def test_organize_does_not_move_folder_level_files(tmp_path):
    """Organize does NOT move folder.jpg, fanart.jpg."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    video = src / "set.mkv"
    video.write_bytes(b"video")
    # Folder-level files that must stay
    (src / "folder.jpg").write_bytes(b"\xff\xd8")
    (src / "fanart.jpg").write_bytes(b"\xff\xd8")
    # Also a real sidecar that should move
    (src / "set.nfo").write_text("<nfo/>")

    target = dst / "set.mkv"
    op = OrganizeOperation(target=target)
    op.execute(video, _make_mf())

    # Folder-level files must remain
    assert (src / "folder.jpg").exists()
    assert (src / "fanart.jpg").exists()
    # Sidecar should have moved
    assert (dst / "set.nfo").exists()


def test_organize_does_not_move_unrelated_files(tmp_path):
    """Organize does not move files with a different stem."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    video = src / "set1.mkv"
    video.write_bytes(b"video")
    # Unrelated file with different stem
    (src / "set2.nfo").write_text("<nfo/>")
    (src / "set2-poster.jpg").write_bytes(b"\xff\xd8")

    target = dst / "set1.mkv"
    op = OrganizeOperation(target=target)
    op.execute(video, _make_mf())

    # Unrelated files must remain
    assert (src / "set2.nfo").exists()
    assert (src / "set2-poster.jpg").exists()


def test_organize_copy_copies_sidecars(tmp_path):
    """Organize with action=copy copies sidecars instead of moving."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    video = src / "set.mkv"
    video.write_bytes(b"video")
    nfo = src / "set.nfo"
    nfo.write_text("<nfo/>")

    target = dst / "set.mkv"
    op = OrganizeOperation(target=target, action="copy")
    result = op.execute(video, _make_mf())

    assert result.status == "done"
    # Both source and destination should exist for copy
    assert video.exists()
    assert nfo.exists()
    assert (dst / "set.nfo").exists()


def test_organize_rename_moves_sidecars(tmp_path):
    """Organize with action=rename also moves sidecars."""
    src = tmp_path / "src"
    video = src / "old.mkv"
    src.mkdir()
    video.write_bytes(b"video")
    (src / "old.nfo").write_text("<nfo/>")
    (src / "old-poster.jpg").write_bytes(b"\xff\xd8")

    target = src / "new.mkv"
    op = OrganizeOperation(target=target, action="rename")
    result = op.execute(video, _make_mf())

    assert result.status == "done"
    assert (src / "new.nfo").exists()
    assert (src / "new-poster.jpg").exists()
    assert not (src / "old.nfo").exists()
    assert not (src / "old-poster.jpg").exists()


def test_organize_sidecar_stem_rename(tmp_path):
    """Sidecars get renamed from old stem to new stem when filename template changes."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    video = src / "2024 - AMF - Tiësto.mkv"
    video.write_bytes(b"video")
    (src / "2024 - AMF - Tiësto.nfo").write_text("<nfo/>")
    (src / "2024 - AMF - Tiësto-poster.jpg").write_bytes(b"\xff\xd8")

    target = dst / "Tiësto - AMF - 2024.mkv"
    op = OrganizeOperation(target=target)
    op.execute(video, _make_mf())

    # Sidecars should use the new stem
    assert (dst / "Tiësto - AMF - 2024.nfo").exists()
    assert (dst / "Tiësto - AMF - 2024-poster.jpg").exists()
    # Old files gone
    assert not (src / "2024 - AMF - Tiësto.nfo").exists()
    assert not (src / "2024 - AMF - Tiësto-poster.jpg").exists()


# --- FanartOperation stores URLs on MediaFile ---


def test_fanart_op_stores_urls_on_mediafile(tmp_path):
    """FanartOperation stores fanart and clearlogo URLs on MediaFile."""
    config = Config(
        {
            **DEFAULT_CONFIG,
            "fanart": {"enabled": True, "project_api_key": "test-key"},
        }
    )
    lib = tmp_path / "lib"
    lib.mkdir()
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(artist="Hardwell")

    mock_cache = MagicMock()
    mock_cache.has.return_value = False

    with patch(
        "festival_organizer.fanart.download_artist_images", return_value=(True, True)
    ):
        with patch("festival_organizer.fanart.lookup_mbid", return_value="mbid-123"):
            with patch("festival_organizer.fanart.fetch_artist_images") as mock_fetch:
                mock_fetch.return_value = {
                    "hdmusiclogo": [
                        {
                            "url": "https://fanart.tv/logo.png",
                            "likes": "5",
                            "lang": "en",
                        }
                    ],
                    "artistbackground": [
                        {"url": "https://fanart.tv/bg.jpg", "likes": "3"}
                    ],
                }
                op = FanartOperation(config, lib)
                op._cache = mock_cache
                op.execute(video, mf)

    assert mf.fanart_url == "https://fanart.tv/bg.jpg"
    assert mf.clearlogo_url == "https://fanart.tv/logo.png"


def test_artist_dir_uses_global_cache(tmp_path):
    """Artist artwork directory resolves under the user cache_dir(), not library root."""
    lib = tmp_path / "lib"
    lib.mkdir()
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    config = Config(
        {
            **DEFAULT_CONFIG,
            "fanart": {"enabled": True, "project_api_key": "test-key"},
        }
    )
    op = FanartOperation(config, lib)
    with patch(
        "festival_organizer.operations.paths.cache_dir", return_value=cache_root
    ):
        result = op._artist_dir("Tiesto")

    assert str(cache_root) in str(result)
    assert str(lib) not in str(result)
    assert result == cache_root / "artists" / "Tiesto"


def test_artist_cache_dir_joins_folder_key():
    """paths.artist_cache_dir joins a canonical folder key under cache_dir()/artists."""
    from festival_organizer import paths

    result = paths.artist_cache_dir("tiesto")
    assert result == paths.cache_dir() / "artists" / "tiesto"

    result = paths.artist_cache_dir("arminvanbuuren")
    assert result == paths.cache_dir() / "artists" / "arminvanbuuren"


# --- AlbumPosterOperation DJ artwork fallback via tracklist URL ---


def test_album_poster_dj_artwork_fallback_from_tracklist(tmp_path):
    """When dj_artwork_url is empty but tracklists_url exists, fetch DJ artwork from tracklist page."""
    config = Config(
        {
            **DEFAULT_CONFIG,
            "tracklists": {"email": "test@test.com", "password": "pw"},
        }
    )
    lib = tmp_path / "lib"
    lib.mkdir()

    folder = tmp_path / "artist"
    folder.mkdir()
    video = folder / "set.mkv"
    video.write_bytes(b"")

    # MediaFile with tracklists_url but no dj_artwork_url
    mf = _make_mf(
        tracklists_url="https://www.1001tracklists.com/tracklist/abc123/",
        dj_artwork_url="",
    )

    op = AlbumPosterOperation(config=config, library_root=lib)

    mock_resp = MagicMock()
    mock_resp.text = '<a href="/dj/martingarrix/">MG</a>'

    # Mock analyse_file to return our mf (with tracklists_url, no dj_artwork_url)
    with patch("festival_organizer.analyzer.analyse_file", return_value=mf):
        with patch("festival_organizer.tracklists.api.TracklistSession") as MockSession:
            api_instance = MockSession.return_value
            api_instance.login.return_value = None
            api_instance._request.return_value = mock_resp
            api_instance._fetch_dj_profile.return_value = {
                "artwork_url": "https://cdn.1001tracklists.com/images/dj/martingarrix.jpg",
                "aliases": [],
                "member_of": [],
            }
            with patch.object(
                op, "_download_dj_artwork", return_value=Path("/tmp/cached.jpg")
            ):
                result = op._find_dj_artwork(folder)

    assert result is not None


def test_album_poster_dj_artwork_fallback_no_credentials(tmp_path):
    """Without credentials, fallback returns None (no crash)."""
    config = Config(DEFAULT_CONFIG)  # No tracklists credentials
    lib = tmp_path / "lib"
    lib.mkdir()

    folder = tmp_path / "artist"
    folder.mkdir()
    video = folder / "set.mkv"
    video.write_bytes(b"")

    mf = _make_mf(
        tracklists_url="https://www.1001tracklists.com/tracklist/abc123/",
        dj_artwork_url="",
    )

    op = AlbumPosterOperation(config=config, library_root=lib)

    # Mock analyse_file to return our mf
    with patch("festival_organizer.analyzer.analyse_file", return_value=mf):
        result = op._find_dj_artwork(folder)

    # Should return None (no credentials, no dj_artwork_url)
    assert result is None


# --- Curated logo tests ---


def test_find_curated_logo_library_level(tmp_path):
    """Curated logo found at library .cratedigger/places/{Name}/logo.png."""
    config = Config(DEFAULT_CONFIG)
    config._data["place_aliases"] = {"Tomorrowland": ["TML", "Tomorrowland Belgium"]}
    lib = tmp_path / "lib"
    logo_dir = lib / ".cratedigger" / "places" / "Tomorrowland"
    logo_dir.mkdir(parents=True)
    logo_file = logo_dir / "logo.png"
    logo_file.write_bytes(b"\x89PNG")

    op = AlbumPosterOperation(config=config, library_root=lib)
    result = op._find_curated_logo("Tomorrowland")
    assert result == logo_file


def test_find_curated_logo_alias_resolution(tmp_path):
    """Alias resolves to canonical name for logo lookup."""
    config = Config(DEFAULT_CONFIG)
    config._data["place_aliases"] = {"Tomorrowland": ["TML"]}
    lib = tmp_path / "lib"
    logo_dir = lib / ".cratedigger" / "places" / "Tomorrowland"
    logo_dir.mkdir(parents=True)
    (logo_dir / "logo.jpg").write_bytes(b"\xff\xd8")

    op = AlbumPosterOperation(config=config, library_root=lib)
    result = op._find_curated_logo("TML")
    assert result is not None
    assert result.name == "logo.jpg"


def test_find_curated_logo_missing(tmp_path):
    """Returns None when no curated logo exists."""
    config = Config(DEFAULT_CONFIG)
    lib = tmp_path / "lib"
    lib.mkdir()

    op = AlbumPosterOperation(config=config, library_root=lib)
    assert op._find_curated_logo("Nonexistent") is None


def test_find_curated_logo_user_global(tmp_path, monkeypatch):
    """Curated logo resolved from user-global paths.places_logo_dir()."""
    config = Config(DEFAULT_CONFIG)
    config._data["place_aliases"] = {"Tomorrowland": ["TML"]}
    lib = tmp_path / "lib"
    lib.mkdir()
    user_global_dir = tmp_path / "user_places"
    (user_global_dir / "Tomorrowland").mkdir(parents=True)
    logo_file = user_global_dir / "Tomorrowland" / "logo.png"
    logo_file.write_bytes(b"\x89PNG")
    monkeypatch.setattr(
        "festival_organizer.operations.paths.places_logo_dir",
        lambda: user_global_dir,
    )

    op = AlbumPosterOperation(config=config, library_root=lib)
    assert op._find_curated_logo("Tomorrowland") == logo_file


def test_find_curated_logo_library_wins_over_user_global(tmp_path, monkeypatch):
    """Library-local logo wins when both library and user-global contain a logo."""
    config = Config(DEFAULT_CONFIG)
    config._data["place_aliases"] = {"Tomorrowland": ["TML"]}
    lib = tmp_path / "lib"
    lib_logo_dir = lib / ".cratedigger" / "places" / "Tomorrowland"
    lib_logo_dir.mkdir(parents=True)
    lib_logo = lib_logo_dir / "logo.png"
    lib_logo.write_bytes(b"\x89PNG")

    user_global_dir = tmp_path / "user_places"
    (user_global_dir / "Tomorrowland").mkdir(parents=True)
    (user_global_dir / "Tomorrowland" / "logo.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr(
        "festival_organizer.operations.paths.places_logo_dir",
        lambda: user_global_dir,
    )

    op = AlbumPosterOperation(config=config, library_root=lib)
    assert op._find_curated_logo("Tomorrowland") == lib_logo


def test_find_curated_logo_empty_festival(tmp_path):
    """Returns None for empty festival name."""
    config = Config(DEFAULT_CONFIG)
    op = AlbumPosterOperation(config=config, library_root=tmp_path)
    assert op._find_curated_logo("") is None


def test_try_background_source_curated_logo(tmp_path):
    """curated_logo source calls _find_curated_logo with mf.place."""
    config = Config(DEFAULT_CONFIG)
    config._data["place_aliases"] = {"AMF": ["AMF"]}
    lib = tmp_path / "lib"
    logo_dir = lib / ".cratedigger" / "places" / "AMF"
    logo_dir.mkdir(parents=True)
    logo_file = logo_dir / "logo.webp"
    logo_file.write_bytes(b"RIFF")

    op = AlbumPosterOperation(config=config, library_root=lib)
    mf = _make_mf(festival="AMF", place="AMF", place_kind="festival")
    result = op._try_background_source("curated_logo", tmp_path, mf)
    assert result == logo_file


def test_curated_logo_found_in_places_dir(tmp_path):
    """Curated logo found at library .cratedigger/places/{Name}/logo.png."""
    config = Config(DEFAULT_CONFIG)
    config._data["place_aliases"] = {"Tomorrowland": ["TML"]}
    lib = tmp_path / "lib"
    logo_dir = lib / ".cratedigger" / "places" / "Tomorrowland"
    logo_dir.mkdir(parents=True)
    logo_file = logo_dir / "logo.png"
    logo_file.write_bytes(b"\x89PNG")

    op = AlbumPosterOperation(config=config, library_root=lib)
    assert op._find_curated_logo("Tomorrowland") == logo_file


def test_try_background_source_uses_mf_place_for_venue(tmp_path):
    """_try_background_source passes mf.place (not mf.festival) to logo lookup."""
    config = Config(DEFAULT_CONFIG)
    op = AlbumPosterOperation(config=config, library_root=tmp_path)
    mf = _make_mf(festival="", place="Alexandra Palace", place_kind="venue")
    with patch.object(op, "_find_curated_logo", return_value=None) as find:
        op._try_background_source("curated_logo", tmp_path, mf)
    find.assert_called_once_with("Alexandra Palace", mf.edition)


def test_logo_summary_tracks_hits_and_misses(tmp_path):
    """logo_summary reports used logos and missing ones."""
    config = Config(DEFAULT_CONFIG)
    config._data["place_aliases"] = {"AMF": ["AMF"], "TML": ["TML"]}
    lib = tmp_path / "lib"
    logo_dir = lib / ".cratedigger" / "places" / "AMF"
    logo_dir.mkdir(parents=True)
    logo_file = logo_dir / "logo.png"
    logo_file.write_bytes(b"\x89PNG")

    op = AlbumPosterOperation(config=config, library_root=lib)
    op._logo_hits["AMF"] = logo_file
    op._logo_misses.add("TML")

    summary = op.logo_summary()
    assert any("Curated logos used: 1" in line for line in summary)
    assert any("Missing curated logos: 1" in line for line in summary)
    assert any("AMF" in line for line in summary)
    assert any("TML" in line for line in summary)


def test_logo_summary_scans_places_dir(tmp_path):
    """logo_summary reports unmatched folders from .cratedigger/places/."""
    config = Config(DEFAULT_CONFIG)
    lib = tmp_path / "lib"
    (lib / ".cratedigger" / "places" / "PlaceOnly").mkdir(parents=True)

    op = AlbumPosterOperation(config=config, library_root=lib)
    summary = op.logo_summary()
    text = "\n".join(summary)
    assert "PlaceOnly" in text


def test_download_artwork_max_width_resizes(tmp_path):
    """Downloaded artwork wider than max_width is resized down."""
    from PIL import Image
    import io

    # Create an 800x800 test image
    img = Image.new("RGB", (800, 800), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    mock_resp = MagicMock()
    mock_resp.content = image_bytes
    mock_resp.raise_for_status = MagicMock()

    op = AlbumPosterOperation(config=Config(DEFAULT_CONFIG), library_root=tmp_path)
    with patch("festival_organizer.operations.paths.cache_dir", return_value=tmp_path):
        with patch(
            "festival_organizer.operations.requests.get", return_value=mock_resp
        ):
            result = op._download_artwork(
                "https://example.com/big.jpg", "test-art", max_width=600
            )

    assert result is not None
    with Image.open(result) as saved:
        assert saved.width == 600
        assert saved.height == 600


def test_download_artwork_no_max_width_keeps_original(tmp_path):
    """Without max_width, artwork is saved at original size."""
    from PIL import Image
    import io

    img = Image.new("RGB", (800, 800), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    mock_resp = MagicMock()
    mock_resp.content = image_bytes
    mock_resp.raise_for_status = MagicMock()

    op = AlbumPosterOperation(config=Config(DEFAULT_CONFIG), library_root=tmp_path)
    with patch("festival_organizer.operations.paths.cache_dir", return_value=tmp_path):
        with patch(
            "festival_organizer.operations.requests.get", return_value=mock_resp
        ):
            result = op._download_artwork("https://example.com/big.jpg", "test-art")

    assert result is not None
    with Image.open(result) as saved:
        assert saved.width == 800


def test_download_artwork_uses_global_cache(tmp_path):
    """Downloaded artwork is cached under the user cache_dir(), not library root."""
    from PIL import Image
    import io

    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    mock_resp = MagicMock()
    mock_resp.content = image_bytes
    mock_resp.raise_for_status = MagicMock()

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    lib = tmp_path / "lib"
    lib.mkdir()

    op = AlbumPosterOperation(config=Config(DEFAULT_CONFIG), library_root=lib)
    with patch(
        "festival_organizer.operations.paths.cache_dir", return_value=cache_root
    ):
        with patch(
            "festival_organizer.operations.requests.get", return_value=mock_resp
        ):
            result = op._download_artwork("https://example.com/photo.jpg", "dj-artwork")

    assert result is not None
    # Cached under the user cache_dir(), not library root
    assert str(cache_root) in str(result)
    assert str(lib) not in str(result)
    assert (cache_root / "dj-artwork").exists()


def test_download_dj_artwork_saves_as_jpeg_in_artist_dir(tmp_path):
    """DJ artwork is saved as dj-artwork.jpg in the artist's directory."""
    from PIL import Image
    import io

    img = Image.new("RGB", (800, 800), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    mock_resp = MagicMock()
    mock_resp.content = image_bytes
    mock_resp.raise_for_status = MagicMock()

    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    op = AlbumPosterOperation(config=Config(DEFAULT_CONFIG), library_root=tmp_path)
    with patch(
        "festival_organizer.operations.paths.cache_dir", return_value=cache_root
    ):
        with patch(
            "festival_organizer.operations.requests.get", return_value=mock_resp
        ):
            result = op._download_dj_artwork("https://example.com/photo.png", "Tiesto")

    assert result is not None
    assert result.name == "dj-artwork.jpg"
    assert "tiesto" in str(result)
    with Image.open(result) as saved:
        assert saved.format == "JPEG"


def test_download_dj_artwork_crops_and_resizes(tmp_path):
    """DJ artwork is center-cropped to square and resized to 550px max."""
    from PIL import Image
    import io

    img = Image.new("RGB", (1200, 800), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    mock_resp = MagicMock()
    mock_resp.content = image_bytes
    mock_resp.raise_for_status = MagicMock()

    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    op = AlbumPosterOperation(config=Config(DEFAULT_CONFIG), library_root=tmp_path)
    with patch(
        "festival_organizer.operations.paths.cache_dir", return_value=cache_root
    ):
        with patch(
            "festival_organizer.operations.requests.get", return_value=mock_resp
        ):
            result = op._download_dj_artwork("https://example.com/big.jpg", "Tiesto")

    assert result is not None
    with Image.open(result) as saved:
        assert saved.width == 550
        assert saved.height == 550


def test_download_dj_artwork_returns_cached(tmp_path):
    """DJ artwork returns cached file if fresh."""
    from PIL import Image

    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    artist_dir = cache_root / "artists" / "tiesto"
    artist_dir.mkdir(parents=True)
    cached = artist_dir / "dj-artwork.jpg"
    # Write a valid tiny JPEG
    img = Image.new("RGB", (10, 10), color="red")
    img.save(cached, "JPEG")

    op = AlbumPosterOperation(config=Config(DEFAULT_CONFIG), library_root=tmp_path)
    with patch(
        "festival_organizer.operations.paths.cache_dir", return_value=cache_root
    ):
        result = op._download_dj_artwork("https://example.com/photo.jpg", "Tiesto")

    assert result == cached


def test_organize_op_tracks_sidecars_moved(tmp_path):
    """OrganizeOperation.sidecars_moved counts sidecars after execute."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"video")
    (tmp_path / "test.nfo").write_text("<nfo/>")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")

    target = tmp_path / "sub" / "test.mkv"
    op = OrganizeOperation(target=target, action="move")
    result = op.execute(video, _make_mf())
    assert result.status == "done"
    assert op.sidecars_moved == 2


def test_organize_op_sidecars_moved_zero_when_none(tmp_path):
    """sidecars_moved is 0 when no sidecars exist."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"video")

    target = tmp_path / "sub" / "test.mkv"
    op = OrganizeOperation(target=target, action="move")
    result = op.execute(video, _make_mf())
    assert result.status == "done"
    assert op.sidecars_moved == 0


# --- AlbumPosterOperation._classify_segment ---


def test_classify_segment_recognizes_place():
    assert AlbumPosterOperation._classify_segment("{place}{ edition}") == "festival"
    assert AlbumPosterOperation._classify_segment("{place}") == "festival"


def test_classify_segment_festival_token_no_longer_recognized():
    # {festival} was removed in 0.15.0; classifier no longer treats it as a place token.
    # A segment containing only {festival} therefore defaults to "artist".
    assert AlbumPosterOperation._classify_segment("{festival}{ edition}") == "artist"


def test_classify_segment_artist_token():
    # place wins over artist when both tokens are present in a segment
    assert AlbumPosterOperation._classify_segment("{artist}/{place}") == "festival"
    assert AlbumPosterOperation._classify_segment("{artist}") == "artist"


def test_classify_segment_year_token():
    assert AlbumPosterOperation._classify_segment("{year}") == "year"


def test_classify_segment_default_to_artist():
    assert AlbumPosterOperation._classify_segment("literal_text_no_tokens") == "artist"


def _portrait(path):
    Image.new("RGB", (1000, 1500), (10, 10, 20)).save(str(path), "JPEG", quality=95)


def test_cover_op_needed_when_stamp_absent(tmp_path):
    video = tmp_path / "t.mkv"
    video.write_bytes(b"")
    _portrait(tmp_path / "t-poster.jpg")
    assert CoverEmbedOperation(load_config()).is_needed(video, _make_mf()) is True


def test_cover_op_not_needed_when_stamp_matches(tmp_path):
    from festival_organizer.poster import build_cover_stamp, inject_poster_stamp

    video = tmp_path / "t.mkv"
    video.write_bytes(b"")
    poster = tmp_path / "t-poster.jpg"
    _portrait(poster)
    cfg = load_config()
    inject_poster_stamp(
        poster,
        build_cover_stamp(**_resolve_poster_fields(_make_mf(), cfg), artists_1001tl=[]),
    )
    assert CoverEmbedOperation(cfg).is_needed(video, _make_mf()) is False


def test_cover_op_not_needed_when_no_poster(tmp_path):
    video = tmp_path / "t.mkv"
    video.write_bytes(b"")
    assert CoverEmbedOperation(load_config()).is_needed(video, _make_mf()) is False


def test_cover_op_force_overrides_stamp_match(tmp_path):
    from festival_organizer.poster import build_cover_stamp, inject_poster_stamp

    video = tmp_path / "t.mkv"
    video.write_bytes(b"")
    poster = tmp_path / "t-poster.jpg"
    _portrait(poster)
    cfg = load_config()
    inject_poster_stamp(
        poster,
        build_cover_stamp(**_resolve_poster_fields(_make_mf(), cfg), artists_1001tl=[]),
    )
    assert CoverEmbedOperation(cfg, force=True).is_needed(video, _make_mf()) is True


def test_cover_op_not_needed_for_non_matroska_suffix(tmp_path):
    video = tmp_path / "t.mp4"
    video.write_bytes(b"")
    _portrait(
        tmp_path / "t-poster.jpg"
    )  # poster present, so the False comes from the suffix gate
    assert CoverEmbedOperation(load_config()).is_needed(video, _make_mf()) is False


def test_cover_op_execute_converges_and_stamps(tmp_path):
    from festival_organizer.poster import read_poster_stamp, build_cover_stamp

    video = tmp_path / "t.mkv"
    video.write_bytes(b"")
    poster = tmp_path / "t-poster.jpg"
    _portrait(poster)
    thumb = tmp_path / "t-thumb.jpg"
    thumb.write_bytes(b"\xff\xd8")
    cfg = load_config()
    with patch(
        "festival_organizer.cover_embed.converge_cover_attachments", return_value=True
    ) as conv:
        result = CoverEmbedOperation(cfg).execute(video, _make_mf())
    conv.assert_called_once_with(video, poster, thumb)
    assert result.status == "done"
    assert read_poster_stamp(poster) == build_cover_stamp(
        **_resolve_poster_fields(_make_mf(), cfg), artists_1001tl=[]
    )


def test_cover_op_execute_no_stamp_when_converge_fails(tmp_path):
    from festival_organizer.poster import read_poster_stamp

    video = tmp_path / "t.mkv"
    video.write_bytes(b"")
    poster = tmp_path / "t-poster.jpg"
    _portrait(poster)
    (tmp_path / "t-thumb.jpg").write_bytes(b"\xff\xd8")
    with patch(
        "festival_organizer.cover_embed.converge_cover_attachments", return_value=False
    ):
        result = CoverEmbedOperation(load_config()).execute(video, _make_mf())
    assert result.status == "error"
    assert read_poster_stamp(poster) is None  # not stamped on failed embed


def test_cover_op_execute_refuses_non_portrait_poster(tmp_path):
    video = tmp_path / "t.mkv"
    video.write_bytes(b"")
    poster = tmp_path / "t-poster.jpg"
    Image.new("RGB", (1600, 900), (10, 10, 20)).save(str(poster), "JPEG")  # landscape!
    with patch("festival_organizer.cover_embed.converge_cover_attachments") as conv:
        result = CoverEmbedOperation(load_config()).execute(video, _make_mf())
    conv.assert_not_called()
    assert result.status == "error"


def test_poster_op_passes_billed_artists_not_resolved(tmp_path):
    """PosterOperation must pass the billed list (alias), never the resolved one."""
    mf = _make_mf(
        artist="ALOK",
        artists=["ALOK", "R3HAB"],  # resolved canonical
        artists_1001tl=["SOMETHING ELSE", "R3HAB"],  # billed alias
    )
    kwargs = _run_poster_and_capture_kwargs(tmp_path, mf)
    assert kwargs["artists_1001tl"] == ["SOMETHING ELSE", "R3HAB"]
