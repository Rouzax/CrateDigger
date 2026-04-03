# Festival Album Poster Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the noisy tiled logo background on festival album posters with a clean gradient + centered logo layout, improve color extraction using brand colors, and split festival/edition text into two distinct lines.

**Architecture:** Modify `generate_album_poster()` in poster.py to remove the tiled pattern block and collage function, add a saturation-aware color extraction fallback, and restructure the text layout to show festival name + edition above the accent line with nothing below. Config changes add brand color overrides to `festivals.example.json`.

**Tech Stack:** Python, Pillow (PIL), NumPy, colorsys, pytest

---

### Task 1: Add `_hex_to_rgb()` and `_extract_logo_color()` helpers

**Files:**
- Modify: `festival_organizer/poster.py` (add after `_visible_pixel_color` at line 306)
- Test: `tests/test_poster.py`

**Step 1: Write failing tests**

Add to `tests/test_poster.py` imports:

```python
from festival_organizer.poster import _hex_to_rgb, _extract_logo_color
```

Add test functions:

```python
# --- hex parsing tests ---

def test_hex_to_rgb_with_hash():
    assert _hex_to_rgb("#EA0000") == (234, 0, 0)


def test_hex_to_rgb_without_hash():
    assert _hex_to_rgb("1C99D8") == (28, 153, 216)


# --- logo color extraction tests ---

def test_extract_logo_color_saturated():
    """Saturated logo returns a dark/moody color in the correct hue range."""
    img = Image.new("RGB", (100, 100), (200, 0, 0))
    color = _extract_logo_color(img)
    r, g, b = color
    # Should be reddish and dark (V ~0.4)
    assert r > g and r > b, f"Expected reddish, got {color}"
    assert r < 150, f"Expected dark, got {color}"


def test_extract_logo_color_with_alpha():
    """Transparent logo ignores invisible pixels."""
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.ellipse([10, 10, 90, 90], fill=(0, 0, 200, 255))
    color = _extract_logo_color(img)
    r, g, b = color
    assert b > r and b > g, f"Expected bluish, got {color}"


def test_extract_logo_color_unsaturated_raises():
    """Grayscale logo raises ValueError."""
    img = Image.new("RGB", (100, 100), (128, 128, 128))
    with pytest.raises(ValueError, match="No saturated pixels"):
        _extract_logo_color(img)


def test_extract_logo_color_white_raises():
    """White logo raises ValueError."""
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    with pytest.raises(ValueError, match="No saturated pixels"):
        _extract_logo_color(img)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_poster.py::test_hex_to_rgb_with_hash tests/test_poster.py::test_extract_logo_color_saturated -v`
Expected: FAIL with ImportError

**Step 3: Implement `_hex_to_rgb` and `_extract_logo_color`**

Add to `festival_organizer/poster.py` after the `_visible_pixel_color` function (after line 306):

```python
def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Parse a hex color string to an RGB tuple."""
    hex_str = hex_str.lstrip("#")
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
            raise ValueError("No saturated pixels found in logo")
        rgb_pixels = arr[:, :, :3][mask]
    else:
        arr = np.array(img.convert("RGB"))
        rgb_pixels = arr.reshape(-1, 3)

    # Convert to HSV using PIL for consistency with _circular_hue_mean
    h_list, s_list = [], []
    # Process in bulk: create a 1-pixel-high image strip
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_poster.py -k "hex_to_rgb or extract_logo" -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add festival_organizer/poster.py tests/test_poster.py
git commit -m "feat(poster): add _hex_to_rgb and _extract_logo_color helpers

Saturation-aware color extraction from logo images using circular hue
mean. Filters out white/black/gray pixels, returns dark/moody gradient
color. Falls back to ValueError when no saturated pixels found."
```

---

### Task 2: Add brand colors to festival config

**Files:**
- Modify: `festivals.example.json`

**Step 1: Update `festivals.example.json`**

Replace the `"config"` section with:

