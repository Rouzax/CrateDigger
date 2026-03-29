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
