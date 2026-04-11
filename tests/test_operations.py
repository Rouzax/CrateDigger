from pathlib import Path
from unittest.mock import patch, MagicMock
from festival_organizer.models import MediaFile
from festival_organizer.operations import (
    NfoOperation, ArtOperation, PosterOperation, TagsOperation,
    OrganizeOperation, AlbumPosterOperation, FanartOperation,
    _safe_artist_dir,
)
from festival_organizer.config import load_config, Config, DEFAULT_CONFIG


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
    assert ps["artist_background_priority"] == ["dj_artwork", "fanart_tv", "gradient"]
    assert ps["festival_background_priority"] == ["curated_logo", "gradient"]
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


def test_album_poster_warms_caches_for_unused_sources(tmp_path):
    """Album poster warms dj_artwork and fanart_tv caches even for festival layout."""
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config(DEFAULT_CONFIG)
    config._data["default_layout"] = "festival_flat"
    lib = tmp_path / "lib"
    (lib / ".cratedigger").mkdir(parents=True)

    folder = lib / "Tomorrowland"
    folder.mkdir()
    (folder / "2024 - Tomorrowland - Tiesto.mkv").write_bytes(b"")
    video = folder / "2024 - Tomorrowland - Tiesto.mkv"

    op = AlbumPosterOperation(config=config, library_root=lib, force=True)
    mf = _make_mf(artist="Tiesto", festival="Tomorrowland", year="2024")

    with patch("festival_organizer.poster.generate_album_poster"):
        with patch.object(op, "_try_background_source", wraps=op._try_background_source) as mock_try:
            op.execute(video, mf)

    # Festival priority is [curated_logo, gradient]; dj_artwork and fanart_tv
    # should still be called to warm the cache
    called_sources = [call.args[0] for call in mock_try.call_args_list]
    assert "dj_artwork" in called_sources
    assert "fanart_tv" in called_sources


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


# --- FanartOperation stores MBID and URLs on MediaFile ---


def test_fanart_op_stores_mbid_on_mediafile(tmp_path):
    """FanartOperation stores the resolved MBID on the MediaFile."""
    config = Config({
        **DEFAULT_CONFIG,
        "fanart": {"enabled": True, "project_api_key": "test-key"},
    })
    lib = tmp_path / "lib"
    lib.mkdir()
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(artist="Hardwell")

    mock_cache = MagicMock()
    mock_cache.has.return_value = False
    mock_cache.get.side_effect = KeyError

    with patch("festival_organizer.fanart.download_artist_images", return_value=(True, True)):
        with patch("festival_organizer.fanart.lookup_mbid", return_value="mbid-abc-123"):
            with patch("festival_organizer.fanart.fetch_artist_images", return_value=None):
                op = FanartOperation(config, lib)
                op._cache = mock_cache
                result = op.execute(video, mf)

    assert mf.mbid == "mbid-abc-123"


def test_fanart_op_stores_urls_on_mediafile(tmp_path):
    """FanartOperation stores fanart and clearlogo URLs on MediaFile."""
    config = Config({
        **DEFAULT_CONFIG,
        "fanart": {"enabled": True, "project_api_key": "test-key"},
    })
    lib = tmp_path / "lib"
    lib.mkdir()
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(artist="Hardwell")

    mock_cache = MagicMock()
    mock_cache.has.return_value = False

    with patch("festival_organizer.fanart.download_artist_images", return_value=(True, True)):
        with patch("festival_organizer.fanart.lookup_mbid", return_value="mbid-123"):
            with patch("festival_organizer.fanart.fetch_artist_images") as mock_fetch:
                mock_fetch.return_value = {
                    "hdmusiclogo": [{"url": "https://fanart.tv/logo.png", "likes": "5", "lang": "en"}],
                    "artistbackground": [{"url": "https://fanart.tv/bg.jpg", "likes": "3"}],
                }
                op = FanartOperation(config, lib)
                op._cache = mock_cache
                result = op.execute(video, mf)

    assert mf.fanart_url == "https://fanart.tv/bg.jpg"
    assert mf.clearlogo_url == "https://fanart.tv/logo.png"