```json
"config": {
    "AMF": {
        "color": "#EA0000"
    },
    "A State Of Trance Festival": {
        "color": "#E63312"
    },
    "Dreamstate": {
        "editions": ["SoCal", "Europe", "Australia", "Mexico"],
        "color": "#1C99D8"
    },
    "EDC": {
        "editions": ["Las Vegas", "Mexico", "Orlando", "Thailand"],
        "color": "#ED3895"
    },
    "Mysteryland": {
        "color": "#FFFF7B"
    },
    "Red Rocks": {
        "color": "#C0392B"
    },
    "Tomorrowland": {
        "editions": ["Belgium", "Brasil", "Winter"],
        "color": "#9B1B5A",
        "edition_colors": {
            "Brasil": "#2A9D8F",
            "Winter": "#5B9BD5"
        }
    },
    "Ultra Music Festival": {
        "editions": ["Miami", "Europe", "Japan", "Korea", "Singapore", "South Africa", "Australia"],
        "color": "#0693E3"
    },
    "We Belong Here": {
        "editions": ["Miami", "Tulum"],
        "color": "#2EA3F2"
    }
}
```

**Step 2: Run existing config tests to verify nothing breaks**

Run: `pytest tests/test_config.py -v`
Expected: All pass (config loading is a pass-through for unknown keys)

**Step 3: Commit**

```bash
git add festivals.example.json
git commit -m "feat(config): add brand colors for all known festivals

Per-festival color hex for poster gradient derivation. Tomorrowland
uses edition_colors for Brasil (teal) and Winter (icy blue) to
differentiate from the main purple brand color."
```

---

### Task 3: Wire color override from config into poster generation

**Files:**
- Modify: `festival_organizer/operations.py:472-536`
- Modify: `festival_organizer/poster.py:711-760` (signature + color derivation)
- Test: `tests/test_poster.py`

**Step 1: Write failing test for `edition` parameter**

Add to `tests/test_poster.py`:

```python
def test_generate_album_poster_with_edition(tmp_path):
    """Album poster accepts edition parameter for two-line text layout."""
    logo = tmp_path / "logo.png"
    Image.new("RGB", (500, 500), (150, 30, 90)).save(str(logo))

    output = tmp_path / "poster.jpg"
    generate_album_poster(
        output_path=output,
        festival="Tomorrowland",
        date_or_year="2025",
        edition="Belgium",
        background_image_path=logo,
    )
    assert output.exists()
    with Image.open(output) as img:
        assert img.size == (POSTER_W, POSTER_H)


def test_generate_album_poster_no_edition(tmp_path):
    """Album poster works without edition (single-line text)."""
    output = tmp_path / "poster.jpg"
    generate_album_poster(
        output_path=output,
        festival="AMF",
        date_or_year="2025",
        override_color=(234, 0, 0),
    )
    assert output.exists()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_poster.py::test_generate_album_poster_with_edition -v`
Expected: FAIL with TypeError (unexpected keyword argument 'edition')

**Step 3: Add `edition` parameter to `generate_album_poster()`**

In `festival_organizer/poster.py`, modify the function signature at line 711:

```python
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
) -> Path:
```

Update the docstring to mention `edition`:

```python
    """Generate an album poster.

    Uses a background image if provided (sharp top + fade, like set posters),
    otherwise falls back to an editorial gradient derived from thumbnail colors.

    For artist folders: pass hero_text="Artist Name" to show just the artist name.
    For festival folders: hero_text defaults to festival name with edition below.

    Args:
        output_path: Where to save the poster
        festival: Festival name (used as hero text if hero_text not set)
        date_or_year: Date or year string for display
        detail: Optional detail (venue, stage)
        edition: Optional edition name (e.g. "Belgium", "Las Vegas")
        thumb_paths: Thumbnail images for color derivation
        override_color: Override the auto-derived color
        background_image_path: Optional background image (curated logo, fanart, DJ artwork)
        background_source: Name of the source that provided the background (for logging)
        hero_text: Override the hero text above the accent line (e.g. artist name)

    Returns:
        Path to the generated poster
    """
```

