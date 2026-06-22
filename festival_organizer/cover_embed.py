"""Cover-attachment convergence policy.

Target invariant per MKV: one portrait `cover.jpg` (the set poster) and one
landscape `cover_land.<ext>` (the original YouTube thumbnail). The landscape is
always preserved as cover_land BEFORE the primary cover slot is overwritten, so the
original thumb is never lost.

Logging:
    Logger: 'festival_organizer.cover_embed'
    Key events:
        - cover.preserve (INFO): landscape preserved as cover_land
        - cover.land_missing (WARNING): no landscape source available
"""

import logging
import tempfile
from pathlib import Path

from festival_organizer.mkv_attachments import (
    IMAGE_MIME,
    add_attachment,
    delete_attachment,
    extract_attachment,
    image_ratio_class,
    list_image_attachments,
    replace_attachment,
)

logger = logging.getLogger(__name__)


def ensure_cover_land(target: Path, atts: list[dict], thumb_path: Path) -> bool:
    """Guarantee a cover_land.* (landscape) attachment exists, preserving original bytes.

    Returns True if cover_land is present or was successfully added, False otherwise.
    """
    if any(a["file_name"].lower().startswith("cover_land") for a in atts):
        return True  # already preserved

    # Find a landscape image currently in a cover.* slot (the un-processed YT thumb).
    for a in atts:
        name = a["file_name"]
        lname = name.lower()
        if not lname.startswith("cover.") or lname.startswith("cover_land"):
            continue
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / name
            if not extract_attachment(target, a["id"], tmp):
                continue
            if image_ratio_class(tmp) != "landscape":
                continue  # this cover.* is our portrait poster, not the thumb
            ext = Path(name).suffix.lower() or ".png"
            mime = a["content_type"] or IMAGE_MIME.get(ext, "image/png")
            if add_attachment(target, tmp, f"cover_land{ext}", mime):
                logger.info("cover.preserve: file=%s from=%s", target.name, name)
                return True
            logger.warning("cover.land_missing: file=%s reason=add_failed", target.name)
            return False

    # No embedded landscape: recover from the on-disk thumb (always landscape).
    if thumb_path.exists():
        if add_attachment(target, thumb_path, "cover_land.jpg", "image/jpeg"):
            logger.info("cover.preserve: file=%s from=thumb", target.name)
            return True
        logger.warning("cover.land_missing: file=%s reason=add_failed", target.name)
        return False

    logger.warning(
        "cover.land_missing: file=%s reason=no_landscape_source", target.name
    )
    return False


def set_primary_cover(target: Path, poster_path: Path, atts: list[dict]) -> bool:
    """Write the portrait poster as cover.jpg, replacing any existing cover.* slot."""
    names = {a["file_name"] for a in atts}
    if "cover.jpg" in names:
        return replace_attachment(
            target, "cover.jpg", poster_path, "cover.jpg", "image/jpeg"
        )
    if "cover.png" in names:
        return replace_attachment(
            target, "cover.png", poster_path, "cover.jpg", "image/jpeg"
        )
    return add_attachment(target, poster_path, "cover.jpg", "image/jpeg")


def converge_cover_attachments(
    target: Path, poster_path: Path, thumb_path: Path
) -> bool:
    """Converge the MKV to {cover.jpg = portrait poster, cover_land.<ext> = landscape}.

    Order matters: the landscape is preserved as cover_land BEFORE the cover slot is
    overwritten. Returns False (without overwriting) if the landscape cannot be
    preserved, so the original thumb is never lost. Returns True on full success.
    """
    atts = list_image_attachments(target)
    if not ensure_cover_land(target, atts, thumb_path):
        logger.warning(
            "cover.skip: file=%s reason=landscape_not_preserved", target.name
        )
        return False
    atts = list_image_attachments(target)  # refresh after the add
    if not set_primary_cover(target, poster_path, atts):
        logger.warning("cover.skip: file=%s reason=cover_write_failed", target.name)
        return False
    # Defensive: a stray cover.png alongside cover_land would double the landscape.
    atts = list_image_attachments(target)
    has_land = any(a["file_name"].lower().startswith("cover_land") for a in atts)
    if has_land and any(a["file_name"] == "cover.png" for a in atts):
        delete_attachment(target, "cover.png")
    return True
