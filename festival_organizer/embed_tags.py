"""Plex tag embedding via mkvpropedit (opt-in via --embed-tags flag).

Embeds artist, title, and date into MKV file tags so Plex can read them.
Only operates on destination files — never modifies source collection.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from festival_organizer.models import MediaFile


def find_mkvpropedit() -> str | None:
    """Locate mkvpropedit executable."""
    found = shutil.which("mkvpropedit")
    if found:
        return found
    for candidate in [
        r"C:\Program Files\MKVToolNix\mkvpropedit.exe",
        r"C:\Program Files (x86)\MKVToolNix\mkvpropedit.exe",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


MKVPROPEDIT_PATH = find_mkvpropedit()


def embed_tags(media_file: MediaFile, target_path: Path) -> bool:
    """Embed metadata tags into an MKV file via mkvpropedit.

    Args:
        media_file: MediaFile with metadata to embed
        target_path: Path to the MKV file to modify (must be the destination, not source)

    Returns:
        True if successful, False otherwise
    """
    if not MKVPROPEDIT_PATH:
        return False

    if not target_path.exists() or target_path.suffix.lower() != ".mkv":
        return False

    # Build tag XML
    tag_xml = _build_tag_xml(media_file)

    try:
        # Write tag XML to a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(tag_xml)
            tag_file = f.name

        # Run mkvpropedit
        result = subprocess.run(
            [MKVPROPEDIT_PATH, str(target_path), "--tags", f"global:{tag_file}"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )

        return result.returncode == 0

    except Exception:
        return False
    finally:
        try:
            os.unlink(tag_file)
        except Exception:
            pass


def _build_tag_xml(media_file: MediaFile) -> str:
    """Build MKV tag XML for embedding."""
    tags = []

    if media_file.artist:
        tags.append(f'    <Simple><Name>ARTIST</Name><String>{_xml_escape(media_file.artist)}</String></Simple>')

    title = media_file.title or media_file.set_title or ""
    if media_file.festival:
        title = f"{media_file.festival} {media_file.year}".strip()
    if title:
        tags.append(f'    <Simple><Name>TITLE</Name><String>{_xml_escape(title)}</String></Simple>')

    date = media_file.date or media_file.year
    if date:
        tags.append(f'    <Simple><Name>DATE_RELEASED</Name><String>{_xml_escape(date)}</String></Simple>')

    tags_str = "\n".join(tags)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Tags>
  <Tag>
    <Targets>
      <TargetTypeValue>50</TargetTypeValue>
    </Targets>
{tags_str}
  </Tag>
</Tags>
"""


def _xml_escape(text: str) -> str:
    """Escape XML special characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))
