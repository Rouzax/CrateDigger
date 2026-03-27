"""Test that --generate-nfo, --extract-art, --generate-posters, and --embed-tags work for files already at target."""
import tempfile
from pathlib import Path
from unittest.mock import patch

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
    """When a file is already at target, --extract-art should attempt extraction without a has_cover gate."""
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

        thumb = video.parent / f"{video.stem}-thumb.jpg"
        with patch("festival_organizer.cli.extract_cover") as mock_extract:
            mock_extract.return_value = thumb
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


def test_post_processing_generates_poster_for_skipped_file():
    """When generate_posters=True and extract_art returns a thumb, generate_set_poster should be called."""
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
            status="skipped",
            generate_nfo=False,
            extract_art=True,
            generate_posters=True,
            embed_tags=False,
        )

        from festival_organizer.cli import _run_post_processing
        from festival_organizer.config import Config, DEFAULT_CONFIG
        config = Config(DEFAULT_CONFIG)

        thumb = video.parent / f"{video.stem}-thumb.jpg"
        with patch("festival_organizer.cli.extract_cover") as mock_extract, \
             patch("festival_organizer.cli.generate_set_poster") as mock_poster:
            mock_extract.return_value = thumb
            _run_post_processing(action, config)

            mock_extract.assert_called_once_with(video, video.parent)
            mock_poster.assert_called_once()
            call_kwargs = mock_poster.call_args.kwargs
            assert call_kwargs["source_image_path"] == thumb
            assert call_kwargs["artist"] == "Martin Garrix"
            assert call_kwargs["festival"] == "AMF"
            assert call_kwargs["year"] == "2024"


def test_post_processing_no_poster_when_extract_returns_none():
    """generate_set_poster should NOT be called if extract_cover returns None."""
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
            status="skipped",
            generate_nfo=False,
            extract_art=True,
            generate_posters=True,
            embed_tags=False,
        )

        from festival_organizer.cli import _run_post_processing
        from festival_organizer.config import Config, DEFAULT_CONFIG
        config = Config(DEFAULT_CONFIG)

        with patch("festival_organizer.cli.extract_cover") as mock_extract, \
             patch("festival_organizer.cli.generate_set_poster") as mock_poster:
            mock_extract.return_value = None
            _run_post_processing(action, config)

            mock_poster.assert_not_called()


def test_post_processing_embeds_tags_for_skipped_file():
    """When embed_tags=True, embed_tags_fn should be called with the media file and file path."""
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
            status="skipped",
            generate_nfo=False,
            extract_art=False,
            generate_posters=False,
            embed_tags=True,
        )

        from festival_organizer.cli import _run_post_processing
        from festival_organizer.config import Config, DEFAULT_CONFIG
        config = Config(DEFAULT_CONFIG)

        with patch("festival_organizer.cli.embed_tags_fn") as mock_embed:
            _run_post_processing(action, config)
            mock_embed.assert_called_once_with(mf, video)


def test_post_processing_embed_tags_not_called_for_errored_file():
    """embed_tags_fn should NOT be called when action status is error."""
    action = FileAction(
        source=Path("C:/nonexistent.mkv"),
        target=Path("C:/out.mkv"),
        media_file=MediaFile(source_path=Path("C:/nonexistent.mkv")),
        action="move",
        status="error",
        error="file not found",
        generate_nfo=False,
        extract_art=False,
        generate_posters=False,
        embed_tags=True,
    )

    from festival_organizer.cli import _run_post_processing
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config(DEFAULT_CONFIG)

    with patch("festival_organizer.cli.embed_tags_fn") as mock_embed:
        _run_post_processing(action, config)
        mock_embed.assert_not_called()
