"""Test that --generate-nfo and --extract-art work for files already at target."""
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from festival_organizer.models import FileAction, MediaFile


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


def test_execute_generates_nfo_for_skipped_file():
    """When a file is already at target, --generate-nfo should still create an NFO."""
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "Artist" / "2024 - AMF - Martin Garrix.mkv"
        video.parent.mkdir(parents=True)
        video.write_text("fake video")

        mf = _make_media_file(video)
        action = FileAction(
            source=video,
            target=video,  # same path = will be skipped
            media_file=mf,
            action="move",
            generate_nfo=True,
            extract_art=False,
        )

        from festival_organizer.executor import execute_actions
        execute_actions([action])
        assert action.status == "skipped"

        # Now simulate what CLI does post-execution
        from festival_organizer.cli import _run_post_processing
        from festival_organizer.config import Config, DEFAULT_CONFIG
        config = Config(DEFAULT_CONFIG)

        _run_post_processing(action, config)

        nfo_path = video.with_suffix(".nfo")
        assert nfo_path.exists(), "NFO should be generated for skipped file"


def test_execute_extracts_art_for_skipped_file():
    """When a file is already at target, --extract-art should still attempt extraction."""
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "Artist" / "2024 - AMF - Martin Garrix.mkv"
        video.parent.mkdir(parents=True)
        video.write_text("fake video")

        mf = _make_media_file(video)
        action = FileAction(
            source=video,
            target=video,
            media_file=mf,
            action="move",
            generate_nfo=False,
            extract_art=True,
        )

        from festival_organizer.executor import execute_actions
        execute_actions([action])

        from festival_organizer.cli import _run_post_processing
        from festival_organizer.config import Config, DEFAULT_CONFIG
        config = Config(DEFAULT_CONFIG)

        with patch("festival_organizer.cli.extract_cover") as mock_extract:
            mock_extract.return_value = video.parent / "poster.png"
            _run_post_processing(action, config)
            mock_extract.assert_called_once_with(video, video.parent)


def test_no_post_processing_for_errored_file():
    """Errored files should NOT get post-processing."""
    action = FileAction(
        source=Path("C:/nonexistent.mkv"),
        target=Path("C:/out.mkv"),
        media_file=MediaFile(source_path=Path("C:/nonexistent.mkv")),
        action="move",
        status="error",
        error="file not found",
        generate_nfo=True,
        extract_art=True,
    )

    from festival_organizer.cli import _run_post_processing
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config(DEFAULT_CONFIG)

    with patch("festival_organizer.cli.generate_nfo") as mock_nfo:
        with patch("festival_organizer.cli.extract_cover") as mock_art:
            _run_post_processing(action, config)
            mock_nfo.assert_not_called()
            mock_art.assert_not_called()
