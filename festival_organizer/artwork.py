"""Cover art extraction from MKV attachments via mkvextract."""
import subprocess
from pathlib import Path

from festival_organizer import metadata


def extract_cover(source: Path, target_dir: Path) -> Path | None:
    """Extract the first attachment (cover art) from an MKV file.

    Saves as poster.png in the target directory.
    Returns the path to the extracted file, or None on failure.
    """
    if not metadata.MKVEXTRACT_PATH:
        return None

    poster_path = target_dir / "poster.png"

    try:
        # mkvextract attachments <file> <attachment_id>:<output_path>
        # Attachment ID 1 is typically the cover image
        result = subprocess.run(
            [metadata.MKVEXTRACT_PATH, str(source), "attachments", f"1:{poster_path}"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0 and poster_path.exists():
            return poster_path
        return None
    except Exception:
        return None