def test_artist_dir_uses_global_cache(tmp_path):
    """Artist artwork directory resolves under ~/.cratedigger/, not library root."""
    lib = tmp_path / "lib"
    lib.mkdir()
    global_home = tmp_path / "home"
    global_home.mkdir()

    config = Config({
        **DEFAULT_CONFIG,
        "fanart": {"enabled": True, "project_api_key": "test-key"},
    })
    op = FanartOperation(config, lib)
    with patch("festival_organizer.operations.Path.home", return_value=global_home):
        result = op._artist_dir("Tiesto")

    assert str(global_home) in str(result)
    assert str(lib) not in str(result)
    assert result == global_home / ".cratedigger" / "artists" / "Tiesto"


def test_safe_artist_dir_sanitizes_name():
    """_safe_artist_dir sanitizes special characters and resolves to global cache."""
    from festival_organizer.operations import _safe_artist_dir

    result = _safe_artist_dir("Tiesto")
    assert result == Path.home() / ".cratedigger" / "artists" / "Tiesto"

    result = _safe_artist_dir("Armin van Buuren")
    assert result == Path.home() / ".cratedigger" / "artists" / "Armin van Buuren"

    # Special chars replaced with underscore
    result = _safe_artist_dir("Artist/Name")
    assert "Artist_Name" in str(result)


# --- AlbumPosterOperation DJ artwork fallback via tracklist URL ---


def test_album_poster_dj_artwork_fallback_from_tracklist(tmp_path):
    """When dj_artwork_url is empty but tracklists_url exists, fetch DJ artwork from tracklist page."""
    config = Config({
        **DEFAULT_CONFIG,
        "tracklists": {"email": "test@test.com", "password": "pw"},
    })
    lib = tmp_path / "lib"
    lib.mkdir()

    folder = tmp_path / "artist"
    folder.mkdir()
    video = folder / "set.mkv"
    video.write_bytes(b"")

    # MediaFile with tracklists_url but no dj_artwork_url
    mf = _make_mf(tracklists_url="https://www.1001tracklists.com/tracklist/abc123/", dj_artwork_url="")

    op = AlbumPosterOperation(config=config, library_root=lib)

    mock_resp = MagicMock()
    mock_resp.text = '<a href="/dj/martingarrix/">MG</a>'

    # Mock analyse_file to return our mf (with tracklists_url, no dj_artwork_url)
    with patch("festival_organizer.analyzer.analyse_file", return_value=mf):
        with patch("festival_organizer.tracklists.api.TracklistSession") as MockSession:
            api_instance = MockSession.return_value
            api_instance.login.return_value = None
            api_instance._request.return_value = mock_resp
            api_instance._fetch_dj_profile.return_value = {"artwork_url": "https://cdn.1001tracklists.com/images/dj/martingarrix.jpg", "aliases": [], "member_of": []}
            with patch.object(op, "_download_dj_artwork", return_value=Path("/tmp/cached.jpg")):
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

    mf = _make_mf(tracklists_url="https://www.1001tracklists.com/tracklist/abc123/", dj_artwork_url="")

    op = AlbumPosterOperation(config=config, library_root=lib)

    # Mock analyse_file to return our mf
    with patch("festival_organizer.analyzer.analyse_file", return_value=mf):
        result = op._find_dj_artwork(folder)

    # Should return None (no credentials, no dj_artwork_url)
    assert result is None


# --- Curated logo tests ---

def test_find_curated_logo_library_level(tmp_path):
    """Curated logo found at library .cratedigger/festivals/{Name}/logo.png."""
    config = Config(DEFAULT_CONFIG)
    config._data["festival_aliases"] = {"Tomorrowland": ["TML", "Tomorrowland Belgium"]}
    lib = tmp_path / "lib"
    logo_dir = lib / ".cratedigger" / "festivals" / "Tomorrowland"
    logo_dir.mkdir(parents=True)
    logo_file = logo_dir / "logo.png"
    logo_file.write_bytes(b"\x89PNG")

    op = AlbumPosterOperation(config=config, library_root=lib)
    result = op._find_curated_logo("Tomorrowland")
    assert result == logo_file


def test_find_curated_logo_alias_resolution(tmp_path):
    """Alias resolves to canonical name for logo lookup."""
    config = Config(DEFAULT_CONFIG)
    config._data["festival_aliases"] = {"Tomorrowland": ["TML"]}
    lib = tmp_path / "lib"
    logo_dir = lib / ".cratedigger" / "festivals" / "Tomorrowland"
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


def test_find_curated_logo_empty_festival(tmp_path):
    """Returns None for empty festival name."""
    config = Config(DEFAULT_CONFIG)
    op = AlbumPosterOperation(config=config, library_root=tmp_path)
    assert op._find_curated_logo("") is None


