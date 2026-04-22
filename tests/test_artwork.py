import logging
import subprocess as subprocess_mod
from pathlib import Path
from unittest.mock import patch, MagicMock
from festival_organizer.artwork import extract_cover
from festival_organizer.metadata import find_tool


def test_find_mkvextract():
    with patch("shutil.which", return_value="/usr/bin/mkvextract"):
        result = find_tool("mkvextract")
        assert result is not None
        assert "mkvextract" in result.lower()


def test_find_mkvextract_not_installed():
    with patch("shutil.which", return_value=None):
        assert find_tool("mkvextract") is None


def test_extract_cover_no_tool(tmp_path):
    """Returns None only when all three tiers fail."""
    source = tmp_path / "source.mkv"
    source.touch()
    with patch("festival_organizer.metadata.MKVEXTRACT_PATH", None):
        with patch("festival_organizer.artwork._sample_frame_fallback", return_value=False):
            with patch("festival_organizer.artwork._gradient_thumb_fallback", return_value=False):
                result = extract_cover(source, tmp_path)
                assert result is None


def test_extract_cover_success(tmp_path):
    """Should call mkvextract and return thumb path on success."""
    source = tmp_path / "source.mkv"
    source.touch()
    target_dir = tmp_path / "output"
    target_dir.mkdir()

    thumb_path = target_dir / "source-thumb.jpg"

    mock_result = MagicMock()
    mock_result.returncode = 0

    mock_img = MagicMock()
    mock_img.__enter__ = MagicMock(return_value=mock_img)
    mock_img.__exit__ = MagicMock(return_value=False)
    mock_img.convert.return_value = mock_img

    def fake_subprocess_run(*args, **kwargs):
        # Simulate mkvextract creating the temp file
        temp_path = thumb_path.with_suffix(".tmp.png")
        temp_path.touch()
        return mock_result

    def fake_img_save(path, fmt, **kwargs):
        Path(path).touch()

    mock_img.save = fake_img_save

    with patch("festival_organizer.metadata.MKVEXTRACT_PATH", "mkvextract"):
        with patch("subprocess.run", side_effect=fake_subprocess_run) as mock_run:
            with patch("festival_organizer.artwork.Image.open", return_value=mock_img):
                result = extract_cover(source, target_dir)
                assert result == thumb_path
                mock_run.assert_called_once()


def test_extract_cover_no_attachment(tmp_path):
    """Should fall through to frame_sampler when mkvextract produces no file."""
    source = tmp_path / "source.mkv"
    source.touch()
    target_dir = tmp_path / "output"
    target_dir.mkdir()

    mock_result = MagicMock()
    mock_result.returncode = 1

    with patch("festival_organizer.metadata.MKVEXTRACT_PATH", "mkvextract"):
        with patch("subprocess.run", return_value=mock_result):
            with patch("festival_organizer.artwork._sample_frame_fallback", return_value=False):
                with patch("festival_organizer.artwork._gradient_thumb_fallback", return_value=False):
                    result = extract_cover(source, target_dir)
                    assert result is None


def test_extract_cover_frame_sampler_fallback(tmp_path):
    """Should use frame_sampler when mkvextract fails, via lazy import patch."""
    source = tmp_path / "source.mkv"
    source.touch()
    target_dir = tmp_path / "output"
    target_dir.mkdir()

    thumb_path = target_dir / "source-thumb.jpg"

    mock_result = MagicMock()
    mock_result.returncode = 1  # mkvextract fails

    # Fake frame PNG that sample_best_frame "creates"
    fake_frame = tmp_path / "source.mkv.frame.png"
    fake_frame.touch()

    mock_img = MagicMock()
    mock_img.__enter__ = MagicMock(return_value=mock_img)
    mock_img.__exit__ = MagicMock(return_value=False)
    mock_img.convert.return_value = mock_img

    def fake_img_save(path, fmt, **kwargs):
        Path(path).touch()

    mock_img.save = fake_img_save

    # sample_best_frame is imported lazily inside _sample_frame_fallback;
    # patch it at the module where it lives.
    with patch("festival_organizer.metadata.MKVEXTRACT_PATH", "mkvextract"):
        with patch("subprocess.run", return_value=mock_result):
            with patch(
                "festival_organizer.frame_sampler.sample_best_frame",
                return_value=fake_frame,
            ):
                with patch("festival_organizer.artwork.Image.open", return_value=mock_img):
                    result = extract_cover(source, target_dir)
                    assert result == thumb_path


