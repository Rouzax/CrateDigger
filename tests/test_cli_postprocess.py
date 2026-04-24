"""Test that operations handle enrichment for files already at target.

These tests replace the old _run_post_processing tests.
The individual operation gap detection and execution are covered in test_operations.py.
These tests verify the operations work correctly in pipeline context.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch

from festival_organizer.config import load_config
from festival_organizer.models import MediaFile
from festival_organizer.operations import (
    NfoOperation, ArtOperation, PosterOperation, TagsOperation,
)


def _make_media_file(path: Path) -> MediaFile:
    return MediaFile(
        source_path=path,
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        content_type="festival_set",
        extension=".mkv",
        has_cover=True,
    )


def test_nfo_operation_generates_for_existing_file():
    """NFO operation generates NFO for a file already in place."""
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "2024 - AMF - Martin Garrix.mkv"
        video.write_text("fake video")
        mf = _make_media_file(video)
        config = load_config()

        op = NfoOperation(config)
        assert op.is_needed(video, mf) is True
        result = op.execute(video, mf)
        assert result.status == "done"
        assert video.with_suffix(".nfo").exists()


def test_nfo_operation_skipped_when_exists():
    """NFO operation skipped when .nfo already exists."""
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "test.mkv"
        video.write_text("fake video")
        video.with_suffix(".nfo").write_text("<musicvideo/>")
        mf = _make_media_file(video)
        config = load_config()

        op = NfoOperation(config)
        assert op.is_needed(video, mf) is False


def test_art_operation_called_without_has_cover_gate():
    """Art extraction is attempted regardless of has_cover flag."""
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "test.mkv"
        video.write_text("fake video")
        mf = _make_media_file(video)
        mf.has_cover = False  # No cover, but should still try

        op = ArtOperation()
        assert op.is_needed(video, mf) is True

        with patch("festival_organizer.artwork.extract_cover") as mock_extract:
            mock_extract.return_value = video.parent / f"{video.stem}-thumb.jpg"
            op.execute(video, mf)
            mock_extract.assert_called_once_with(video, video.parent)


def test_poster_operation_not_called_when_no_thumb():
    """Poster operation skipped when no thumb available."""
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "test.mkv"
        video.write_text("fake video")
        mf = _make_media_file(video)
        config = load_config()

        op = PosterOperation(config)
        assert op.is_needed(video, mf) is False


def test_tags_operation_skipped_for_non_mkv():
    """Tags operation skipped for non-MKV files."""
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "test.mp4"
        video.write_text("fake video")
        mf = _make_media_file(video)

        op = TagsOperation()
        assert op.is_needed(video, mf) is False
