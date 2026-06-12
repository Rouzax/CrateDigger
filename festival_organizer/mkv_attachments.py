"""List, extract, and write MKV image attachments via MKVToolNix.

Mechanism only (no cover policy; see cover_embed.py).

Logging:
    Logger: 'festival_organizer.mkv_attachments'
    Key events:
        - attachments.list (DEBUG): mkvmerge identify failed
        - attachments.extract (DEBUG): mkvextract failed
        - attachments.write (DEBUG): mkvpropedit add/replace/delete failed
"""
import json
import logging
import subprocess
from pathlib import Path

from PIL import Image

from festival_organizer import metadata
from festival_organizer.subprocess_utils import tracked_run

logger = logging.getLogger(__name__)

IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
_IMAGE_EXTS = tuple(IMAGE_MIME.keys())


def classify_ratio(width: int, height: int) -> str:
    """Classify an image aspect ratio: landscape, portrait, square, or unknown."""
    if not width or not height:
        return "unknown"
    if width >= height * 1.1:
        return "landscape"
    if height >= width * 1.1:
        return "portrait"
    return "square"


def image_ratio_class(path: Path) -> str:
    """Return classify_ratio for an image file, or 'unknown' if unreadable."""
    try:
        with Image.open(path) as im:
            w, h = im.size
    except (OSError, ValueError):
        return "unknown"
    return classify_ratio(w, h)


def list_image_attachments(source: Path) -> list[dict]:
    """Return image attachments as [{'id', 'file_name', 'content_type'}]."""
    if not metadata.MKVMERGE_PATH:
        return []
    try:
        result = tracked_run(
            [metadata.MKVMERGE_PATH, "-i", "-F", "json", str(source)],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout or "{}")
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as e:
        logger.debug("attachments.list: status=failed source=%s error=\"%s\"", source, e)
        return []
    out: list[dict] = []
    for a in data.get("attachments", []):
        ct = (a.get("content_type") or "").lower()
        fn = a.get("file_name") or ""
        if ct.startswith("image/") or fn.lower().endswith(_IMAGE_EXTS):
            out.append({"id": a.get("id"), "file_name": fn, "content_type": a.get("content_type") or ""})
    return out


def extract_attachment(source: Path, att_id: int, dest: Path) -> bool:
    """Extract one attachment by id to dest."""
    if not metadata.MKVEXTRACT_PATH:
        return False
    try:
        result = tracked_run(
            [metadata.MKVEXTRACT_PATH, str(source), "attachments", f"{att_id}:{dest}"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        return result.returncode == 0 and Path(dest).exists()
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("attachments.extract: status=failed source=%s id=%s error=\"%s\"", source, att_id, e)
        return False


def add_attachment(target: Path, data_path: Path, name: str, mime: str) -> bool:
    """Add a new attachment with the given name and mime type."""
    return _run_propedit(
        target,
        ["--attachment-name", name, "--attachment-mime-type", mime, "--add-attachment", str(data_path)],
    )


def replace_attachment(target: Path, old_name: str, data_path: Path, new_name: str, mime: str) -> bool:
    """Replace the attachment named old_name with data_path, renaming it to new_name."""
    return _run_propedit(
        target,
        ["--attachment-name", new_name, "--attachment-mime-type", mime,
         "--replace-attachment", f"name:{old_name}:{data_path}"],
    )


def delete_attachment(target: Path, name: str) -> bool:
    """Delete the attachment named name."""
    return _run_propedit(target, ["--delete-attachment", f"name:{name}"])


def _run_propedit(target: Path, args: list[str]) -> bool:
    if not metadata.MKVPROPEDIT_PATH:
        return False
    try:
        result = tracked_run(
            [metadata.MKVPROPEDIT_PATH, str(target), *args],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("attachments.write: status=failed target=%s error=\"%s\"", target.name, e)
        return False
