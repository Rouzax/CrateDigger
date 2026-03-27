"""Cover art extraction from MKV attachments + frame sampling fallback."""
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

from PIL import Image

from festival_organizer import metadata


def extract_cover(source: Path, target_dir: Path) -> Path | None:
    """Extract cover art from an MKV file, with frame sampling fallback.

    Priority:
    1. Extract embedded MKV attachment via mkvextract
    2. Fallback: smart-sample a video frame via frame_sampler

    Saves as {source.stem}-thumb.jpg in the target directory.
    Returns the path to the thumb file, or None on failure.
    """
    thumb_path = target_dir / f"{source.stem}-thumb.jpg"

    # Skip if thumb already exists
    if thumb_path.exists():
        return thumb_path

    # 1. Try mkvextract
    if _extract_mkvattachment(source, thumb_path):
        return thumb_path

    # 2. Fallback: sample best frame from video
    if _sample_frame_fallback(source, thumb_path):
        return thumb_path

    return None


def _extract_mkvattachment(source: Path, thumb_path: Path) -> bool:
    """Extract first MKV attachment and save as thumb JPG."""
    if not metadata.MKVEXTRACT_PATH:
        return False

    # Extract to temp file first (mkvextract saves in original format)
    temp_path = thumb_path.with_suffix(".tmp.png")

    try:
        result = subprocess.run(
            [metadata.MKVEXTRACT_PATH, str(source), "attachments", f"1:{temp_path}"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0 or not temp_path.exists():
            return False

        # Convert to JPG
        with Image.open(temp_path) as img:
            img.convert("RGB").save(str(thumb_path), "JPEG", quality=95)

        return thumb_path.exists()

    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("MKV attachment extraction failed for %s: %s", source, e)
        return False
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _sample_frame_fallback(source: Path, thumb_path: Path) -> bool:
    """Sample best frame from video and save as thumb JPG."""
    try:
        from festival_organizer.frame_sampler import sample_best_frame
        frame_path = sample_best_frame(source)
        if not frame_path or not frame_path.exists():
            return False

        # Convert sampled PNG to JPG thumb
        with Image.open(frame_path) as img:
            img.convert("RGB").save(str(thumb_path), "JPEG", quality=95)

        # Clean up the .frame.png
        frame_path.unlink(missing_ok=True)
        return thumb_path.exists()

    except ImportError:
        return False
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Frame sampling failed for %s: %s", source, e)
        return False
