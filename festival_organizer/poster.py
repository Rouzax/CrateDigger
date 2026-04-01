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

logger = logging.getLogger(__name__)

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat

# Layout constants (tuned through ~15 iterations)
POSTER_W, POSTER_H = 1000, 1500
LINE_Y = int(POSTER_H * 0.67)  # accent line at 2/3
LINE_H = 4

PAD_LINE_TO_ARTIST = 28
PAD_ARTIST_LINES = 6
PAD_LINE_TO_FEST = 30
PAD_FEST_TO_YEAR = 22
PAD_YEAR_TO_DETAIL = 22
PAD_DETAIL_LINES = 8

from festival_organizer.fonts import get_font_path

_font_overrides: dict[str, str] | None = None


def configure_fonts(overrides: dict[str, str] | None = None) -> None:
    """Set font path overrides from user config."""
    global _font_overrides
    _font_overrides = overrides


def get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font variant by name using bundled fonts or config overrides."""
    path = get_font_path(name, overrides=_font_overrides)
    return ImageFont.truetype(path, size)


def auto_fit(text: str, font_name: str, max_width: int, start: int = 120, minimum: int = 40):
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
    return bbox[2] - bbox[0]


def _wcag_luminance(r: int, g: int, b: int) -> float:
    """Calculate WCAG relative luminance with proper sRGB linearization."""
    def _linearize(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _wcag_contrast(r: int, g: int, b: int, bg: tuple[int, int, int] = (10, 10, 10)) -> float:
    """Calculate WCAG contrast ratio against a dark background."""
    l1 = _wcag_luminance(r, g, b)
    l2 = _wcag_luminance(*bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _ensure_contrast(r: int, g: int, b: int, min_ratio: float = 4.5) -> tuple[int, int, int]:
    """Boost color brightness until it meets WCAG AA contrast against dark background."""
    if _wcag_contrast(r, g, b) >= min_ratio:
        return (r, g, b)
    h, s, v = rgb_to_hsv(r / 255, g / 255, b / 255)
    for _ in range(40):
        v = min(v + 0.03, 1.0)
        s = max(s - 0.01, 0.3)  # slightly desaturate to gain luminance
        nr, ng, nb = hsv_to_rgb(h, s, v)
        ri, gi, bi = int(nr * 255), int(ng * 255), int(nb * 255)
        if _wcag_contrast(ri, gi, bi) >= min_ratio:
            return (ri, gi, bi)
    return (ri, gi, bi)


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
    s = min(1.0, np.mean(s_arr[s_arr >= 40]) / 160) if (s_arr >= 40).any() else 0.5
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
    paren_match = re.match(r'^(.+?)\s*\((.+)\)\s*$', name)
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
    lines = [name[:splits[0][0]].strip()]
    for i, (idx, sep) in enumerate(splits):
        end = splits[i + 1][0] if i + 1 < len(splits) else len(name)
        lines.append(name[idx:end].strip())
    return lines


def format_date_display(date: str, year: str) -> str:
    """Format date for display. Full date -> '28 March 2025', year only -> '2025'."""
    if date and len(date) == 10:
        try:
            parts = date.split("-")
            months = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]
            day = int(parts[2])
            month = months[int(parts[1]) - 1]
            return f"{day} {month} {parts[0]}"
        except (IndexError, ValueError):
            pass
    return year or ""


def _filter_venue_parts(venue: str, detail: str) -> list[str]:
    """Return venue parts not already covered by a detail part (substring match)."""
    if not venue:
        return []
    detail_parts_lower = [p.strip().lower() for p in detail.split(",") if p.strip()]
    result = []
    for part in [p.strip() for p in venue.split(",") if p.strip()]:
        part_lower = part.lower()
        if any(part_lower in d or d in part_lower for d in detail_parts_lower):
            continue
        result.append(part)
    return result


# --- Drawing helpers ---

def _draw_centered(draw, y, text, font, fill, letter_spacing=0):
    """Draw centered text with optional letter spacing and drop shadow."""
    if letter_spacing == 0:
        w = measure_w(font, text)
        x = (POSTER_W - w) // 2
        draw.text((x + 2, y + 3), text, fill=(0, 0, 0, 160), font=font)
        draw.text((x, y), text, fill=fill, font=font)
    else:
        total_w = sum(measure_w(font, c) for c in text) + letter_spacing * (len(text) - 1)
        x = (POSTER_W - total_w) // 2
        for c in text:
            cw = measure_w(font, c)
            draw.text((x + 2, y + 3), c, fill=(0, 0, 0, 140), font=font)
            draw.text((x, y), c, fill=fill, font=font)
            x += cw + letter_spacing


def _draw_centered_no_shadow(draw, y, text, font, fill, letter_spacing=0):
    """Draw centered text without drop shadow (for album posters)."""
    if letter_spacing == 0:
        w = measure_w(font, text)
        x = (POSTER_W - w) // 2
        draw.text((x, y), text, fill=fill, font=font)
    else:
        total_w = sum(measure_w(font, c) for c in text) + letter_spacing * (len(text) - 1)
        x = (POSTER_W - total_w) // 2
        for c in text:
            cw = measure_w(font, c)
            draw.text((x, y), c, fill=fill, font=font)
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


def _flatten_alpha(img: Image.Image, bg_color: tuple[int, int, int] = (0, 0, 0)) -> Image.Image:
    """Composite an image with alpha onto a solid background -> RGB."""
    if img.mode not in ("RGBA", "LA", "PA"):
        return img.convert("RGB")
    bg = Image.new("RGB", img.size, bg_color)
    bg.paste(img.convert("RGBA"), (0, 0), img.convert("RGBA"))
    return bg


def _visible_pixel_color(img: Image.Image) -> tuple[int, int, int]:
    """Average RGB of visible (non-transparent) pixels. Falls back to (0,0,0)."""
    if img.mode in ("RGBA", "LA", "PA"):
        arr = np.array(img.convert("RGBA"))
        mask = arr[:, :, 3] > 128
        if mask.any():
            rgb = arr[:, :, :3][mask]
            mean = rgb.mean(axis=0)
            return (int(mean[0]), int(mean[1]), int(mean[2]))
    arr = np.array(img.convert("RGB"))
    mean = arr.mean(axis=(0, 1))
    return (int(mean[0]), int(mean[1]), int(mean[2]))


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Parse a hex color string to an RGB tuple."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) != 6:
        raise ValueError(f"Expected 6-character hex color, got: {hex_str!r}")
    return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))


def _extract_logo_color(img: Image.Image) -> tuple[int, int, int]:
    """Extract dominant color from logo using saturation-aware circular hue mean.

    Filters out low-saturation pixels (white/black/gray) and returns a dark/moody
    RGB color suitable for gradient backgrounds (V ~0.4).

    Raises ValueError if no saturated pixels are found.
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
        raise ValueError("No saturated pixels found in logo")

    hue = _circular_hue_mean(h_arr, s_arr, min_sat=40)
    mean_sat = float(np.mean(s_arr[sat_mask]) / 255)
    sat = max(0.4, min(0.7, mean_sat))

    r, g, b = hsv_to_rgb(hue, sat, 0.4)
    return (int(r * 255), int(g * 255), int(b * 255))