def test_try_background_source_curated_logo(tmp_path):
    """curated_logo source calls _find_curated_logo with festival name."""
    config = Config(DEFAULT_CONFIG)
    config._data["festival_aliases"] = {"AMF": ["AMF"]}
    lib = tmp_path / "lib"
    logo_dir = lib / ".cratedigger" / "festivals" / "AMF"
    logo_dir.mkdir(parents=True)
    logo_file = logo_dir / "logo.webp"
    logo_file.write_bytes(b"RIFF")

    op = AlbumPosterOperation(config=config, library_root=lib)
    mf = _make_mf(festival="AMF")
    result = op._try_background_source("curated_logo", tmp_path, mf)
    assert result == logo_file


def test_logo_summary_tracks_hits_and_misses(tmp_path):
    """logo_summary reports used logos and missing ones."""
    config = Config(DEFAULT_CONFIG)
    config._data["festival_aliases"] = {"AMF": ["AMF"], "TML": ["TML"]}
    lib = tmp_path / "lib"
    logo_dir = lib / ".cratedigger" / "festivals" / "AMF"
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
    with patch("festival_organizer.operations.Path.home", return_value=tmp_path):
        with patch("festival_organizer.operations.requests.get", return_value=mock_resp):
            result = op._download_artwork("https://example.com/big.jpg", "test-art", max_width=600)

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
    with patch("festival_organizer.operations.Path.home", return_value=tmp_path):
        with patch("festival_organizer.operations.requests.get", return_value=mock_resp):
            result = op._download_artwork("https://example.com/big.jpg", "test-art")

    assert result is not None
    with Image.open(result) as saved:
        assert saved.width == 800


def test_download_artwork_uses_global_cache(tmp_path):
    """Downloaded artwork is cached under ~/.cratedigger/, not library root."""
    from PIL import Image
    import io

    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    mock_resp = MagicMock()
    mock_resp.content = image_bytes
    mock_resp.raise_for_status = MagicMock()

    global_home = tmp_path / "home"
    global_home.mkdir()
    lib = tmp_path / "lib"
    lib.mkdir()

    op = AlbumPosterOperation(config=Config(DEFAULT_CONFIG), library_root=lib)
    with patch("festival_organizer.operations.Path.home", return_value=global_home):
        with patch("festival_organizer.operations.requests.get", return_value=mock_resp):
            result = op._download_artwork("https://example.com/photo.jpg", "dj-artwork")

    assert result is not None
    # Cached under global home, not library root
    assert str(global_home) in str(result)
    assert str(lib) not in str(result)
    assert (global_home / ".cratedigger" / "dj-artwork").exists()


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

    global_home = tmp_path / "home"
    global_home.mkdir()

    op = AlbumPosterOperation(config=Config(DEFAULT_CONFIG), library_root=tmp_path)
    with patch("festival_organizer.operations.Path.home", return_value=global_home):
        with patch("festival_organizer.operations.requests.get", return_value=mock_resp):
            result = op._download_dj_artwork("https://example.com/photo.png", "Tiesto")

    assert result is not None
    assert result.name == "dj-artwork.jpg"
    assert "Tiesto" in str(result)
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

    global_home = tmp_path / "home"
    global_home.mkdir()

    op = AlbumPosterOperation(config=Config(DEFAULT_CONFIG), library_root=tmp_path)
    with patch("festival_organizer.operations.Path.home", return_value=global_home):
        with patch("festival_organizer.operations.requests.get", return_value=mock_resp):
            result = op._download_dj_artwork("https://example.com/big.jpg", "Tiesto")

    assert result is not None
    with Image.open(result) as saved:
        assert saved.width == 550
        assert saved.height == 550


def test_download_dj_artwork_returns_cached(tmp_path):
    """DJ artwork returns cached file if fresh."""
    from PIL import Image
    import io

    global_home = tmp_path / "home"
    global_home.mkdir()

    artist_dir = global_home / ".cratedigger" / "artists" / "Tiesto"
    artist_dir.mkdir(parents=True)
    cached = artist_dir / "dj-artwork.jpg"
    # Write a valid tiny JPEG
    img = Image.new("RGB", (10, 10), color="red")
    img.save(cached, "JPEG")

    op = AlbumPosterOperation(config=Config(DEFAULT_CONFIG), library_root=tmp_path)
    with patch("festival_organizer.operations.Path.home", return_value=global_home):
        result = op._download_dj_artwork("https://example.com/photo.jpg", "Tiesto")

    assert result == cached
