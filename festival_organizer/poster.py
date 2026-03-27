"""Poster generation: set posters (v5b layout) and album posters (editorial gradient).

Set posters use embedded cover art or sampled frames as source image.
Album posters use gradient backgrounds derived from thumbnail colors.
Layout uses a line-anchored system: accent line at 2/3 down, artist builds UP, metadata builds DOWN.
"""
import re
from colorsys import hsv_to_rgb, rgb_to_hsv
from pathlib import Path

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

# Font paths (Windows)
FONT_PATHS = {
    "bold": "C:/Windows/Fonts/segoeuib.ttf",
    "light": "C:/Windows/Fonts/segoeuil.ttf",
    "semilight": "C:/Windows/Fonts/segoeuisl.ttf",
    "regular": "C:/Windows/Fonts/segoeui.ttf",
}


def get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a Segoe UI font variant by name."""
    try:
        return ImageFont.truetype(FONT_PATHS.get(name, name), size)
    except OSError:
        return ImageFont.truetype(FONT_PATHS["bold"], size)


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


def get_accent_color(img: Image.Image) -> tuple[int, int, int]:
    """Auto-derive accent color from source image mean HSV."""
    hsv = img.convert("HSV")
    stat = ImageStat.Stat(hsv)
    h = stat.mean[0] / 255
    s = min(1.0, stat.mean[1] / 160)
    v = 0.95
    r, g, b = hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def split_artist(name: str) -> tuple[str, str | None]:
    """Split artist name for two-line display.

    Priority:
    1. Parenthetical: "Act Name (Artist & Artist)" -> ("Act Name", "Artist & Artist")
    2. Connectors: & B2B vs x -> split at connector
    3. No split for band names like "Swedish House Mafia"
    """
    # 1. Parenthetical pattern
    paren_match = re.match(r'^(.+?)\s*\((.+)\)\s*$', name)
    if paren_match:
        return paren_match.group(1).strip(), paren_match.group(2).strip()
    # 2. Connectors
    upper = name.upper()
    for sep in [" & ", " B2B ", " VS ", " X "]:
        if sep in upper:
            idx = upper.index(sep)
            return name[:idx].strip(), name[idx:].strip()
    # 3. No split
    return name, None


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
    frame = Image.open(source_image_path).convert("RGB")
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

    # Split artist name
    line1, line2 = split_artist(artist)
    line1_upper = line1.upper()
    line2_upper = line2.upper() if line2 else None

    # Auto-fit fonts
    font_artist1, _ = auto_fit(line1_upper, "bold", max_w, start=110, minimum=50)
    font_artist2 = None
    if line2_upper:
        font_artist2, _ = auto_fit(line2_upper, "bold", max_w, start=110, minimum=50)
    font_fest, _ = auto_fit(festival.upper(), "bold", max_w, start=68, minimum=36)
    font_year = get_font("light", 52)
    font_detail = get_font("semilight", 36)

    # BUILD UP from accent line
    if line2_upper:
        h2 = font_visual_height(font_artist2)
        artist2_y = LINE_Y - PAD_LINE_TO_ARTIST - h2

        h1 = font_visual_height(font_artist1)
        artist1_y = artist2_y - PAD_ARTIST_LINES - h1

        sp1 = max(2, min(8, (max_w - measure_w(font_artist1, line1_upper)) // max(len(line1_upper), 1)))
        _draw_centered(draw, artist1_y, line1_upper, font_artist1, "white", letter_spacing=sp1)

        sp2 = max(2, min(8, (max_w - measure_w(font_artist2, line2_upper)) // max(len(line2_upper), 1)))
        _draw_centered(draw, artist2_y, line2_upper, font_artist2, "white", letter_spacing=sp2)
    else:
        h1 = font_visual_height(font_artist1)
        artist1_y = LINE_Y - PAD_LINE_TO_ARTIST - h1

        sp = max(2, min(10, (max_w - measure_w(font_artist1, line1_upper)) // max(len(line1_upper), 1)))
        _draw_centered(draw, artist1_y, line1_upper, font_artist1, "white", letter_spacing=sp)

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

    # Date/Year line
    date_display = format_date_display(date, year)
    if date_display:
        year_h = font_visual_height(font_year)
        bg = _draw_glow_text(bg, ty, date_display, font_year, accent, accent, glow_radius=14)
        draw = ImageDraw.Draw(bg)
        ty += year_h + PAD_YEAR_TO_DETAIL

    # Detail line
    if detail:
        _draw_centered(draw, ty, detail, font_detail, (170, 170, 170))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bg.save(str(output_path), quality=95)
    return output_path


# --- Album poster generation ---

def get_dominant_color_from_thumbs(thumb_paths: list[Path]) -> tuple[int, int, int]:
    """Get average color from thumbnail images."""
    if not thumb_paths:
        return (40, 80, 180)  # default blue

    total_h, total_s, total_v = 0.0, 0.0, 0.0
    valid = 0
    for path in thumb_paths:
        try:
            img = Image.open(path).convert("HSV")
            stat = ImageStat.Stat(img)
            total_h += stat.mean[0]
            total_s += stat.mean[1]
            total_v += stat.mean[2]
            valid += 1
        except Exception:
            continue

    if valid == 0:
        return (40, 80, 180)

    h = total_h / valid / 255
    s = min(0.7, total_s / valid / 255)
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
) -> Path:
    """Generate an album poster (editorial gradient, no image).

    Args:
        output_path: Where to save the poster
        festival: Festival name (hero text)
        date_or_year: Date or year string for display
        detail: Optional detail (venue, location)
        thumb_paths: Thumbnail images for color derivation
        override_color: Override the auto-derived color

    Returns:
        Path to the generated poster
    """
    base_color = override_color or get_dominant_color_from_thumbs(thumb_paths or [])
    accent = _accent_from_base(base_color)

    bg = _make_gradient_bg(base_color)
    draw = ImageDraw.Draw(bg)
    max_w = POSTER_W - 100
    fest_upper = festival.upper()

    font_fest, _ = auto_fit(fest_upper, "bold", max_w, start=130, minimum=60)
    font_date = get_font("light", 52)
    font_detail = get_font("semilight", 36)

    # Festival above line (no drop shadow on album posters)
    fest_h = font_visual_height(font_fest)
    fest_y = LINE_Y - PAD_LINE_TO_FEST - fest_h
    spacing = max(2, min(14, (max_w - measure_w(font_fest, fest_upper)) // max(len(fest_upper), 1)))
    _draw_centered_no_shadow(draw, fest_y, fest_upper, font_fest, "white", letter_spacing=spacing)

    # Accent line with glow
    bg = _draw_glow_line(bg, LINE_Y, 400, LINE_H, accent, glow_radius=16)
    draw = ImageDraw.Draw(bg)

    # Date with glow
    pad_line_to_date = 28
    ty = LINE_Y + LINE_H + pad_line_to_date
    bg = _draw_glow_text(bg, ty, date_or_year, font_date, accent, accent, glow_radius=16)
    draw = ImageDraw.Draw(bg)
    ty += font_visual_height(font_date) + PAD_YEAR_TO_DETAIL

    # Detail
    if detail:
        _draw_centered_no_shadow(draw, ty, detail, font_detail, (170, 170, 170))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bg.save(str(output_path), quality=95)
    return output_path