**Step 4: Update color derivation to use `_extract_logo_color` as fallback**

Replace lines 750-755 (the color derivation block inside the `background_image_path` branch):

Old:
```python
            # Derive base color for gradient: logo pixels, or thumbnails if too dark
            base_color = override_color or _visible_pixel_color(frame_raw)
            if _pixel_luminance(base_color) < 30 and thumb_paths:
                base_color = get_dominant_color_from_thumbs(thumb_paths)
            elif _pixel_luminance(base_color) < 30:
                base_color = (40, 40, 50)
```

New:
```python
            # Derive base color: config override > logo extraction > error
            if override_color:
                base_color = override_color
            else:
                base_color = _extract_logo_color(frame_raw)
```

**Step 5: Update operations.py to pass color and edition**

In `festival_organizer/operations.py`, in `AlbumPosterOperation.execute()` (around line 527), modify the code that calls `generate_album_poster`:

After line 514 (after `bg_path, bg_source = self._resolve_background(...)`), add color lookup:

```python
            # Look up brand color from festival config
            fc = self.config.festival_config.get(mf.festival, {})
            color_hex = fc.get("edition_colors", {}).get(mf.edition) or fc.get("color")
            if color_hex:
                from festival_organizer.poster import _hex_to_rgb
                override_color = _hex_to_rgb(color_hex)
            else:
                override_color = None
```

Modify the `generate_album_poster` call (lines 527-536):

```python
            generate_album_poster(
                output_path=folder_jpg,
                festival=mf.festival or mf.artist or "Unknown",
                date_or_year=date_or_year,
                detail=mf.stage or "",
                edition=mf.edition or "",
                thumb_paths=thumb_paths if thumb_paths else None,
                override_color=override_color,
                background_image_path=bg_path,
                background_source=bg_source,
                hero_text=hero_text,
            )
```

Note: `festival` now receives the canonical name (not `festival_display` which merged edition in). The `poster_title` variable is no longer needed for the festival path; keep it for the hero_text assignment on non-festival poster types. Update the `poster_title` usage:

For the festival case (line 522), change:
```python
            elif poster_type == "festival":
                hero_text = None
                poster_title = mf.festival or mf.artist or "Unknown"
```

The `poster_title` is no longer passed to `festival=` since we pass `mf.festival` directly. For artist/year paths, `poster_title` is still used for `festival=` parameter. Simplify by inlining:

```python
            if poster_type == "artist":
                hero_text = mf.artist
                poster_festival = festival_display or mf.artist or "Unknown"
            elif poster_type == "festival":
                hero_text = None
                poster_festival = mf.festival or mf.artist or "Unknown"
            else:  # year
                hero_text = date_or_year or mf.year
                poster_festival = festival_display or mf.artist or "Unknown"

            generate_album_poster(
                output_path=folder_jpg,
                festival=poster_festival,
                date_or_year=date_or_year,
                detail=mf.stage or "",
                edition=mf.edition or "",
                thumb_paths=thumb_paths if thumb_paths else None,
                override_color=override_color,
                background_image_path=bg_path,
                background_source=bg_source,
                hero_text=hero_text,
            )
```

**Step 6: Run tests**

Run: `pytest tests/test_poster.py tests/test_operations.py -v`
Expected: All pass

**Step 7: Commit**

```bash
git add festival_organizer/poster.py festival_organizer/operations.py tests/test_poster.py
git commit -m "feat(poster): wire edition parameter and config color override

Album poster accepts edition for two-line text layout. Operations
looks up brand color from festival config (edition_colors > color >
auto-extraction). Canonical festival name passed separately from
edition."
```

---

### Task 4: Remove tiled logo background and collage

**Files:**
- Modify: `festival_organizer/poster.py:552-708` (remove `_make_collage_bg`)
- Modify: `festival_organizer/poster.py:765-797` (remove tiled block)
- Modify: `festival_organizer/poster.py:871-883` (remove collage fallback)
- Test: `tests/test_poster.py`

