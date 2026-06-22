"""Poster generation: set posters (v5b layout) and album posters (editorial gradient).

Set posters use embedded cover art or sampled frames as source image.
Album posters use gradient backgrounds derived from thumbnail colors.
Layout uses a line-anchored system: accent line at 2/3 down, artist builds UP, metadata builds DOWN.

Logging:
    Logger: 'festival_organizer.poster'
    Key events:
        - thumbnail.read_error (DEBUG): Could not read a thumbnail for color extraction
        - background.load_error (WARNING): Could not load artist fanart background image
        - layout.branch (INFO): Which album poster layout was selected
    See docs/logging.md for full guidelines.
"""

import logging
import math
import re
from colorsys import hsv_to_rgb, rgb_to_hsv
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from festival_organizer.fonts import get_font_path

logger = logging.getLogger(__name__)

# --- Cover sidecar stamp (staleness tracking; see plans/2026-06-12-mkv-cover-attachment-naming.md) ---
# Bump COVER_POSTER_VERSION whenever the set-poster composition changes so existing
# posters are re-rendered and re-embedded on the next enrich run.
COVER_POSTER_VERSION = 2

_STAMP_PREFIX = "CDPOSTER"
_STAMP_SEP = "\x1f"  # unit separator: never appears in the resolved field values
_STAMP_LINE_SEP = (
    "\x1e"  # record separator: joins the rendered artist lines within the stamp
)


def build_cover_stamp(
    *,
    artist: str,
    festival: str,
    date: str,
    year: str,
    stage: str,
    venue: str,
    artists_1001tl: list[str] | None = None,
) -> bytes:
    """Build the staleness stamp from the fields that determine the rendered poster.

    The artist portion is stamped as the resolved render output
    (``_resolve_artist_lines``), so the stamp changes exactly when the drawn
    artist text changes, not merely when ``display_artist`` changes. For a
    1001TL set the lines come from ``artists_1001tl``; for a non-1001TL set
    they fall back to ``artist`` (display) via the helper.
    """
    artist_lines = _resolve_artist_lines(artists_1001tl, artist)
    fields = [
        f"{_STAMP_PREFIX}{COVER_POSTER_VERSION}",
        _STAMP_LINE_SEP.join(artist_lines),
        festival or "",
        date or "",
        year or "",
        stage or "",
        venue or "",
    ]
    return _STAMP_SEP.join(fields).encode("utf-8")


# Bump FOLDER_POSTER_VERSION whenever the folder-poster (folder.jpg) composition or
# per-level layout changes so existing folder posters re-render on the next enrich run.
FOLDER_POSTER_VERSION = 1

_FOLDER_STAMP_PREFIX = "CDFOLDER"


def build_folder_stamp(
    *, poster_type: str, name: str, year: str, edition: str, bg: str = ""
) -> bytes:
    """Build the staleness stamp for a folder poster (``folder.jpg``).

    Encodes the inputs that determine which folder poster is rendered: the poster
    type (``festival`` / ``artist`` / ``year``), the name shown above the line, the
    year (for year badges), the edition, and ``bg`` (a cheap fingerprint of the
    background image, so a refreshed artist photo or swapped curated logo also
    regenerates the poster). A change to any of these, or a ``FOLDER_POSTER_VERSION``
    bump, makes the stamp differ from the one embedded in an existing ``folder.jpg``
    and triggers regeneration, this is how a layout change (folder now represents a
    different type/name) self-heals. Derived gradient colors are intentionally
    excluded (mirrors ``build_cover_stamp``) to avoid thrash. Reuses the same JPEG
    COM read/write as set posters (``read_poster_stamp`` / ``inject_poster_stamp``).
    """
    fields = [
        f"{_FOLDER_STAMP_PREFIX}{FOLDER_POSTER_VERSION}",
        poster_type or "",
        name or "",
        year or "",
        edition or "",
        bg or "",
    ]
    return _STAMP_SEP.join(fields).encode("utf-8")


def read_poster_stamp(path: Path) -> bytes | None:
    """Return the first JPEG COM marker payload from a poster sidecar, or None."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if data[:2] != b"\xff\xd8":  # not a JPEG
        return None
    i, n = 2, len(data)
    while i + 4 <= n and data[i] == 0xFF:
        marker = data[i + 1]
        if marker == 0xD9:  # EOI
            break
        if 0xD0 <= marker <= 0xD7:  # RSTn: no length
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
        if marker == 0xFE:  # COM
            return data[i + 4 : i + 2 + seg_len]
        if marker == 0xDA:  # SOS: image scan begins
            break
        i += 2 + seg_len
    return None


def inject_poster_stamp(path: Path, stamp: bytes) -> None:
    """Splice a JPEG COM marker carrying the stamp right after SOI (no re-encode).

    Idempotent: any existing COM markers immediately following SOI are removed
    first, so re-stamping a previously stamped poster does not accumulate markers.
    """
    data = Path(path).read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError(f"not a JPEG: {path}")
    body = data[2:]
    # Drop existing COM markers at the SOI position (idempotent re-stamp).
    while len(body) >= 4 and body[:2] == b"\xff\xfe":
        seg_len = int.from_bytes(body[2:4], "big")
        body = body[2 + seg_len :]
    segment = b"\xff\xfe" + (len(stamp) + 2).to_bytes(2, "big") + stamp
    Path(path).write_bytes(data[:2] + segment + body)


# Layout constants (tuned through ~15 iterations)
POSTER_W, POSTER_H = 1000, 1500
LINE_Y = int(POSTER_H * 0.67)  # accent line at 2/3
LINE_H = 4

PAD_LINE_TO_ARTIST = 30
PAD_ARTIST_LINES = 6
PAD_LINE_TO_FEST = 30
PAD_FEST_TO_YEAR = 22
PAD_YEAR_TO_DETAIL = 22
PAD_DETAIL_LINES = 8

_font_overrides: dict[str, str] | None = None


def configure_fonts(overrides: dict[str, str] | None = None) -> None:
    """Set font path overrides from user config."""
    global _font_overrides
    _font_overrides = overrides


def get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font variant by name using bundled fonts or config overrides."""
    path = get_font_path(name, overrides=_font_overrides)
    return ImageFont.truetype(path, size)


