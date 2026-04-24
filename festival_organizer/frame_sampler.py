"""Smart frame sampling from video files for poster art fallback.

Samples evenly-spaced frames, scores by vibrancy (brightness * saturation),
with soft bonuses for sharpness and exposure quality. Skips near-black frames.

Requires opencv-python-headless and numpy (optional dependencies).
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

logger = logging.getLogger(__name__)


def sample_best_frame(video_path: str | Path, num_samples: int = 50) -> Path | None:
    """Sample frames from a video and return the best one as a PNG.

    Opens the video, samples `num_samples` evenly-spaced frames (skipping
    first/last 5%), scores each by vibrancy, and saves the winner.

    Args:
        video_path: Path to the video file
        num_samples: Number of frames to sample (default 50)

    Returns:
        Path to the saved PNG frame, or None on failure
    """
    video_path = Path(video_path)

    if not _HAS_CV2:
        logger.debug("Frame sampler skipped: cv2/numpy not installed")
        return None

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning("Frame sampler could not open video %s", video_path)
        return None

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames < 10 or fps <= 0:
            logger.warning(
                "Frame sampler: %s too short or invalid (frames=%d fps=%s)",
                video_path, total_frames, fps,
            )
            return None

        # Skip first and last 5% (intros/outros are often black or title cards)
        start_f = int(total_frames * 0.05)
        end_f = int(total_frames * 0.95)
        sample_indices = np.linspace(start_f, end_f, num=num_samples, dtype=int)

        best_score = -1.0
        best_frame = None

        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok:
                continue

            score = _score_frame(frame)
            if score > best_score:
                best_score = score
                best_frame = frame

    finally:
        cap.release()

    if best_frame is None:
        logger.warning("Frame sampler: no readable frames in %s", video_path)
        return None

    # Save as PNG next to the video
    output_path = video_path.with_suffix(".frame.png")
    cv2.imwrite(str(output_path), best_frame)
    return output_path


def _score_frame(frame: np.ndarray) -> float:
    """Score a frame for visual impact.

    Combines vibrancy (brightness * saturation) with soft bonuses for
    sharpness and exposure quality.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h_ch, s_ch, v_ch = cv2.split(hsv)

    mean_sat = float(s_ch.mean())
    mean_val = float(v_ch.mean())

    # Core metric: brightness * saturation
    vibrancy = mean_sat * mean_val

    # Sharpness as a soft bonus
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    laplacian = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharp_bonus = math.log1p(laplacian) / 15.0

    # Exposure quality — gaussian around 0.45 brightness
    mean_brightness = gray.mean() / 255.0
    expo_quality = math.exp(-((mean_brightness - 0.45) ** 2) / (2 * 0.20 ** 2))

    # Penalize near-black frames
    if mean_brightness < 0.08:
        vibrancy = 0

    # Combined score
    return (
        0.60 * vibrancy / 20000.0 +
        0.15 * sharp_bonus +
        0.15 * expo_quality +
        0.10 * min(float(h_ch.astype(float).std()) / 50.0, 1.0)
    )