**Step 1: Write test for gradient-only no-logo fallback**

Add to `tests/test_poster.py`:

```python
def test_generate_album_poster_no_logo_gradient_only(tmp_path):
    """Festival without logo gets gradient-only poster (no collage)."""
    thumbs = []
    for i in range(4):
        t = tmp_path / f"thumb_{i}.png"
        Image.new("RGB", (320, 180), (100 + i * 20, 50, 200)).save(str(t))
        thumbs.append(t)

    output = tmp_path / "poster.jpg"
    generate_album_poster(
        output_path=output,
        festival="Mysteryland",
        date_or_year="2025",
        thumb_paths=thumbs,
        override_color=(255, 255, 123),
    )
    assert output.exists()
    with Image.open(output) as img:
        assert img.size == (POSTER_W, POSTER_H)
```

**Step 2: Remove `_make_collage_bg` function**

Delete lines 552-708 in `festival_organizer/poster.py` (the entire `_make_collage_bg` function).

**Step 3: Remove tiled logo block**

In the `generate_album_poster` function, find the block gated by `if is_small_source and hero_text is None:` (around line 765 after prior edits shifted things). Replace the tiled pattern code with just the centered logo:

Remove the tiling section (the `tile_max`, `pattern`, `alpha_band`, `ImageEnhance.Brightness` block). Keep only the sharp logo compositing:

```python
            if is_small_source and hero_text is None:
                # Festival layout: gradient + centered sharp logo
                logger.info("Layout: festival gradient + logo")
                max_display = 420
                if has_alpha:
                    sharp, img_x, img_y = _center_sharp(frame_raw.convert("RGBA"), max_display)
                    bg = bg.convert("RGBA")
                    bg.paste(sharp, (img_x, img_y), sharp)
                    bg = bg.convert("RGB")
                else:
                    sharp, img_x, img_y = _center_sharp(frame_rgb, max_display)
                    mask = _rounded_edge_mask(sharp.size[0], sharp.size[1])
                    bg.paste(sharp, (img_x, img_y), mask)
```

**Step 4: Remove collage fallback**

In the no-background fallback section (the `if not background_image_path` block), remove the collage branch:

Old:
```python
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
```

New:
```python
    if not background_image_path or not background_image_path.exists():
        # Gradient fallback (no background image available)
        logger.info("Layout: gradient fallback")
        base_color = override_color or get_dominant_color_from_thumbs(thumb_paths or [])
        accent = _accent_from_base(base_color)
        bg = _make_gradient_bg(base_color)
```

**Step 5: Update the existing dark logo test**

The test `test_generate_album_poster_dark_logo_uses_thumbs` relied on the thumbnail fallback which is now removed. Replace it:

```python
def test_generate_album_poster_dark_logo_uses_override(tmp_path):
    """Dark logo with config color override produces a visible poster."""
    logo = tmp_path / "logo.png"
    # Black on transparent
    img = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.rectangle([100, 100, 400, 400], fill=(0, 0, 0, 255))
    img.save(str(logo))

    output = tmp_path / "poster.jpg"
    generate_album_poster(
        output_path=output,
        festival="Dark Fest",
        date_or_year="2025",
        background_image_path=logo,
        override_color=(100, 50, 200),
    )
    assert output.exists()
    with Image.open(output) as result:
        import numpy as np
        arr = np.array(result)
        mean_brightness = arr.mean()
        assert mean_brightness > 10, f"Poster too dark ({mean_brightness:.1f})"
```

**Step 6: Update the thumbs-only test**

`test_generate_album_poster_with_thumbs` previously triggered the collage path. It now hits the gradient fallback. It should still pass since it only checks size, but verify:

Run: `pytest tests/test_poster.py::test_generate_album_poster_with_thumbs -v`

**Step 7: Remove unused imports**

If `_make_collage_bg` was the only user of any imports, remove them. Check: `ImageStat` might only be used by collage. Verify with grep.

**Step 8: Run all tests**

