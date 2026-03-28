"""Poster generation: set posters (v5b layout) and album posters (editorial gradient).

Set posters use embedded cover art or sampled frames as source image.
Album posters use gradient backgrounds derived from thumbnail colors.
Layout uses a line-anchored system: accent line at 2/3 down, artist builds UP, metadata builds DOWN.
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


# --- Set poster generation ---

def generate_set_poster(
    source_image_path: Path,
    output_path: Path,
    artist: str,
    festival: str,
    date: str = "",
    year: str = "",
    detail: str = "",
) -> Path:
    """Generate a set poster (per-video) using the v5b line-anchored layout.

    Args:
        source_image_path: Path to cover art or sampled frame image
        output_path: Where to save the poster
        artist: Artist name
        festival: Festival display name (already resolved with location)
        date: ISO date string (YYYY-MM-DD) for full date display
        year: Year string as fallback
        detail: Optional detail line (stage, venue)

    Returns:
        Path to the generated poster
    """
    try:
        frame = Image.open(source_image_path).convert("RGB")
    except (OSError, ValueError) as e:
        raise OSError(f"Cannot open source image {source_image_path}: {e}") from e
    accent = get_accent_color(frame)

    # Blurred + darkened background fills entire poster
    bg = frame.resize((POSTER_W, POSTER_H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=40))
    bg = ImageEnhance.Brightness(bg).enhance(0.18)

    # Sharp image flush to top (img_y = 0)
    scale = POSTER_W / frame.width
    new_h = int(frame.height * scale)
    sharp = frame.resize((POSTER_W, new_h), Image.LANCZOS)

    img_y = 0
    # Fade mask starting at 60% of image height
    mask = Image.new("L", (POSTER_W, new_h), 255)
    dm = ImageDraw.Draw(mask)
    fade_start = int(new_h * 0.60)
    for y in range(fade_start, new_h):
        alpha = int(255 * (1 - (y - fade_start) / (new_h - fade_start)))
        dm.line([(0, y), (POSTER_W, y)], fill=alpha)
    bg.paste(sharp, (0, img_y), mask)

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
    font_detail = get_font("semilight", 44)

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

    # Detail line — white, no effects for TV readability
    if detail:
        _draw_centered_no_shadow(draw, ty, detail, font_detail, "white")

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


def generate_album_poster(
    output_path: Path,
    festival: str,
    date_or_year: str,
    detail: str = "",
    thumb_paths: list[Path] | None = None,
    override_color: tuple[int, int, int] | None = None,
    background_image_path: Path | None = None,
) -> Path:
    """Generate an album poster.

    Uses a background image if provided (blurred + darkened like set posters),
    otherwise falls back to an editorial gradient derived from thumbnail colors.

    Args:
        output_path: Where to save the poster
        festival: Festival name (hero text)
        date_or_year: Date or year string for display
        detail: Optional detail (venue, location)
        thumb_paths: Thumbnail images for color derivation
        override_color: Override the auto-derived color
        background_image_path: Optional fanart.tv background image

    Returns:
        Path to the generated poster
    """
    if background_image_path and background_image_path.exists():
        # Use fanart background: blur + darken, similar to set poster
        try:
            frame = Image.open(background_image_path).convert("RGB")
            accent = get_accent_color(frame)

            bg = frame.resize((POSTER_W, POSTER_H), Image.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(radius=20))
            bg = ImageEnhance.Brightness(bg).enhance(0.40)

            # Dark gradient overlay from 40% down
            gradient = Image.new("RGBA", (POSTER_W, POSTER_H), (0, 0, 0, 0))
            dg = ImageDraw.Draw(gradient)
            grad_start = int(POSTER_H * 0.40)
            for y in range(grad_start, POSTER_H):
                progress = (y - grad_start) / (POSTER_H - grad_start)
                a = int(180 * progress ** 1.4)
                dg.line([(0, y), (POSTER_W, y)], fill=(0, 0, 0, a))
            bg = Image.alpha_composite(bg.convert("RGBA"), gradient).convert("RGB")
        except (OSError, ValueError) as e:
            logger.warning("Could not use background image %s: %s", background_image_path, e)
            background_image_path = None  # fall through to gradient

    if not background_image_path or not background_image_path.exists():
        base_color = override_color or get_dominant_color_from_thumbs(thumb_paths or [])
        accent = _accent_from_base(base_color)
        bg = _make_gradient_bg(base_color)
    draw = ImageDraw.Draw(bg)
    max_w = POSTER_W - 100
    fest_upper = festival.upper()

    font_fest, _ = auto_fit(fest_upper, "bold", max_w, start=130, minimum=60)
    font_date = get_font("semilight", 62)
    font_detail = get_font("semilight", 44)

    # Festival above line (no drop shadow on album posters)
    fest_h = font_visual_height(font_fest)
    fest_y = LINE_Y - PAD_LINE_TO_FEST - fest_h
    spacing = max(2, min(14, (max_w - measure_w(font_fest, fest_upper)) // max(len(fest_upper), 1)))
    _draw_centered_no_shadow(draw, fest_y, fest_upper, font_fest, "white", letter_spacing=spacing)

    # Accent line with glow
    bg = _draw_glow_line(bg, LINE_Y, 400, LINE_H, accent, glow_radius=16)
    draw = ImageDraw.Draw(bg)

    # Date — white, no effects for TV readability
    pad_line_to_date = 28
    ty = LINE_Y + LINE_H + pad_line_to_date
    _draw_centered_no_shadow(draw, ty, date_or_year, font_date, "white")
    ty += font_visual_height(font_date) + PAD_YEAR_TO_DETAIL

    # Detail — white, no effects for TV readability
    if detail:
        _draw_centered_no_shadow(draw, ty, detail, font_detail, "white")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bg.save(str(output_path), quality=95)
    return output_path
