"""Cover art extraction from MKV attachments + frame sampling fallback.

Logging:
    Logger: 'festival_organizer.artwork'
    Key events:
        - attachment.extract_error (DEBUG): MKV attachment extraction failed
        - frame.sample_error (DEBUG): Frame sampling via ffmpeg failed
    See docs/logging.md for full guidelines.
"""
import logging
import subprocess
from pathlib import Path

from PIL import Image

from festival_organizer import metadata
from festival_organizer.mkv_attachments import (
    extract_attachment,
    image_ratio_class,
    list_image_attachments,
)

logger = logging.getLogger(__name__)


def extract_cover(source: Path, target_dir: Path) -> Path | None:
    """Extract cover art from an MKV file, with frame sampling fallback.

    Priority:
    1. Extract embedded MKV attachment via mkvextract
    2. Fallback: smart-sample a video frame via frame_sampler
    3. Final fallback: write a plain gradient thumb so downstream poster
       generation still has something to work with. The gradient carries no
       text, so set-poster layout is identical to the normal path.

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

    # 3. Last resort: synthesise a gradient thumb
    if _gradient_thumb_fallback(thumb_path):
        return thumb_path

    return None


def _extract_mkvattachment(source: Path, thumb_path: Path) -> bool:
    """Extract the landscape thumbnail attachment and save it as the thumb JPG.

    Prefers cover_land.*, then any landscape cover.*; never a portrait cover.* (that
    is CrateDigger's own embedded poster, and using it would build a poster from a
    poster). Returns False if no landscape attachment is available.
    """
    if not metadata.MKVEXTRACT_PATH:
        return False

    atts = list_image_attachments(source)
    if not atts:
        return False

    # cover_land.* first, then everything else (so a landscape cover.* is tried too).
    ordered = sorted(atts, key=lambda a: 0 if a["file_name"].lower().startswith("cover_land") else 1)

    temp_path = thumb_path.with_suffix(".tmp.img")
    try:
        for a in ordered:
            if not extract_attachment(source, a["id"], temp_path):
                continue
            if image_ratio_class(temp_path) != "landscape":
                temp_path.unlink(missing_ok=True)
                continue
            with Image.open(temp_path) as img:
                img.convert("RGB").save(str(thumb_path), "JPEG", quality=95)
            return thumb_path.exists()
        return False
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("artwork.extract: status=failed source=%s error=\"%s\"", source, e)
        return False
    finally:
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
        logger.debug("artwork.frame_sample: status=failed source=%s error=\"%s\"", source, e)
        return False


def _gradient_thumb_fallback(thumb_path: Path) -> bool:
    """Write a 16:9 gradient-only thumb as last-resort fallback.

    The gradient carries no text or decoration; set-poster rendering stays
    identical to the normal path (only the upper sharp-image region differs).
    """
    try:
        from festival_organizer.poster import _make_gradient_bg
        # Neutral brand blue; deterministic across runs and files.
        base_color = (60, 90, 140)
        bg = _make_gradient_bg(base_color, width=1920, height=1080)
        bg.save(str(thumb_path), "JPEG", quality=95)
        return thumb_path.exists()
    except (OSError, ValueError) as e:
        logger.debug("artwork.gradient_fallback: status=failed path=%s error=\"%s\"", thumb_path, e)
        return False