Run: `pytest tests/test_poster.py -v`
Expected: All pass

**Step 9: Commit**

```bash
git add festival_organizer/poster.py tests/test_poster.py
git commit -m "refactor(poster): remove tiled logo background and collage

Festival album posters now use gradient + centered logo. The tiled
pattern block and _make_collage_bg function are removed entirely.
No-logo fallback is gradient-only. Dark logo test updated to use
config color override instead of thumbnail fallback."
```

---

### Task 5: Restructure text layout (festival name + edition above accent line)

**Files:**
- Modify: `festival_organizer/poster.py` (text rendering section, ~lines 887-916 after prior edits)
- Test: `tests/test_poster.py`

**Step 1: Write failing test for two-line text layout**

Add to `tests/test_poster.py`:

```python
def test_generate_album_poster_edition_text_layout(tmp_path):
    """Festival poster with edition shows two text lines above accent line."""
    logo = tmp_path / "logo.png"
    img = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.ellipse([50, 50, 450, 450], fill=(155, 27, 90, 255))
    img.save(str(logo))

    output = tmp_path / "poster.jpg"
    generate_album_poster(
        output_path=output,
        festival="Tomorrowland",
        date_or_year="2025",
        edition="Belgium",
        background_image_path=logo,
    )
    assert output.exists()
    with Image.open(output) as result:
        assert result.size == (POSTER_W, POSTER_H)
        # Verify nothing is rendered below the accent line area
        # The bottom third should be mostly dark gradient
        import numpy as np
        arr = np.array(result)
        bottom_strip = arr[LINE_Y + 50:, :]
        mean_bottom = bottom_strip.mean()
        # Bottom should be dark (no text rendered there)
        assert mean_bottom < 40, f"Bottom area too bright ({mean_bottom:.1f}), text may be below accent line"
```

Also import `LINE_Y` in the test file header (already imported via `POSTER_W, POSTER_H`; add `LINE_Y`):

```python
from festival_organizer.poster import (
    split_artist,
    get_accent_color,
    auto_fit,
    format_date_display,
    generate_set_poster,
    generate_album_poster,
    _filter_venue_parts,
    _hex_to_rgb,
    _extract_logo_color,
    POSTER_W,
    POSTER_H,
    LINE_Y,
)
```

**Step 2: Restructure text rendering in `generate_album_poster`**

Replace the text section (from `display_text` through the end of the `if not is_artist_poster` block):

```python
    # Determine hero text: artist name for artist folders, festival for festival folders
    display_text = (hero_text or festival).upper()
    is_artist_poster = hero_text is not None

    font_hero, _ = auto_fit(display_text, "bold", max_w, start=130, minimum=60)

    # Hero text above line
    hero_h = font_visual_height(font_hero)
    spacing = max(2, min(14, (max_w - measure_w(font_hero, display_text)) // max(len(display_text), 1)))

    if not is_artist_poster and edition:
        # Two lines: festival name + edition above accent line
        font_edition = get_font("semilight", 48)
        edition_h = font_visual_height(font_edition)
        pad_between = 12
        total_block = hero_h + pad_between + edition_h
        hero_y = LINE_Y - PAD_LINE_TO_FEST - total_block
        _draw_centered_no_shadow(draw, hero_y, display_text, font_hero, "white", letter_spacing=spacing)
        edition_y = hero_y + hero_h + pad_between
        _draw_centered_no_shadow(draw, edition_y, edition, font_edition, "white")
    else:
        # Single line: festival name (or artist name)
        hero_y = LINE_Y - PAD_LINE_TO_FEST - hero_h
        _draw_centered_no_shadow(draw, hero_y, display_text, font_hero, "white", letter_spacing=spacing)

    # Accent line with glow
    bg = _draw_glow_line(bg, LINE_Y, 400, LINE_H, accent, glow_radius=16)
    draw = ImageDraw.Draw(bg)

    # No text below accent line for festival posters
    # Artist posters also have no text below (unchanged behavior)
```

