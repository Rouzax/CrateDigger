from pathlib import Path
from unittest.mock import patch, MagicMock
from festival_organizer.models import MediaFile
from festival_organizer.operations import (
    NfoOperation, ArtOperation, PosterOperation, TagsOperation,
    OrganizeOperation, AlbumPosterOperation,
)
from festival_organizer.config import load_config


def _make_mf(**kwargs):
    defaults = dict(source_path=Path("test.mkv"), artist="Test",
                    festival="TML", year="2024", content_type="festival_set")
    defaults.update(kwargs)
    return MediaFile(**defaults)


def test_nfo_op_needed_when_missing(tmp_path):
    """NFO operation needed when .nfo file doesn't exist."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = NfoOperation(load_config())
    assert op.is_needed(video, _make_mf()) is True


def test_nfo_op_not_needed_when_exists(tmp_path):
    """NFO operation not needed when .nfo file exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test.nfo").write_text("<musicvideo/>")
    op = NfoOperation(load_config())
    assert op.is_needed(video, _make_mf()) is False


def test_nfo_op_needed_when_forced(tmp_path):
    """NFO operation needed when forced, even if .nfo exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test.nfo").write_text("<musicvideo/>")
    op = NfoOperation(load_config(), force=True)
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


def test_poster_op_not_needed_when_poster_exists(tmp_path):
    """Poster operation not needed when poster exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    (tmp_path / "test-poster.jpg").write_bytes(b"\xff\xd8")
    op = PosterOperation(load_config())
    assert op.is_needed(video, _make_mf()) is False


def test_poster_op_not_needed_when_no_thumb(tmp_path):
    """Poster operation not needed when no thumb available."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = PosterOperation(load_config())
    assert op.is_needed(video, _make_mf()) is False


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


def test_album_poster_needed_when_missing(tmp_path):
    """Album poster needed when folder.jpg doesn't exist."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = AlbumPosterOperation(config=load_config())
    assert op.is_needed(video, _make_mf()) is True


def test_album_poster_not_needed_when_exists(tmp_path):
    """Album poster not needed when folder.jpg exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "folder.jpg").write_bytes(b"\xff\xd8")
    op = AlbumPosterOperation(config=load_config())
    assert op.is_needed(video, _make_mf()) is False


def test_album_poster_execute_parses_filenames(tmp_path):
    """Album poster execute() correctly passes config to parse_filename."""
    video = tmp_path / "2024 - Tomorrowland - Bicep.mkv"
    video.write_bytes(b"")
    (tmp_path / "2024 - Tomorrowland - Bicep-thumb.jpg").write_bytes(b"\xff\xd8")
    op = AlbumPosterOperation(config=load_config())
    mf = _make_mf(festival="Tomorrowland", artist="Bicep", year="2024")
    with patch("festival_organizer.poster.generate_album_poster"):
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
    lib = tmp_path / "lib"
    fanart = lib / ".cratedigger" / "artists" / "Bicep" / "fanart.jpg"
    fanart.parent.mkdir(parents=True)
    fanart.write_bytes(b"\xff\xd8")
    op = AlbumPosterOperation(config=load_config(), library_root=lib)
    result = op._find_fanart_background(tmp_path, "Bicep")
    assert result == fanart


def test_album_poster_fanart_single_artist_dash_we(tmp_path):
    """Dash-separated WE suffix doesn't split artist detection."""
    (tmp_path / "2024 - TML - Bicep - WE1.mkv").write_bytes(b"")
    (tmp_path / "2024 - TML - Bicep - WE2.mkv").write_bytes(b"")
    lib = tmp_path / "lib"
    fanart = lib / ".cratedigger" / "artists" / "Bicep" / "fanart.jpg"
    fanart.parent.mkdir(parents=True)
    fanart.write_bytes(b"\xff\xd8")
    op = AlbumPosterOperation(config=load_config(), library_root=lib)
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
    with patch("festival_organizer.poster.generate_album_poster"):
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
    with patch("festival_organizer.poster.generate_album_poster"):
        op.execute(video1, mf1)
    # Different folder: still needed
    assert op.is_needed(video2, mf2) is True


def test_album_poster_type_from_artist_flat_layout():
    """artist_flat layout: {artist} -> artist poster type."""
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "artist_flat"
    op = AlbumPosterOperation(config=config)
    assert op._get_folder_poster_type("festival_set") == "artist"


def test_album_poster_type_from_festival_flat_layout():
    """festival_flat layout: {festival} -> festival poster type."""
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "festival_flat"
    op = AlbumPosterOperation(config=config)
    assert op._get_folder_poster_type("festival_set") == "festival"


def test_album_poster_type_nested_segments():
    """artist_nested layout: {artist}/{festival}/{year} -> per-segment types."""
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "artist_nested"
    op = AlbumPosterOperation(config=config)
    segments = op._get_layout_segments("festival_set")
    assert segments == ["artist", "festival", "year"]


def test_album_poster_type_festival_nested_segments():
    """festival_nested: {festival}/{year}/{artist} -> per-segment types."""
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "festival_nested"
    op = AlbumPosterOperation(config=config)
    segments = op._get_layout_segments("festival_set")
    assert segments == ["festival", "year", "artist"]


def test_album_poster_type_mixed_segment_festival_wins():
    """Mixed segment {artist} - {festival} -> festival wins (higher priority)."""
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config({**DEFAULT_CONFIG, "layouts": {
        **DEFAULT_CONFIG["layouts"],
        "custom": {"festival_set": "{artist} - {festival}"},
    }})
    config._data["default_layout"] = "custom"
    op = AlbumPosterOperation(config=config)
    assert op._get_folder_poster_type("festival_set") == "festival"


def test_album_poster_segment_for_folder_depth(tmp_path):
    """Correct poster type at each folder depth in nested layout."""
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "artist_nested"
    op = AlbumPosterOperation(config=config, library_root=tmp_path)
    # Template: {artist}/{festival}/{year}
    # Depth 0 = artist, depth 1 = festival, depth 2 = year
    artist_folder = tmp_path / "Tiësto"
    festival_folder = artist_folder / "Tomorrowland"
    year_folder = festival_folder / "2025"
    assert op._get_poster_type_for_folder(year_folder, "festival_set") == "year"
    assert op._get_poster_type_for_folder(festival_folder, "festival_set") == "festival"
    assert op._get_poster_type_for_folder(artist_folder, "festival_set") == "artist"


def test_album_poster_config_priority_defaults():
    """Default poster settings have correct priority chains."""
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config(DEFAULT_CONFIG)
    ps = config.poster_settings
    assert ps["artist_background_priority"] == ["dj_artwork", "fanart_tv", "event_artwork", "gradient"]
    assert ps["festival_background_priority"] == ["event_artwork", "thumb_collage", "gradient"]
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
    config._data["default_layout"] = "festival_flat"
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
    """Organize does NOT move folder.jpg, fanart.jpg, album.nfo."""
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
