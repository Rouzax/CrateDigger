"""Tests for the frame_sampler module's logging of silent-None return paths."""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from festival_organizer.frame_sampler import _HAS_CV2, sample_best_frame


pytestmark = pytest.mark.skipif(not _HAS_CV2, reason="cv2/numpy not installed")


def test_sample_best_frame_warns_when_video_not_opened(tmp_path, caplog):
    """VideoCapture.isOpened() False => WARNING naming the video path."""
    video = tmp_path / "bad.mkv"
    video.write_bytes(b"")
    fake_cap = MagicMock()
    fake_cap.isOpened.return_value = False
    with patch("festival_organizer.frame_sampler.cv2.VideoCapture", return_value=fake_cap):
        with caplog.at_level(logging.WARNING, logger="festival_organizer.frame_sampler"):
            result = sample_best_frame(video)
    assert result is None
    joined = "\n".join(r.message for r in caplog.records)
    assert "could not open" in joined.lower()
    assert "bad.mkv" in joined


def test_sample_best_frame_warns_when_video_too_short(tmp_path, caplog):
    """Videos with too few frames or fps <= 0 => WARNING naming the reason."""
    video = tmp_path / "short.mkv"
    video.write_bytes(b"")
    fake_cap = MagicMock()
    fake_cap.isOpened.return_value = True

    def _get(prop):
        import cv2
        if prop == cv2.CAP_PROP_FPS:
            return 25.0
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return 3
        return 0
    fake_cap.get.side_effect = _get
    with patch("festival_organizer.frame_sampler.cv2.VideoCapture", return_value=fake_cap):
        with caplog.at_level(logging.WARNING, logger="festival_organizer.frame_sampler"):
            result = sample_best_frame(video)
    assert result is None
    joined = "\n".join(r.message for r in caplog.records)
    assert "short.mkv" in joined
    assert "too short" in joined.lower() or "insufficient" in joined.lower() or "3" in joined


def test_sample_best_frame_warns_when_no_best_frame(tmp_path, caplog):
    """When every sampled frame fails to read, the caller logs WARNING
    and returns None rather than saving nothing."""
    video = tmp_path / "unreadable.mkv"
    video.write_bytes(b"")
    fake_cap = MagicMock()
    fake_cap.isOpened.return_value = True

    def _get(prop):
        import cv2
        if prop == cv2.CAP_PROP_FPS:
            return 25.0
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return 1000
        return 0
    fake_cap.get.side_effect = _get
    fake_cap.read.return_value = (False, None)  # every sample fails
    with patch("festival_organizer.frame_sampler.cv2.VideoCapture", return_value=fake_cap):
        with caplog.at_level(logging.WARNING, logger="festival_organizer.frame_sampler"):
            result = sample_best_frame(video)
    assert result is None
    joined = "\n".join(r.message for r in caplog.records)
    assert "unreadable.mkv" in joined
    assert "no" in joined.lower() and "frame" in joined.lower()