This removes the entire `if not is_artist_poster:` block that rendered `date_or_year` and `detail` below the accent line.

**Step 3: Run all tests**

Run: `pytest tests/test_poster.py -v`
Expected: All pass

**Step 4: Commit**

```bash
git add festival_organizer/poster.py tests/test_poster.py
git commit -m "feat(poster): two-line text layout for festival album posters

Festival name (bold, uppercase, auto-fitted) and edition (semilight,
48pt) rendered above the accent line. Nothing below the accent line.
Festivals without editions get a single line."
```

---

### Task 6: Derive gradient from brand color (darken to V=0.4)

**Files:**
- Modify: `festival_organizer/poster.py` (color derivation in `generate_album_poster`)
- Test: `tests/test_poster.py`

**Step 1: Write test for brand color darkening**

Add to `tests/test_poster.py`:

```python
def test_generate_album_poster_brand_color_darkened(tmp_path):
    """Bright brand color override is darkened for gradient, not used raw."""
    logo = tmp_path / "logo.png"
    Image.new("RGB", (500, 500), (150, 30, 90)).save(str(logo))

    output = tmp_path / "poster.jpg"
    # Pass bright red as override; gradient should be dark red, not bright
    generate_album_poster(
        output_path=output,
        festival="AMF",
        date_or_year="2025",
        override_color=(234, 0, 0),
        background_image_path=logo,
    )
    assert output.exists()
    with Image.open(output) as result:
        import numpy as np
        arr = np.array(result)
        # Sample top center area (gradient zone)
        top_strip = arr[50:150, 300:700]
        mean_r = top_strip[:, :, 0].mean()
        # Should be darkened, not bright red
        assert mean_r < 150, f"Gradient too bright ({mean_r:.0f}), brand color not darkened"
```

**Step 2: Add brand color darkening logic**

In `festival_organizer/poster.py`, add a helper after `_accent_from_base`:

```python
def _darken_brand_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Darken a brand color to a moody gradient base (V ~0.4)."""
    r, g, b = [c / 255 for c in color]
    h, s, v = rgb_to_hsv(r, g, b)
    # Keep hue, moderate saturation, dark value
    s = max(0.4, min(0.7, s))
    v = 0.4
    r2, g2, b2 = hsv_to_rgb(h, s, v)
    return (int(r2 * 255), int(g2 * 255), int(b2 * 255))
```

Then in `generate_album_poster`, update the color derivation to darken the override:

```python
            # Derive base color: config override > logo extraction > error
            if override_color:
                base_color = _darken_brand_color(override_color)
            else:
                base_color = _extract_logo_color(frame_raw)
```

Also update the no-background fallback to darken:

```python
    if not background_image_path or not background_image_path.exists():
        logger.info("Layout: gradient fallback")
        if override_color:
            base_color = _darken_brand_color(override_color)
        else:
            base_color = get_dominant_color_from_thumbs(thumb_paths or [])
        accent = _accent_from_base(base_color)
        bg = _make_gradient_bg(base_color)
```

**Step 3: Run tests**

Run: `pytest tests/test_poster.py -v`
Expected: All pass

**Step 4: Commit**

```bash
git add festival_organizer/poster.py tests/test_poster.py
git commit -m "feat(poster): darken brand colors for moody gradient backgrounds

Brand colors from config are converted to HSV and darkened to V=0.4
before use as gradient base. Keeps the hue recognizable while ensuring
the poster stays dark and the logo/text pop."
```

---

### Task 7: Clean up unused code and update imports

**Files:**
- Modify: `festival_organizer/poster.py` (remove unused imports/functions)
- Modify: `tests/test_poster.py` (update imports)

**Step 1: Check for unused imports**

Run: `grep -n "ImageStat" festival_organizer/poster.py` to see if `ImageStat` is still used anywhere.

Remove any unused imports (likely `ImageStat` and `ImageEnhance` if only used by the removed tiled/collage code).

Check: `grep -n "ImageEnhance" festival_organizer/poster.py` to verify usage.

