"""Resize a poster image to inline-email thumbnail JPEG bytes."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image


def make_thumbnail(poster_path: Path, width: int, *, quality: int = 82) -> bytes:
    """Return JPEG bytes of the poster resized to 2x `width` (retina), aspect kept."""
    with Image.open(poster_path) as src:
        img = src.convert("RGB")
        target_w = max(1, width * 2)
        new_h = max(1, round(img.height * (target_w / img.width)))
        img = img.resize((target_w, new_h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