def auto_fit(
    text: str, font_name: str, max_width: int, start: int = 120, minimum: int = 40
):
    """Auto-size font to fit text within max_width. Returns (font, size)."""
    for size in range(start, minimum - 1, -2):
        font = get_font(font_name, size)
        w = font.getbbox(text)[2] - font.getbbox(text)[0]
        if w <= max_width:
            return font, size
    return get_font(font_name, minimum), minimum


def font_visual_height(font: ImageFont.FreeTypeFont) -> int:
    """Get full visual height (ascent + descent) — consistent for a font size."""
    ascent, descent = font.getmetrics()
    return ascent + descent


def measure_w(font: ImageFont.FreeTypeFont, text: str) -> int:
    """Measure text width."""
    bbox = font.getbbox(text)
    return int(bbox[2] - bbox[0])


# --- Color contrast (WCAG) ---
# Shared primitive: _wcag_contrast(color, bg=...). Directional helpers build on it:
#   _ensure_contrast        - brighten a color until it reads on a dark background
#   _darken_for_white_text  - darken a fill until white text reads on it


def _wcag_luminance(r: int, g: int, b: int) -> float:
    """Calculate WCAG relative luminance with proper sRGB linearization."""

    def _linearize(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _wcag_contrast(
    r: int, g: int, b: int, bg: tuple[int, int, int] = (10, 10, 10)
) -> float:
    """Calculate WCAG contrast ratio against a dark background."""
    l1 = _wcag_luminance(r, g, b)
    l2 = _wcag_luminance(*bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _ensure_contrast(
    r: int, g: int, b: int, min_ratio: float = 4.5
) -> tuple[int, int, int]:
    """Boost color brightness until it meets WCAG AA contrast against dark background."""
    if _wcag_contrast(r, g, b) >= min_ratio:
        return (r, g, b)
    h, s, v = rgb_to_hsv(r / 255, g / 255, b / 255)
    ri, gi, bi = (
        r,
        g,
        b,
    )  # bound before the loop (range(40) always runs; satisfies type check)
    for _ in range(40):
        v = min(v + 0.03, 1.0)
        s = max(s - 0.01, 0.3)  # slightly desaturate to gain luminance
        nr, ng, nb = hsv_to_rgb(h, s, v)
        ri, gi, bi = int(nr * 255), int(ng * 255), int(nb * 255)
        if _wcag_contrast(ri, gi, bi) >= min_ratio:
            return (ri, gi, bi)
    return (ri, gi, bi)


def _darken_for_white_text(
    color: tuple[int, int, int], min_ratio: float = 3.0
) -> tuple[int, int, int]:
    """Darken a fill color until white text on it meets WCAG contrast.

    The inverse of :func:`_ensure_contrast` (which brightens a color to read on a
    dark background); this darkens a colored fill so white text stays legible on
    it. Both build on the shared :func:`_wcag_contrast` primitive. The default
    ``min_ratio`` of 3.0 is the WCAG AA threshold for large text (the year digits
    are large), so vivid brand colors are darkened only when genuinely too light.
    """
    if _wcag_contrast(255, 255, 255, bg=color) >= min_ratio:
        return color
    h, s, v = rgb_to_hsv(*[c / 255 for c in color])
    ci = color
    for _ in range(40):
        v = max(v - 0.03, 0.0)
        nr, ng, nb = hsv_to_rgb(h, s, v)
        ci = (int(nr * 255), int(ng * 255), int(nb * 255))
        if _wcag_contrast(255, 255, 255, bg=ci) >= min_ratio:
            return ci
    return ci


def _circular_hue_mean(h_array, s_array, min_sat: int = 40) -> float:
    """Compute circular mean of hue, weighted by saturation, ignoring low-sat pixels.

    Hue is circular (0-255 maps to 0-360°), so simple averaging breaks for reds
    that straddle 0°/360°. Use sin/cos decomposition instead.
    """
    mask = s_array >= min_sat
    if not mask.any():
        mask = s_array >= 0  # fallback: use all pixels

    h_filtered = h_array[mask].astype(np.float64)
    s_filtered = s_array[mask].astype(np.float64)

    angles = h_filtered * (2 * math.pi / 255)
    weights = s_filtered / 255
    sin_sum = np.sum(np.sin(angles) * weights)
    cos_sum = np.sum(np.cos(angles) * weights)
    mean_angle = math.atan2(sin_sum, cos_sum)
    if mean_angle < 0:
        mean_angle += 2 * math.pi
    return mean_angle / (2 * math.pi)


def get_accent_color(img: Image.Image) -> tuple[int, int, int]:
    """Auto-derive accent color from source image using circular hue mean."""
    hsv = img.convert("HSV")
    arr = np.array(hsv)
    h_arr, s_arr = arr[:, :, 0].ravel(), arr[:, :, 1].ravel()

    h = _circular_hue_mean(h_arr, s_arr)
    s = (
        min(1.0, float(np.mean(s_arr[s_arr >= 40])) / 160)
        if (s_arr >= 40).any()
        else 0.5
    )
    v = 0.95
    r, g, b = hsv_to_rgb(h, s, v)
    color = (int(r * 255), int(g * 255), int(b * 255))
    return _ensure_contrast(*color)


def split_artist(name: str) -> list[str]:
    """Split artist name for multi-line display.

    Returns a list of 1-3 lines:
    1. Parenthetical: "Act Name (Artist & Artist)" -> ["Act Name", "Artist & Artist"]
    2. Multiple connectors: split at each & / B2B / vs / x
    3. Single connector: split into 2 lines
    4. No connector: single line
    """
    # 1. Parenthetical pattern
    paren_match = re.match(r"^(.+?)\s*\((.+)\)\s*$", name)
    if paren_match:
        return [paren_match.group(1).strip(), paren_match.group(2).strip()]
    # 2. Find all connector positions
    upper = name.upper()
    splits: list[tuple[int, str]] = []
    for sep in [" & ", " B2B ", " VS ", " X "]:
        start = 0
        while True:
            idx = upper.find(sep, start)
            if idx == -1:
                break
            splits.append((idx, sep))
            start = idx + len(sep)
    if not splits:
        return [name]
    splits.sort()
    # 3. Single connector -> 2 lines
    if len(splits) == 1:
        idx, sep = splits[0]
        return [name[:idx].strip(), name[idx:].strip()]
    # 4. Multiple connectors -> one line per artist, keeping connector on each subsequent line
    lines = [name[: splits[0][0]].strip()]
    for i, (idx, _sep) in enumerate(splits):
        end = splits[i + 1][0] if i + 1 < len(splits) else len(name)
        lines.append(name[idx:end].strip())
    return lines


def _resolve_artist_lines(artists_1001tl: list[str] | None, display: str) -> list[str]:
    """Resolve set-poster artist lines from the billed per-act 1001TL list.

    ``artists_1001tl`` is the raw, alias-preserving, billed-form per-act list
    (``MediaFile.artists_1001tl`` / the ``CRATEDIGGER_1001TL_ARTISTS`` tag),
    where a duo such as "Dimitri Vegas & Like Mike" is ONE element. Lines are
    built from it directly: the first act as-is, each subsequent act prefixed
    "& ". A single element yields one line, so an internal "&"/"with" in an act
    name is never split. This matches TrackSplit's cover layout and shows the
    alias (the 1001TL form), never the resolved canonical.

    ``display`` is the fallback ONLY for non-1001TL files (empty list): they
    keep the previous ``split_artist`` behaviour, including its parenthetical
    handling.
    """
    if artists_1001tl:
        return [artists_1001tl[0]] + [f"& {a}" for a in artists_1001tl[1:]]
    return split_artist(display)


def _balanced_word_split(text: str) -> list[str] | None:
    """Split text at the word boundary closest to equal line widths."""
    words = text.split()
    if len(words) < 2:
        return None
    best: tuple[int, list[str]] | None = None
    for i in range(1, len(words)):
        a = " ".join(words[:i])
        b = " ".join(words[i:])
        diff = abs(len(a) - len(b))
        if best is None or diff < best[0]:
            best = (diff, [a, b])
    return best[1] if best else None


def _word_wrap_lines(lines: list[str], max_width: int, min_size: int) -> list[str]:
    """Re-split any line that doesn't fit at min_size."""
    result: list[str] = []
    for line in lines:
        font = get_font("bold", min_size)
        if measure_w(font, line) <= max_width:
            result.append(line)
            continue
        wrapped = _balanced_word_split(line)
        if wrapped is None:
            result.append(line)
            continue
        result.extend(wrapped)
    return result


def format_date_display(date: str, year: str) -> str:
    """Format date for display. Full date -> '28 March 2025', year only -> '2025'."""
    if date and len(date) == 10:
        try:
            parts = date.split("-")
            months = [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ]
            day = int(parts[2])
            month = months[int(parts[1]) - 1]
            return f"{day} {month} {parts[0]}"
        except (IndexError, ValueError):
            pass
    return year or ""


def _filter_venue_parts(venue: str, detail: str, festival: str = "") -> list[str]:
    """Return venue parts not already covered by a detail or festival part."""
    if not venue:
        return []
    known_lower = [p.strip().lower() for p in detail.split(",") if p.strip()]
    known_lower += [p.strip().lower() for p in festival.split(",") if p.strip()]
    result = []
    for part in [p.strip() for p in venue.split(",") if p.strip()]:
        part_lower = part.lower()
        if any(part_lower in k or k in part_lower for k in known_lower):
            continue
        result.append(part)
    return result


# --- Drawing helpers ---


def _draw_centered(
    draw, y, text, font, fill, letter_spacing=0, stroke_width=0, stroke_fill=None
):
    """Draw centered text with optional letter spacing and stroke outline."""
    sw_kwargs = {}
    if stroke_width and stroke_fill:
        sw_kwargs = {"stroke_width": stroke_width, "stroke_fill": stroke_fill}
    if letter_spacing == 0:
        w = measure_w(font, text)
        x = (POSTER_W - w) // 2
        draw.text((x, y), text, fill=fill, font=font, **sw_kwargs)
    else:
        total_w = sum(measure_w(font, c) for c in text) + letter_spacing * (
            len(text) - 1
        )
        x = (POSTER_W - total_w) // 2
        for c in text:
            cw = measure_w(font, c)
            draw.text((x, y), c, fill=fill, font=font, **sw_kwargs)
            x += cw + letter_spacing


def _draw_glow_line(base_img, y, width, height, color, glow_radius=14):
    """Draw accent line with glow effect."""
    x1 = POSTER_W // 2 - width // 2
    x2 = POSTER_W // 2 + width // 2

    glow = Image.new("RGBA", (POSTER_W, POSTER_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for offset in range(-2, 3):
        gd.rectangle([(x1, y + offset), (x2, y + height + offset)], fill=(*color, 220))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    glow2 = glow.filter(ImageFilter.GaussianBlur(radius=glow_radius // 2))
    glow = Image.alpha_composite(glow, glow2)

    result = Image.alpha_composite(base_img.convert("RGBA"), glow)
    rd = ImageDraw.Draw(result)
    rd.rectangle([(x1, y), (x2, y + height)], fill=color)
    return result.convert("RGB")


def _draw_glow_text(base_img, y, text, font, fill, glow_color, glow_radius=18):
    """Draw text with glow effect."""
    w = measure_w(font, text)
    x = (POSTER_W - w) // 2

    glow = Image.new("RGBA", (POSTER_W, POSTER_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for opacity in [255, 220, 180]:
        gd.text((x, y), text, fill=(*glow_color, opacity), font=font)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    glow2 = glow.filter(ImageFilter.GaussianBlur(radius=glow_radius // 2))
    glow = Image.alpha_composite(glow, glow2)

    result = Image.alpha_composite(base_img.convert("RGBA"), glow)
    rd = ImageDraw.Draw(result)
    rd.text((x + 2, y + 2), text, fill=(0, 0, 0, 120), font=font)
    rd.text((x, y), text, fill=fill, font=font)
    return result.convert("RGB")


def _flatten_alpha(
    img: Image.Image, bg_color: tuple[int, int, int] = (0, 0, 0)
) -> Image.Image:
    """Composite an image with alpha onto a solid background -> RGB."""
    if img.mode not in ("RGBA", "LA", "PA"):
        return img.convert("RGB")
    bg = Image.new("RGB", img.size, bg_color)
    bg.paste(img.convert("RGBA"), (0, 0), img.convert("RGBA"))
    return bg


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Parse a hex color string to an RGB tuple."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) != 6:
        raise ValueError(f"Expected 6-character hex color, got: {hex_str!r}")
    return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))


def _neutral_base_from_luminance(img: Image.Image) -> tuple[int, int, int]:
    """Derive a moody neutral-gray base color from a monochrome image.

    Used when a background image has content but no saturated pixels (e.g. a
    black-and-white promo). Returns a pure gray whose value is the image's mean
    luminance, clamped to the moody band [0.40, 0.55] of full scale so high-key
    images do not blow out and dark images do not go fully black.
    """
    if img.mode in ("RGBA", "LA", "PA"):
        arr = np.array(img.convert("RGBA"))
        mask = arr[:, :, 3] > 128
        rgb_pixels = arr[:, :, :3][mask] if mask.any() else arr[:, :, :3].reshape(-1, 3)
    else:
        rgb_pixels = np.array(img.convert("RGB")).reshape(-1, 3)

    if rgb_pixels.size:
        # Rec. 601 luma, normalized to 0..1
        luma = rgb_pixels @ np.array([0.299, 0.587, 0.114])
        mean_luma = float(np.mean(luma)) / 255
    else:
        mean_luma = 0.5

    v = max(0.40, min(0.55, mean_luma))
    g = round(v * 255)
    return (g, g, g)


def _extract_logo_color(img: Image.Image) -> tuple[int, int, int]:
    """Extract a gradient base color from a background image.

    Filters out low-saturation pixels (white/black/gray) and returns a
    dark/moody RGB color (V ~0.5) derived from the colorful pixels. For a
    monochrome image (content but no saturated pixels) returns a neutral gray
    from _neutral_base_from_luminance so the image still renders. Raises
    ValueError only when the image has no visible pixels at all.
    """
    if img.mode in ("RGBA", "LA", "PA"):
        arr = np.array(img.convert("RGBA"))
        mask = arr[:, :, 3] > 128
        if not mask.any():
            raise ValueError("No visible pixels found in logo")
        rgb_pixels = arr[:, :, :3][mask]
    else:
        arr = np.array(img.convert("RGB"))
        rgb_pixels = arr.reshape(-1, 3)

    # Convert to HSV using PIL for consistency with _circular_hue_mean
    strip = Image.fromarray(rgb_pixels.reshape(1, -1, 3).astype(np.uint8), "RGB")
    hsv_strip = np.array(strip.convert("HSV"))
    h_arr = hsv_strip[0, :, 0]
    s_arr = hsv_strip[0, :, 1]

    # Filter to saturated pixels
    sat_mask = s_arr >= 40
    if not sat_mask.any():
        # Monochrome image (e.g. a black-and-white promo): no hue to extract,
        # but the image is still displayable. Return a neutral gray base so the
        # portrait renders instead of collapsing to a bare gradient.
        return _neutral_base_from_luminance(img)

    hue = _circular_hue_mean(h_arr, s_arr, min_sat=40)
    mean_sat = float(np.mean(s_arr[sat_mask]) / 255)
    sat = max(0.4, min(0.7, mean_sat))

    r, g, b = hsv_to_rgb(hue, sat, 0.5)
    return (int(r * 255), int(g * 255), int(b * 255))


# --- Set poster generation ---


def generate_set_poster(
    source_image_path: Path,
    output_path: Path,
    artist: str,
    festival: str,
    date: str = "",
    year: str = "",
    detail: str = "",
    venue: str = "",
    artists_1001tl: list[str] | None = None,
) -> Path:
    """Generate a set poster (per-video) using the v5b line-anchored layout.

    Args:
        source_image_path: Path to cover art or sampled frame image
        output_path: Where to save the poster
        artist: Artist name
        festival: Festival display name (already resolved with location)
        date: ISO date string (YYYY-MM-DD) for full date display
        year: Year string as fallback
        detail: Optional detail line (stage name)
        venue: Optional venue/location (rendered in light gray)
        artists_1001tl: Optional billed per-act 1001TL list; when set, drives the
            artist lines directly (one act per line), otherwise falls back to
            split_artist(artist). See _resolve_artist_lines.

    Returns:
        Path to the generated poster
    """
    try:
        frame_raw = Image.open(source_image_path)
        has_alpha = frame_raw.mode in ("RGBA", "LA", "PA")
        frame_rgb = _flatten_alpha(frame_raw)
    except (OSError, ValueError) as e:
        raise OSError(f"Cannot open source image {source_image_path}: {e}") from e
    accent = get_accent_color(frame_rgb)

    # Blurred + darkened background fills entire poster
    bg = frame_rgb.resize((POSTER_W, POSTER_H), Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=40))
    bg = ImageEnhance.Brightness(bg).enhance(0.18)

    # Sharp image flush to top, cover-fit to fill minimum height
    min_img_h = 700
    scale = max(POSTER_W / frame_raw.width, min_img_h / frame_raw.height)
    scaled_w = int(frame_raw.width * scale)
    scaled_h = int(frame_raw.height * scale)

    if has_alpha:
        sharp = frame_raw.convert("RGBA").resize(
            (scaled_w, scaled_h), Image.Resampling.LANCZOS
        )
    else:
        sharp = frame_rgb.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    # Center-crop horizontally to poster width
    if scaled_w > POSTER_W:
        left = (scaled_w - POSTER_W) // 2
        sharp = sharp.crop((left, 0, left + POSTER_W, scaled_h))
    # Crop vertically if taller than target
    new_h = min(scaled_h, min_img_h)
    if scaled_h > min_img_h:
        top = (scaled_h - min_img_h) // 2
        sharp = sharp.crop((0, top, POSTER_W, top + min_img_h))
        new_h = sharp.height

    # Fade mask starting at 60% of image height
    fade_mask = Image.new("L", (POSTER_W, new_h), 255)
    dm = ImageDraw.Draw(fade_mask)
    fade_start = int(new_h * 0.60)
    for y in range(fade_start, new_h):
        alpha = int(255 * (1 - (y - fade_start) / (new_h - fade_start)))
        dm.line([(0, y), (POSTER_W, y)], fill=alpha)

    if has_alpha:
        orig_alpha = sharp.split()[3]
        combined = Image.fromarray(
            np.minimum(np.array(orig_alpha), np.array(fade_mask)), mode="L"
        )
        sharp.putalpha(combined)
        bg = bg.convert("RGBA")
        bg.paste(sharp, (0, 0), sharp)
        bg = bg.convert("RGB")
    else:
        bg.paste(sharp, (0, 0), fade_mask)

    # Dark gradient overlay from 40% down
    gradient = Image.new("RGBA", (POSTER_W, POSTER_H), (0, 0, 0, 0))
    dg = ImageDraw.Draw(gradient)
    grad_start = int(POSTER_H * 0.40)
    for y in range(grad_start, POSTER_H):
        progress = (y - grad_start) / (POSTER_H - grad_start)
        a = int(200 * progress**1.4)
        dg.line([(0, y), (POSTER_W, y)], fill=(0, 0, 0, a))
    bg = Image.alpha_composite(bg.convert("RGBA"), gradient).convert("RGB")

    draw = ImageDraw.Draw(bg)
    max_w = POSTER_W - 100

    # Split artist name into lines, word-wrap any that don't fit
    artist_lines = [
        line.upper() for line in _resolve_artist_lines(artists_1001tl, artist)
    ]
    artist_lines = _word_wrap_lines(artist_lines, max_w, min_size=80)

    # Auto-fit fonts — uniform size across all lines (driven by the longest)
    sizes = []
    for line in artist_lines:
        _, size = auto_fit(line, "bold", max_w, start=130, minimum=50)
        sizes.append(size)
    shared_size = min(sizes)
    font_artist = get_font("bold", shared_size)

    font_fest, _ = auto_fit(festival.upper(), "bold", max_w, start=68, minimum=36)
    # BUILD UP from accent line — stack lines bottom-to-top
    line_h = font_visual_height(font_artist)
    cursor_y = LINE_Y - PAD_LINE_TO_ARTIST
    for line in reversed(artist_lines):
        cursor_y -= line_h
        sp = max(
            2, min(14, (max_w - measure_w(font_artist, line)) // max(len(line), 1))
        )
        _draw_centered(draw, cursor_y, line, font_artist, "white", letter_spacing=sp)
        cursor_y -= PAD_ARTIST_LINES

    # ACCENT LINE with glow
    bg = _draw_glow_line(bg, LINE_Y, 400, LINE_H, accent, glow_radius=16)
    draw = ImageDraw.Draw(bg)

    # BUILD DOWN from accent line
    ty = LINE_Y + LINE_H + PAD_LINE_TO_FEST

    # Festival name (plain colored text, no glow)
    fest_h = font_visual_height(font_fest)
    _draw_centered(draw, ty, festival.upper(), font_fest, accent)
    ty += fest_h + PAD_FEST_TO_YEAR

    # Date/Year line — white, no effects for TV readability
    date_display = format_date_display(date, year)
    if date_display:
        font_year, _ = auto_fit(date_display, "semilight", max_w, start=62, minimum=28)
        year_h = font_visual_height(font_year)
        _draw_centered(draw, ty, date_display, font_year, "white")
        ty += year_h + PAD_YEAR_TO_DETAIL

    # Detail lines — split on comma, auto-fit each line
    if detail:
        for part in [p.strip() for p in detail.split(",") if p.strip()]:
            font_d, _ = auto_fit(part, "semilight", max_w, start=62, minimum=28)
            dh = font_visual_height(font_d)
            _draw_centered(draw, ty, part, font_d, "white")
            ty += dh + PAD_DETAIL_LINES

    # Venue lines — deduplicate against detail, split on comma
    if venue:
        for part in _filter_venue_parts(venue, detail or "", festival):
            font_v, _ = auto_fit(part, "semilight", max_w, start=62, minimum=28)
            vh = font_visual_height(font_v)
            _draw_centered(draw, ty, part, font_v, (200, 200, 200))
            ty += vh + PAD_DETAIL_LINES

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bg.save(str(output_path), quality=95)
    return output_path


# --- Album poster generation ---


def get_dominant_color_from_thumbs(thumb_paths: list[Path]) -> tuple[int, int, int]:
    """Get average color from thumbnail images using circular hue mean."""
    if not thumb_paths:
        return (40, 80, 180)  # default blue

    all_h: list[np.ndarray] = []
    all_s: list[np.ndarray] = []
    for path in thumb_paths:
        try:
            img = Image.open(path).convert("HSV")
            arr = np.array(img)
            all_h.append(arr[:, :, 0].ravel())
            all_s.append(arr[:, :, 1].ravel())
        except (OSError, ValueError) as e:
            logger.debug('poster.thumb: status=read_failed path=%s error="%s"', path, e)
            continue

    if not all_h:
        return (40, 80, 180)

    h_arr = np.concatenate(all_h)
    s_arr = np.concatenate(all_s)

    h = _circular_hue_mean(h_arr, s_arr)
    s = (
        min(0.7, float(np.mean(s_arr[s_arr >= 40])) / 255)
        if (s_arr >= 40).any()
        else 0.3
    )
    v = 0.5
    r, g, b = hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _darken_brand_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Darken a brand color to a moody gradient base (V ~0.5)."""
    r, g, b = [c / 255 for c in color]
    h, s, v = rgb_to_hsv(r, g, b)
    s = max(0.4, min(0.7, s))
    v = 0.5
    r2, g2, b2 = hsv_to_rgb(h, s, v)
    return (int(r2 * 255), int(g2 * 255), int(b2 * 255))


def _accent_from_base(base_color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Derive a brighter accent color from the base."""
    r, g, b = [c / 255 for c in base_color]
    h, s, v = rgb_to_hsv(r, g, b)
    r2, g2, b2 = hsv_to_rgb(h, min(s * 1.3, 0.9), min(v + 0.4, 0.95))
    return (int(r2 * 255), int(g2 * 255), int(b2 * 255))


def _make_gradient_bg(
    base_color: tuple[int, int, int],
    width: int = POSTER_W,
    height: int = POSTER_H,
) -> Image.Image:
    """Create a smooth gradient background with radial highlight and noise grain."""
    r, g, b = base_color
    bg = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(bg)

    # Vertical gradient: lighter at top, darker at bottom
    for y in range(height):
        progress = y / height
        brightness = 0.55 * (1 - progress**0.8) + 0.08
        sat_factor = 1.0 - 0.3 * progress
        line_r = int(r * brightness * sat_factor)
        line_g = int(g * brightness * sat_factor)
        line_b = int(b * brightness * sat_factor)
        draw.line([(0, y), (width, y)], fill=(line_r, line_g, line_b))

    # Radial highlight in upper center
    highlight = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    cx, cy = width // 2, int(height * 0.30)
    radius = int(width * 0.6)
    for dist in range(radius, 0, -2):
        alpha = int(40 * (1 - dist / radius) ** 2)
        hd.ellipse(
            [(cx - dist, cy - dist), (cx + dist, cy + dist)], fill=(r, g, b, alpha)
        )
    bg = Image.alpha_composite(bg.convert("RGBA"), highlight).convert("RGB")

    # Subtle noise grain
    noise = np.random.default_rng(42).normal(0, 3, (height, width, 3)).astype(np.int16)
    bg_arr = np.array(bg, dtype=np.int16) + noise
    bg_arr = np.clip(bg_arr, 0, 255).astype(np.uint8)
    bg = Image.fromarray(bg_arr)

    return bg


def _center_sharp(frame: Image.Image, max_display: int) -> tuple[Image.Image, int, int]:
    """Scale and center a sharp image in the upper poster area."""
    scale = min(max_display / frame.width, max_display / frame.height)
    new_w = int(frame.width * scale)
    new_h = int(frame.height * scale)
    sharp = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)
    img_x = (POSTER_W - new_w) // 2
    img_y = int(LINE_Y * 0.5) - new_h // 2
    img_y = max(30, img_y)
    return sharp, img_x, img_y


def _rounded_edge_mask(w: int, h: int, corner_pct: float = 0.06) -> Image.Image:
    """Create a mask with rounded corners."""
    corner_r = int(min(w, h) * corner_pct)
    mask = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(mask)
    dm.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=corner_r, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(radius=2))


def _draw_glyph_centered(
    draw, width, top, text, font, fill=(255, 255, 255, 255)
) -> None:
    """Draw text horizontally centered in `width` with its glyph box top at `top`.

    Uses the glyph bounding box (not the font line box) so the visible digits are
    centered within the badge tile.
    """
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    x = (width - w) // 2 - bbox[0]
    y = top - bbox[1]
    draw.text((x, y), text, font=font, fill=fill)


def _make_year_badge(
    year: str,
    color: tuple[int, int, int],
    size: int = 420,
) -> Image.Image:
    """Render a colorful rounded-square badge holding the year.

    Fills a square tile with a vertical brand gradient (a lighter tint at the top
    fading to a deeper shade at the bottom), rounds the corners to match the
    logo/photo tiles, and draws the year centered in white. Each gradient stop is
    passed through :func:`_darken_for_white_text`, so light brand colors are
    darkened just enough to keep the white year legible (no drop shadow needed).
    Returns an RGBA tile (transparent outside the rounded square) ready to paste
    into the logo slot.
    """
    h, s, v = rgb_to_hsv(*[c / 255 for c in color])
    v = v or 0.6
    top = hsv_to_rgb(h, max(0.0, s * 0.85), min(1.0, v * 1.18))
    bot = hsv_to_rgb(h, min(1.0, s * 1.05), v * 0.70)
    top_stop = _darken_for_white_text(
        (int(top[0] * 255), int(top[1] * 255), int(top[2] * 255))
    )
    bot_stop = _darken_for_white_text(
        (int(bot[0] * 255), int(bot[1] * 255), int(bot[2] * 255))
    )
    top_rgb = np.array(top_stop, dtype=float)
    bot_rgb = np.array(bot_stop, dtype=float)
    t = np.linspace(0.0, 1.0, size).reshape(size, 1)
    rows = top_rgb * (1 - t) + bot_rgb * t  # (size, 3)
    grad = np.repeat(rows[:, None, :], size, axis=1)  # (size, size, 3)
    tile = Image.fromarray(np.clip(grad, 0, 255).astype(np.uint8), "RGB").convert(
        "RGBA"
    )
    tile.putalpha(_rounded_edge_mask(size, size))

    draw = ImageDraw.Draw(tile)
    usable = int(size * 0.68)
    font, _ = auto_fit(year, "bold", usable, start=int(size * 0.5), minimum=40)
    bbox = font.getbbox(year)
    gh = bbox[3] - bbox[1]
    _draw_glyph_centered(draw, size, (size - gh) // 2, year, font)
    return tile


def generate_album_poster(
    output_path: Path,
    festival: str,
    date_or_year: str,
    detail: str = "",
    edition: str = "",
    thumb_paths: list[Path] | None = None,
    override_color: tuple[int, int, int] | None = None,
    background_image_path: Path | None = None,
    background_source: str = "",
    hero_text: str | None = None,
    year_badge: str = "",
) -> Path:
    """Generate an album poster.

    Uses a background image if provided (sharp top + fade, like set posters),
    otherwise falls back to an editorial gradient derived from thumbnail colors.

    For artist folders: pass hero_text="Artist Name" to show just the artist name.
    For festival folders: hero_text defaults to festival name with edition below.

    Args:
        output_path: Where to save the poster
        festival: Festival name (used as hero text if hero_text not set)
        date_or_year: Date or year string for display
        detail: Optional detail (venue, location)
        edition: Optional edition name (e.g. "Belgium", "Las Vegas")
        thumb_paths: Thumbnail images for color derivation
        override_color: Override the auto-derived color
        background_image_path: Optional background image (curated logo, fanart, DJ artwork)
        background_source: Name of the source that provided the background (for logging)
        hero_text: Override the hero text above the accent line (e.g. artist name)
        year_badge: When set, render a colorful rounded-square year badge in the
            logo slot (year folder posters). Pair with hero_text=None and
            festival=<parent name> so the parent name is the hero and the edition
            renders below the line.

    Returns:
        Path to the generated poster
    """
    if background_image_path and background_image_path.exists():
        # Background image provided (curated logo, fanart, DJ artwork)
        try:
            frame_raw = Image.open(background_image_path)
            has_alpha = frame_raw.mode in ("RGBA", "LA", "PA")

            # Derive base color: config override > logo extraction > error
            if override_color:
                base_color = _darken_brand_color(override_color)
                accent = override_color
            else:
                base_color = _extract_logo_color(frame_raw)
                accent = _accent_from_base(base_color)

            # Gradient base layer — always the foundation
            bg = _make_gradient_bg(base_color)

            # Flatten for blur/tile operations
            frame_rgb = (
                _flatten_alpha(frame_raw, base_color)
                if has_alpha
                else frame_raw.convert("RGB")
            )
            is_small_source = frame_raw.width < 600

            if is_small_source and hero_text is None:
                # Festival layout: gradient + centered sharp logo
                logger.info("poster.layout: type=festival_gradient_logo")
                max_display = 420
                if has_alpha:
                    sharp, img_x, img_y = _center_sharp(
                        frame_raw.convert("RGBA"), max_display
                    )
                    bg = bg.convert("RGBA")
                    bg.paste(sharp, (img_x, img_y), sharp)
                    bg = bg.convert("RGB")
                else:
                    sharp, img_x, img_y = _center_sharp(frame_rgb, max_display)
                    mask = _rounded_edge_mask(sharp.size[0], sharp.size[1])
                    bg.paste(sharp, (img_x, img_y), mask)

            elif is_small_source:
                # Artist layout: blurred overlay on gradient + centered sharp logo
                logger.info("poster.layout: type=artist_centered_blur")
                logger.debug(
                    "poster.layout: source=%dx%d origin=%s",
                    frame_raw.width,
                    frame_raw.height,
                    background_source or "unknown",
                )
                blurred = frame_rgb.resize(
                    (POSTER_W, POSTER_H), Image.Resampling.LANCZOS
                )
                blurred = blurred.filter(ImageFilter.GaussianBlur(radius=40))
                blurred = ImageEnhance.Brightness(blurred).enhance(0.18)
                blurred_rgba = blurred.convert("RGBA")
                blurred_rgba.putalpha(Image.new("L", (POSTER_W, POSTER_H), 150))
                bg = Image.alpha_composite(bg.convert("RGBA"), blurred_rgba)

                max_display = 550
                if has_alpha:
                    sharp, img_x, img_y = _center_sharp(
                        frame_raw.convert("RGBA"), max_display
                    )
                    bg.paste(sharp, (img_x, img_y), sharp)
                else:
                    sharp, img_x, img_y = _center_sharp(frame_rgb, max_display)
                    mask = _rounded_edge_mask(sharp.size[0], sharp.size[1])
                    bg.paste(sharp, (img_x, img_y), mask)
                bg = bg.convert("RGB")

            else:
                # Large source: sharp top on gradient, fade to dark
                logger.info("poster.layout: type=large_source_fade")
                logger.debug(
                    "poster.layout: source=%dx%d origin=%s",
                    frame_raw.width,
                    frame_raw.height,
                    background_source or "unknown",
                )
                scale = POSTER_W / frame_raw.width
                new_h = int(frame_raw.height * scale)
                fade_mask = Image.new("L", (POSTER_W, new_h), 255)
                dm = ImageDraw.Draw(fade_mask)
                fade_start = int(new_h * 0.60)
                for y in range(fade_start, new_h):
                    alpha = int(255 * (1 - (y - fade_start) / (new_h - fade_start)))
                    dm.line([(0, y), (POSTER_W, y)], fill=alpha)

                if has_alpha:
                    sharp_rgba = frame_raw.convert("RGBA").resize(
                        (POSTER_W, new_h), Image.Resampling.LANCZOS
                    )
                    orig_alpha = sharp_rgba.split()[3]
                    combined = Image.fromarray(
                        np.minimum(np.array(orig_alpha), np.array(fade_mask)), mode="L"
                    )
                    sharp_rgba.putalpha(combined)
                    bg = bg.convert("RGBA")
                    bg.paste(sharp_rgba, (0, 0), sharp_rgba)
                    bg = bg.convert("RGB")
                else:
                    sharp = frame_rgb.resize(
                        (POSTER_W, new_h), Image.Resampling.LANCZOS
                    )
                    bg.paste(sharp, (0, 0), fade_mask)

            # Dark gradient overlay from 40% down
            gradient = Image.new("RGBA", (POSTER_W, POSTER_H), (0, 0, 0, 0))
            dg = ImageDraw.Draw(gradient)
            grad_start = int(POSTER_H * 0.40)
            for y in range(grad_start, POSTER_H):
                progress = (y - grad_start) / (POSTER_H - grad_start)
                a = int(200 * progress**1.4)
                dg.line([(0, y), (POSTER_W, y)], fill=(0, 0, 0, a))
            bg = Image.alpha_composite(bg.convert("RGBA"), gradient).convert("RGB")
        except (OSError, ValueError) as e:
            logger.warning(
                'poster.background: status=failed path=%s error="%s"',
                background_image_path,
                e,
            )
            background_image_path = None  # fall through to gradient

    if not background_image_path or not background_image_path.exists():
        # Gradient fallback (no background image available)
        logger.info("poster.layout: type=gradient_fallback")
        if override_color:
            base_color = _darken_brand_color(override_color)
            accent = override_color
        else:
            base_color = get_dominant_color_from_thumbs(thumb_paths or [])
            accent = _accent_from_base(base_color)
        bg = _make_gradient_bg(base_color)
    if year_badge:
        badge = _make_year_badge(year_badge, accent, size=420)
        bx = (POSTER_W - badge.width) // 2
        by = max(30, int(LINE_Y * 0.5) - badge.height // 2)
        bg = bg.convert("RGBA")
        bg.paste(badge, (bx, by), badge)
        bg = bg.convert("RGB")

    draw = ImageDraw.Draw(bg)
    max_w = POSTER_W - 100

    # Determine hero text: artist name for artist folders, festival for festival folders
    is_artist_poster = hero_text is not None

    if is_artist_poster:
        display_text = hero_text.upper()
        font_hero, _ = auto_fit(display_text, "bold", max_w, start=130, minimum=50)
        hero_h = font_visual_height(font_hero)
        spacing = max(
            2,
            min(
                14,
                (max_w - measure_w(font_hero, display_text))
                // max(len(display_text), 1),
            ),
        )
        hero_y = LINE_Y - PAD_LINE_TO_ARTIST - hero_h
        _draw_centered(
            draw, hero_y, display_text, font_hero, "white", letter_spacing=spacing
        )
    else:
        display_text = festival.upper()
        font_hero, _ = auto_fit(display_text, "bold", max_w, start=130, minimum=50)
        hero_h = font_visual_height(font_hero)
        spacing = max(
            2,
            min(
                14,
                (max_w - measure_w(font_hero, display_text))
                // max(len(display_text), 1),
            ),
        )
        hero_y = LINE_Y - PAD_LINE_TO_FEST - hero_h
        _draw_centered(
            draw, hero_y, display_text, font_hero, "white", letter_spacing=spacing
        )

    # Accent line with glow
    bg = _draw_glow_line(bg, LINE_Y, 400, LINE_H, accent, glow_radius=16)
    draw = ImageDraw.Draw(bg)

    # Edition below accent line (festival posters only)
    if not is_artist_poster and edition:
        font_edition, _ = auto_fit(edition.upper(), "bold", max_w, start=68, minimum=36)
        ty = LINE_Y + LINE_H + PAD_LINE_TO_FEST
        _draw_centered(draw, ty, edition.upper(), font_edition, accent)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bg.save(str(output_path), quality=95)
    return output_path