**Step 2: Check if `_visible_pixel_color` is still used**

Run: `grep -n "_visible_pixel_color" festival_organizer/poster.py`

If it is only used for the festival color derivation (which is now replaced by `_extract_logo_color`), check if any other caller uses it. If not, leave it (it may still be useful for non-festival paths like artist posters). Do not remove if still referenced.

**Step 3: Run full test suite**

Run: `pytest -v`
Expected: All pass (528+ tests)

**Step 4: Commit**

```bash
git add festival_organizer/poster.py tests/test_poster.py
git commit -m "refactor(poster): clean up unused imports and code after redesign"
```

---

### Task 8: End-to-end verification

**Files:** None (verification only)

**Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

**Step 2: Generate sample posters for visual inspection**

Create a quick test script to generate posters for all 11 festivals using curated logos and brand colors:

```python
python3 -c "
from pathlib import Path
from festival_organizer.poster import generate_album_poster, _hex_to_rgb, _darken_brand_color

festivals = {
    'AMF': ('#EA0000', '', 'AMF'),
    'ASOT': ('#E63312', '', 'A State Of Trance Festival'),
    'Dreamstate': ('#1C99D8', 'SoCal', 'Dreamstate'),
    'EDC': ('#ED3895', 'Las Vegas', 'EDC'),
    'Red Rocks': ('#C0392B', '', 'Red Rocks'),
    'Tomorrowland Belgium': ('#9B1B5A', 'Belgium', 'Tomorrowland'),
    'Tomorrowland Brasil': ('#2A9D8F', 'Brasil', 'Tomorrowland'),
    'Tomorrowland Winter': ('#5B9BD5', 'Winter', 'Tomorrowland'),
    'Ultra': ('#0693E3', 'Miami', 'Ultra Music Festival'),
    'We Belong Here': ('#2EA3F2', '', 'We Belong Here'),
    'Mysteryland': ('#FFFF7B', '', 'Mysteryland'),
}

logo_base = Path('/home/martijn/_temp/cratedigger/festivals')
out_dir = Path('/tmp/poster_redesign_test')
out_dir.mkdir(exist_ok=True)

for name, (color_hex, edition, festival) in festivals.items():
    logo_dirs = {
        'AMF': 'AMF',
        'ASOT': 'A State Of Trance Festival',
        'Dreamstate': 'Dreamstate SoCal',
        'EDC': 'EDC Las Vegas',
        'Red Rocks': 'Red Rocks',
        'Tomorrowland Belgium': 'Tomorrowland',
        'Tomorrowland Brasil': 'Tomorrowland Brasil',
        'Tomorrowland Winter': 'Tomorrowland Winter',
        'Ultra': 'Ultra Music Festival Miami',
        'We Belong Here': 'We Belong Here',
    }
    logo_dir = logo_dirs.get(name)
    logo_path = logo_base / logo_dir / 'logo.png' if logo_dir else None
    bg = logo_path if logo_path and logo_path.exists() else None

    generate_album_poster(
        output_path=out_dir / f'{name}.jpg',
        festival=festival,
        date_or_year='2025',
        edition=edition,
        override_color=_hex_to_rgb(color_hex),
        background_image_path=bg,
    )
    print(f'Generated: {name}')
print(f'Output: {out_dir}')
"
```

**Step 3: Visual comparison**

Compare generated posters at `/tmp/poster_redesign_test/` with mockups at `/home/martijn/_temp/cratedigger/posters_mockup_v2/`. Key checks:
- Gradient is dark/moody with correct hue per festival
- Logo is centered in upper area, not tiled
- Festival name bold/uppercase above accent line
- Edition in semilight below festival name (when present)
- Nothing below accent line
- Accent line color matches gradient hue (brighter)
- Mysteryland has no logo, just gradient + text

**Step 4: Final commit with design doc**

```bash
git add docs/plans/2026-04-01-poster-redesign-design.md
git commit -m "docs: add poster redesign design document"
```