def _pixel_luminance(color: tuple[int, int, int]) -> float:
    """Simple perceived luminance (0-255 scale)."""
    return 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]


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
    bg = frame_rgb.resize((POSTER_W, POSTER_H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=40))
    bg = ImageEnhance.Brightness(bg).enhance(0.18)

    # Sharp image flush to top
    scale = POSTER_W / frame_raw.width
    new_h = int(frame_raw.height * scale)

    # Fade mask starting at 60% of image height
    fade_mask = Image.new("L", (POSTER_W, new_h), 255)
    dm = ImageDraw.Draw(fade_mask)
    fade_start = int(new_h * 0.60)
    for y in range(fade_start, new_h):
        alpha = int(255 * (1 - (y - fade_start) / (new_h - fade_start)))
        dm.line([(0, y), (POSTER_W, y)], fill=alpha)

    if has_alpha:
        sharp_rgba = frame_raw.convert("RGBA").resize((POSTER_W, new_h), Image.LANCZOS)
        orig_alpha = sharp_rgba.split()[3]
        combined = Image.fromarray(
            np.minimum(np.array(orig_alpha), np.array(fade_mask)), mode="L"
        )
        sharp_rgba.putalpha(combined)
        bg = bg.convert("RGBA")
        bg.paste(sharp_rgba, (0, 0), sharp_rgba)
        bg = bg.convert("RGB")
    else:
        sharp = frame_rgb.resize((POSTER_W, new_h), Image.LANCZOS)
        bg.paste(sharp, (0, 0), fade_mask)

    # Dark gradient overlay from 40% down
    gradient = Image.new("RGBA", (POSTER_W, POSTER_H), (0, 0, 0, 0))
    dg = ImageDraw.Draw(gradient)
    grad_start = int(POSTER_H * 0.40)
    for y in range(grad_start, POSTER_H):
        progress = (y - grad_start) / (POSTER_H - grad_start)
        a = int(200 * progress ** 1.4)
        dg.line([(0, y), (POSTER_W, y)], fill=(0, 0, 0, a))
    bg = Image.alpha_composite(bg.convert("RGBA"), gradient).convert("RGB")

    draw = ImageDraw.Draw(bg)
    max_w = POSTER_W - 100

    # Split artist name into lines
    artist_lines = [line.upper() for line in split_artist(artist)]

    # Auto-fit fonts — uniform size across all lines (driven by the longest)
    sizes = []
    for line in artist_lines:
        _, size = auto_fit(line, "bold", max_w, start=110, minimum=50)
        sizes.append(size)
    shared_size = min(sizes)
    font_artist = get_font("bold", shared_size)

    font_fest, _ = auto_fit(festival.upper(), "bold", max_w, start=68, minimum=36)
    font_year = get_font("semilight", 62)
    # BUILD UP from accent line — stack lines bottom-to-top
    line_h = font_visual_height(font_artist)
    cursor_y = LINE_Y - PAD_LINE_TO_ARTIST
    for line in reversed(artist_lines):
        cursor_y -= line_h
        sp = max(2, min(8, (max_w - measure_w(font_artist, line)) // max(len(line), 1)))
        _draw_centered(draw, cursor_y, line, font_artist, "white", letter_spacing=sp)
        cursor_y -= PAD_ARTIST_LINES

    # ACCENT LINE with glow
    bg = _draw_glow_line(bg, LINE_Y, 400, LINE_H, accent, glow_radius=14)
    draw = ImageDraw.Draw(bg)

    # BUILD DOWN from accent line
    ty = LINE_Y + LINE_H + PAD_LINE_TO_FEST

    # Festival name with glow
    fest_h = font_visual_height(font_fest)
    bg = _draw_glow_text(bg, ty, festival.upper(), font_fest, accent, accent, glow_radius=18)
    draw = ImageDraw.Draw(bg)
    ty += fest_h + PAD_FEST_TO_YEAR

    # Date/Year line — white, no effects for TV readability
    date_display = format_date_display(date, year)
    if date_display:
        year_h = font_visual_height(font_year)
        _draw_centered_no_shadow(draw, ty, date_display, font_year, "white")
        ty += year_h + PAD_YEAR_TO_DETAIL

    # Detail lines — split on comma, auto-fit each line
    if detail:
        for part in [p.strip() for p in detail.split(",") if p.strip()]:
            font_d, _ = auto_fit(part, "semilight", max_w, start=44, minimum=28)
            dh = font_visual_height(font_d)
            _draw_centered_no_shadow(draw, ty, part, font_d, "white")
            ty += dh + PAD_DETAIL_LINES

    # Venue lines — deduplicate against detail, split on comma
    if venue:
        for part in _filter_venue_parts(venue, detail or ""):
            font_v, _ = auto_fit(part, "semilight", max_w, start=38, minimum=24)
            vh = font_visual_height(font_v)
            _draw_centered_no_shadow(draw, ty, part, font_v, (200, 200, 200))
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
            logger.debug("Could not read thumbnail %s: %s", path, e)
            continue

    if not all_h:
        return (40, 80, 180)

    h_arr = np.concatenate(all_h)
    s_arr = np.concatenate(all_s)

    h = _circular_hue_mean(h_arr, s_arr)
    s = min(0.7, np.mean(s_arr[s_arr >= 40]) / 255) if (s_arr >= 40).any() else 0.3
    v = 0.5
    r, g, b = hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _accent_from_base(base_color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Derive a brighter accent color from the base."""
    r, g, b = [c / 255 for c in base_color]
    h, s, v = rgb_to_hsv(r, g, b)
    r2, g2, b2 = hsv_to_rgb(h, min(s * 1.3, 0.9), min(v + 0.4, 0.95))
    return (int(r2 * 255), int(g2 * 255), int(b2 * 255))


def _make_gradient_bg(base_color: tuple[int, int, int]) -> Image.Image:
    """Create a smooth gradient background with radial highlight and noise grain."""
    r, g, b = base_color
    bg = Image.new("RGB", (POSTER_W, POSTER_H), (0, 0, 0))
    draw = ImageDraw.Draw(bg)

    # Vertical gradient: lighter at top, darker at bottom
    for y in range(POSTER_H):
        progress = y / POSTER_H
        brightness = 0.55 * (1 - progress ** 0.8) + 0.08
        sat_factor = 1.0 - 0.3 * progress
        line_r = int(r * brightness * sat_factor)
        line_g = int(g * brightness * sat_factor)
        line_b = int(b * brightness * sat_factor)
        draw.line([(0, y), (POSTER_W, y)], fill=(line_r, line_g, line_b))

    # Radial highlight in upper center
    highlight = Image.new("RGBA", (POSTER_W, POSTER_H), (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    cx, cy = POSTER_W // 2, int(POSTER_H * 0.30)
    radius = int(POSTER_W * 0.6)
    for dist in range(radius, 0, -2):
        alpha = int(40 * (1 - dist / radius) ** 2)
        hd.ellipse([(cx - dist, cy - dist), (cx + dist, cy + dist)], fill=(r, g, b, alpha))
    bg = Image.alpha_composite(bg.convert("RGBA"), highlight).convert("RGB")

    # Subtle noise grain
    noise = np.random.default_rng(42).normal(0, 3, (POSTER_H, POSTER_W, 3)).astype(np.int16)
    bg_arr = np.array(bg, dtype=np.int16) + noise
    bg_arr = np.clip(bg_arr, 0, 255).astype(np.uint8)
    bg = Image.fromarray(bg_arr)

    return bg


def _center_sharp(frame: Image.Image, max_display: int) -> tuple[Image.Image, int, int]:
    """Scale and center a sharp image in the upper poster area."""
    scale = min(max_display / frame.width, max_display / frame.height)
    new_w = int(frame.width * scale)
    new_h = int(frame.height * scale)
    sharp = frame.resize((new_w, new_h), Image.LANCZOS)
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


def _make_collage_bg(thumb_paths: list[Path]) -> Image.Image:
    """Create a collage background from multiple thumbnails.

    Overlapping semi-transparent images create an atmospheric festival texture.
    Uses a seeded RNG for reproducible layouts.
    """
    rng = np.random.default_rng(42)

    # Start with a subtle gradient background derived from thumb colors
    base_color = get_dominant_color_from_thumbs(thumb_paths)
    gradient_bg = _make_gradient_bg(base_color)
    bg = gradient_bg.convert("RGBA")
    # Darken the gradient so it sits behind the collage images
    darken = Image.new("RGBA", (POSTER_W, POSTER_H), (0, 0, 0, 100))
    bg = Image.alpha_composite(bg, darken)

    # Pick up to 6 thumbs, evenly spaced through the list for variety
    paths = list(thumb_paths)
    if len(paths) > 6:
        step = len(paths) / 6
        paths = [paths[int(i * step)] for i in range(6)]

    # Composition using rule of thirds with foreground/background layering.
    # Third lines at 1/3 and 2/3 of poster width (333, 667) and usable height.
    # Background layer: larger, dimmer images placed first.
    # Foreground layer: smaller, brighter images on top.
    n = len(paths)
    max_bottom = LINE_Y - 80

    # Split into background (first half) and foreground (second half)
    bg_count = max(n // 2, 1)
    fg_count = n - bg_count

    # Scale image sizes based on thumb count — fewer thumbs = larger images
    if n <= 2:
        bg_scale, fg_scale = 0.85, 0.75
    elif n <= 4:
        bg_scale, fg_scale = 0.75, 0.60
    else:
        bg_scale, fg_scale = 0.70, 0.55

    bg_size_w = int(POSTER_W * bg_scale)
    bg_size_h = int(bg_size_w * 9 / 16)
    fg_size_w = int(POSTER_W * fg_scale)
    fg_size_h = int(fg_size_w * 9 / 16)

    # Layout slots based on rule of thirds
    # Vertical offset to center the image mass between top and text line
    y_offset = 0.08

    if n <= 2:
        bg_slots = [
            (0.08, y_offset + 0.05),
            (0.15, y_offset + 0.30),
        ]
        fg_slots = bg_slots
    elif n <= 4:
        bg_slots = [
            (0.0, y_offset + 0.0),
            (0.25, y_offset + 0.22),
        ]
        fg_slots = [
            (0.10, y_offset + 0.38),
            (0.30, y_offset + 0.08),
        ]
    else:
        bg_slots = [
            (0.02, y_offset + 0.0),
            (0.30, y_offset + 0.15),
            (0.05, y_offset + 0.35),
        ]
        fg_slots = [
            (0.25, y_offset + 0.05),
            (0.0, y_offset + 0.22),
            (0.20, y_offset + 0.42),
        ]

    layers = []
    for i, path in enumerate(paths):
        is_bg = i < bg_count
        size_w = bg_size_w if is_bg else fg_size_w
        size_h = bg_size_h if is_bg else fg_size_h
        slots = bg_slots if is_bg else fg_slots
        slot_idx = i if is_bg else (i - bg_count)
        slot = slots[slot_idx % len(slots)]

        layers.append((path, size_w, size_h, slot, is_bg))

    for path, size_w, size_h, slot, is_bg in layers:
        try:
            img = Image.open(path).convert("RGBA")
        except (OSError, ValueError):
            continue

        # Crop to center portion and resize
        src_w, src_h = img.size
        crop_w = int(src_w * 0.7)
        crop_h = int(src_h * 0.7)
        cx, cy = src_w // 2, src_h // 2
        ox = int(rng.integers(-src_w // 10, src_w // 10))
        oy = int(rng.integers(-src_h // 10, src_h // 10))
        left = max(0, cx + ox - crop_w // 2)
        top = max(0, cy + oy - crop_h // 2)
        right = min(src_w, left + crop_w)
        bottom = min(src_h, top + crop_h)
        img = img.crop((left, top, right, bottom))
        img = img.resize((size_w, size_h), Image.LANCZOS)

        # Oval mask first — applied on clean rectangle before rotation
        max_opacity = 180 if is_bg else 240
        iw, ih = img.size
        ys = np.arange(ih, dtype=np.float64)
        xs = np.arange(iw, dtype=np.float64)
        ecx, ecy = iw / 2, ih / 2
        rx, ry = iw / 2, ih / 2
        yy = ((ys - ecy) / ry)[:, None].repeat(iw, axis=1)
        xx = ((xs - ecx) / rx)[None, :].repeat(ih, axis=0)
        ellipse_dist = np.sqrt(yy ** 2 + xx ** 2)
        mask_arr = np.clip(1.0 - (ellipse_dist - 0.45) / 0.55, 0, 1)
        mask_arr = (mask_arr ** 1.3 * max_opacity).astype(np.uint8)
        edge_mask = Image.fromarray(mask_arr, mode="L")
        edge_mask = edge_mask.filter(ImageFilter.GaussianBlur(radius=15))

        # Darken the image pixels at the edges so bright content doesn't bleed through
        # the semi-transparent feather zone
        darken_arr = np.clip(1.0 - (ellipse_dist - 0.35) / 0.65, 0, 1)
        darken_arr = darken_arr ** 0.8
        img_arr = np.array(img)
        for c in range(3):
            img_arr[:, :, c] = (img_arr[:, :, c] * darken_arr).astype(np.uint8)
        img = Image.fromarray(img_arr)
        img.putalpha(edge_mask)

        # Rotation last — tilts the oval, transparent corners blend naturally
        angle = float(rng.uniform(-3, 3))
        img = img.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))

        # Position from slot + slight jitter
        min_top = size_h // 6
        x = int(slot[0] * POSTER_W) + int(rng.integers(-15, 15))
        y = int(slot[1] * max_bottom) + int(rng.integers(-10, 10))
        x = max(-size_w // 4, min(x, POSTER_W - size_w // 2))
        y = max(min_top, min(y, max_bottom - size_h))

        bg.paste(img, (x, y), img)

    # Dark gradient overlay from 45% down
    gradient = Image.new("RGBA", (POSTER_W, POSTER_H), (0, 0, 0, 0))
    dg = ImageDraw.Draw(gradient)
    grad_start = int(POSTER_H * 0.40)
    for y in range(grad_start, POSTER_H):
        progress = (y - grad_start) / (POSTER_H - grad_start)
        a = int(220 * progress ** 1.2)
        dg.line([(0, y), (POSTER_W, y)], fill=(0, 0, 0, a))
    bg = Image.alpha_composite(bg, gradient)

    return bg.convert("RGB")


def generate_album_poster(
    output_path: Path,
    festival: str,
    date_or_year: str,
    detail: str = "",
    thumb_paths: list[Path] | None = None,
    override_color: tuple[int, int, int] | None = None,
    background_image_path: Path | None = None,
    background_source: str = "",
    hero_text: str | None = None,
) -> Path:
    """Generate an album poster.

    Uses a background image if provided (sharp top + fade, like set posters),
    otherwise falls back to an editorial gradient derived from thumbnail colors.

    For artist folders: pass hero_text="Artist Name" to show just the artist name.
    For festival folders: hero_text defaults to festival name with date/detail below.

    Args:
        output_path: Where to save the poster
        festival: Festival name (used as hero text if hero_text not set)
        date_or_year: Date or year string for display
        detail: Optional detail (venue, location)
        thumb_paths: Thumbnail images for color derivation
        override_color: Override the auto-derived color
        background_image_path: Optional background image (curated logo, fanart, DJ artwork)
        background_source: Name of the source that provided the background (for logging)
        hero_text: Override the hero text above the accent line (e.g. artist name)

    Returns:
        Path to the generated poster
    """
    if background_image_path and background_image_path.exists():
        # Background image provided (curated logo, fanart, DJ artwork)
        try:
            frame_raw = Image.open(background_image_path)
            has_alpha = frame_raw.mode in ("RGBA", "LA", "PA")

            # Derive base color for gradient: logo pixels, or thumbnails if too dark
            base_color = override_color or _visible_pixel_color(frame_raw)
            if _pixel_luminance(base_color) < 30 and thumb_paths:
                base_color = get_dominant_color_from_thumbs(thumb_paths)
            elif _pixel_luminance(base_color) < 30:
                base_color = (40, 40, 50)

            # Gradient base layer — always the foundation
            bg = _make_gradient_bg(base_color)
            accent = _accent_from_base(base_color)

            # Flatten for blur/tile operations
            frame_rgb = _flatten_alpha(frame_raw, base_color) if has_alpha else frame_raw.convert("RGB")
            is_small_source = frame_raw.width < 600

            if is_small_source and hero_text is None:
                # Festival layout: ratio-preserving tiled pattern + centered sharp logo
                logger.info("Layout: festival tiled pattern")
                logger.debug("Layout: source %dx%d from %s", frame_raw.width, frame_raw.height, background_source or "unknown")
                tile_max = 200
                w, h = frame_rgb.size
                tile_scale = tile_max / max(w, h)
                tile_w = max(1, int(w * tile_scale))
                tile_h = max(1, int(h * tile_scale))
                tile = frame_rgb.resize((tile_w, tile_h), Image.LANCZOS)

                pattern = Image.new("RGB", (POSTER_W, LINE_Y))
                for x in range(0, POSTER_W, tile_w):
                    for y in range(0, LINE_Y, tile_h):
                        pattern.paste(tile, (x, y))

                pattern = ImageEnhance.Brightness(pattern).enhance(0.30)
                pattern_rgba = pattern.convert("RGBA")

                # Fade alpha: in from top, out toward bottom
                alpha_band = Image.new("L", (POSTER_W, LINE_Y), 0)
                ad = ImageDraw.Draw(alpha_band)
                for y in range(LINE_Y):
                    if y < LINE_Y * 0.1:
                        a = int(150 * y / (LINE_Y * 0.1))
                    elif y < LINE_Y * 0.6:
                        a = 150
                    else:
                        a = int(150 * (1 - (y - LINE_Y * 0.6) / (LINE_Y * 0.4)))
                    ad.line([(0, y), (POSTER_W, y)], fill=a)
                pattern_rgba.putalpha(alpha_band)
                bg = bg.convert("RGBA")
                bg.paste(pattern_rgba, (0, 0), pattern_rgba)

                # Sharp logo centered — use RGBA for transparent logos
                max_display = 420
                if has_alpha:
                    sharp, img_x, img_y = _center_sharp(frame_raw.convert("RGBA"), max_display)
                    bg.paste(sharp, (img_x, img_y), sharp)
                else:
                    sharp, img_x, img_y = _center_sharp(frame_rgb, max_display)
                    mask = _rounded_edge_mask(sharp.size[0], sharp.size[1])
                    bg.paste(sharp, (img_x, img_y), mask)
                bg = bg.convert("RGB")

            elif is_small_source:
                # Artist layout: blurred overlay on gradient + centered sharp logo
                logger.info("Layout: artist centered on blur")
                logger.debug("Layout: source %dx%d from %s", frame_raw.width, frame_raw.height, background_source or "unknown")
                blurred = frame_rgb.resize((POSTER_W, POSTER_H), Image.LANCZOS)
                blurred = blurred.filter(ImageFilter.GaussianBlur(radius=40))
                blurred = ImageEnhance.Brightness(blurred).enhance(0.18)
                blurred_rgba = blurred.convert("RGBA")
                blurred_rgba.putalpha(Image.new("L", (POSTER_W, POSTER_H), 150))
                bg = Image.alpha_composite(bg.convert("RGBA"), blurred_rgba)

                max_display = 550
                if has_alpha:
                    sharp, img_x, img_y = _center_sharp(frame_raw.convert("RGBA"), max_display)
                    bg.paste(sharp, (img_x, img_y), sharp)
                else:
                    sharp, img_x, img_y = _center_sharp(frame_rgb, max_display)
                    mask = _rounded_edge_mask(sharp.size[0], sharp.size[1])
                    bg.paste(sharp, (img_x, img_y), mask)
                bg = bg.convert("RGB")

            else:
                # Large source: sharp top on gradient, fade to dark
                logger.info("Layout: large source with fade")
                logger.debug("Layout: source %dx%d from %s", frame_raw.width, frame_raw.height, background_source or "unknown")
                scale = POSTER_W / frame_raw.width
                new_h = int(frame_raw.height * scale)
                fade_mask = Image.new("L", (POSTER_W, new_h), 255)
                dm = ImageDraw.Draw(fade_mask)
                fade_start = int(new_h * 0.60)
                for y in range(fade_start, new_h):
                    alpha = int(255 * (1 - (y - fade_start) / (new_h - fade_start)))
                    dm.line([(0, y), (POSTER_W, y)], fill=alpha)

                if has_alpha:
                    sharp_rgba = frame_raw.convert("RGBA").resize((POSTER_W, new_h), Image.LANCZOS)
                    orig_alpha = sharp_rgba.split()[3]
                    combined = Image.fromarray(
                        np.minimum(np.array(orig_alpha), np.array(fade_mask)), mode="L"
                    )
                    sharp_rgba.putalpha(combined)
                    bg = bg.convert("RGBA")
                    bg.paste(sharp_rgba, (0, 0), sharp_rgba)
                    bg = bg.convert("RGB")
                else:
                    sharp = frame_rgb.resize((POSTER_W, new_h), Image.LANCZOS)
                    bg.paste(sharp, (0, 0), fade_mask)

            # Dark gradient overlay from 40% down
            gradient = Image.new("RGBA", (POSTER_W, POSTER_H), (0, 0, 0, 0))
            dg = ImageDraw.Draw(gradient)
            grad_start = int(POSTER_H * 0.40)
            for y in range(grad_start, POSTER_H):
                progress = (y - grad_start) / (POSTER_H - grad_start)
                a = int(200 * progress ** 1.4)
                dg.line([(0, y), (POSTER_W, y)], fill=(0, 0, 0, a))
            bg = Image.alpha_composite(bg.convert("RGBA"), gradient).convert("RGB")
        except (OSError, ValueError) as e:
            logger.warning("Could not use background image %s: %s", background_image_path, e)
            background_image_path = None  # fall through to gradient

    if not background_image_path or not background_image_path.exists():
        is_festival = hero_text is None
        if is_festival and thumb_paths and len(thumb_paths) >= 2:
            # Festival folder with multiple thumbs: use collage
            logger.info("Layout: festival collage (%d thumbnails)", len(thumb_paths))
            bg = _make_collage_bg(thumb_paths)
            accent = get_accent_color(bg)
        else:
            # Gradient fallback
            logger.info("Layout: gradient fallback")
            base_color = override_color or get_dominant_color_from_thumbs(thumb_paths or [])
            accent = _accent_from_base(base_color)
            bg = _make_gradient_bg(base_color)
    draw = ImageDraw.Draw(bg)
    max_w = POSTER_W - 100

    # Determine hero text: artist name for artist folders, festival for festival folders
    display_text = (hero_text or festival).upper()
    is_artist_poster = hero_text is not None

    font_hero, _ = auto_fit(display_text, "bold", max_w, start=130, minimum=60)

    # Hero text above line
    hero_h = font_visual_height(font_hero)
    hero_y = LINE_Y - PAD_LINE_TO_FEST - hero_h
    spacing = max(2, min(14, (max_w - measure_w(font_hero, display_text)) // max(len(display_text), 1)))
    _draw_centered_no_shadow(draw, hero_y, display_text, font_hero, "white", letter_spacing=spacing)

    # Accent line with glow
    bg = _draw_glow_line(bg, LINE_Y, 400, LINE_H, accent, glow_radius=16)
    draw = ImageDraw.Draw(bg)

    # Festival folders: show date + detail below the line
    # Artist folders: nothing below the line — the image and name are enough
    if not is_artist_poster:
        font_date = get_font("semilight", 62)
        font_detail = get_font("semilight", 44)

        pad_line_to_date = 28
        ty = LINE_Y + LINE_H + pad_line_to_date
        if date_or_year:
            _draw_centered_no_shadow(draw, ty, date_or_year, font_date, "white")
            ty += font_visual_height(font_date) + PAD_YEAR_TO_DETAIL

        if detail:
            _draw_centered_no_shadow(draw, ty, detail, font_detail, "white")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bg.save(str(output_path), quality=95)
    return output_path