def test_extract_cover_frame_sampler_fallback_direct(tmp_path):
    """Frame sampler fallback: mkvextract fails, _sample_frame_fallback succeeds."""
    source = tmp_path / "source.mkv"
    source.touch()
    target_dir = tmp_path / "output"
    target_dir.mkdir()

    thumb_path = target_dir / "source-thumb.jpg"

    mock_result = MagicMock()
    mock_result.returncode = 1  # mkvextract fails

    def fake_sample_frame_fallback(src, tgt):
        # Simulate the fallback creating the thumb
        tgt.touch()
        return True

    with patch("festival_organizer.metadata.MKVEXTRACT_PATH", "mkvextract"):
        with patch("subprocess.run", return_value=mock_result):
            with patch(
                "festival_organizer.artwork._sample_frame_fallback",
                side_effect=fake_sample_frame_fallback,
            ) as mock_fallback:
                result = extract_cover(source, target_dir)
                assert result == thumb_path
                mock_fallback.assert_called_once_with(source, thumb_path)


def test_mkvextract_failure_logged(tmp_path, caplog):
    """MKV extraction failure is logged at debug level."""
    from festival_organizer.artwork import _extract_mkvattachment

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    thumb = tmp_path / "test-thumb.jpg"

    with patch("festival_organizer.artwork.metadata.MKVEXTRACT_PATH", "/usr/bin/mkvextract"):
        with patch("festival_organizer.artwork.subprocess.run",
                   side_effect=subprocess_mod.SubprocessError("fail")):
            with caplog.at_level(logging.DEBUG, logger="festival_organizer.artwork"):
                result = _extract_mkvattachment(video, thumb)
    assert result is False
    assert "fail" in caplog.text


def test_extract_cover_gradient_fallback(tmp_path):
    """Tier 3 kicks in when both mkvextract and frame sampler fail; thumb is 1920x1080 JPEG."""
    from PIL import Image as PILImage

    source = tmp_path / "source.mkv"
    source.touch()
    target_dir = tmp_path / "output"
    target_dir.mkdir()
    thumb_path = target_dir / "source-thumb.jpg"

    with patch("festival_organizer.metadata.MKVEXTRACT_PATH", None):
        with patch("festival_organizer.artwork._sample_frame_fallback", return_value=False):
            result = extract_cover(source, target_dir)

    assert result == thumb_path
    assert thumb_path.exists()
    with PILImage.open(thumb_path) as img:
        assert img.size == (1920, 1080)
        assert img.format == "JPEG"


def test_gradient_thumb_fallback_handles_poster_error(tmp_path):
    """Gradient fallback returns False (not raise) on PIL errors."""
    from festival_organizer.artwork import _gradient_thumb_fallback

    thumb = tmp_path / "x-thumb.jpg"
    with patch("festival_organizer.poster._make_gradient_bg", side_effect=OSError("boom")):
        assert _gradient_thumb_fallback(thumb) is False
    assert not thumb.exists()


def test_extract_cover_skip_existing(tmp_path):
    """Should return immediately if thumb already exists."""
    source = tmp_path / "source.mkv"
    source.touch()
    target_dir = tmp_path / "output"
    target_dir.mkdir()

    thumb_path = target_dir / "source-thumb.jpg"
    thumb_path.touch()  # Pre-create the thumb

    with patch("festival_organizer.artwork._extract_mkvattachment") as mock_mkv:
        with patch("festival_organizer.artwork._sample_frame_fallback") as mock_frame:
            result = extract_cover(source, target_dir)
            assert result == thumb_path
            mock_mkv.assert_not_called()
            mock_frame.assert_not_called()
