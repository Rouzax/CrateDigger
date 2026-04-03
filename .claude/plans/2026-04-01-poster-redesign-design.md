# Festival Album Poster Redesign - Design Document

## Context

The current festival album poster uses a tiled logo pattern background that looks noisy and inconsistent. The editions refactor is now complete (all 528 tests pass), unblocking this work. The redesign replaces the tiled pattern with a clean gradient + centered logo layout, improves color extraction, and separates festival name from edition into two text lines.

Scope: festival album posters only. Set posters and artist/year album posters are unchanged.

## Layout

### Background
- Remove the tiled logo pattern (poster.py lines 765-797) entirely
- Use `_make_gradient_bg(base_color)` as the sole background layer
- Centered sharp logo composited on top (keep existing RGBA/RGB paths at lines 799-808)
- No-logo fallback: gradient + text + accent line only (remove collage fallback)
- Remove `_make_collage_bg()` function entirely (only caller is the festival fallback path)

### Text (above accent line only)
```
                LINE_Y (accent line at y=1005)
                ================================
    PAD=30  ^
    edition ^   Belgium                 (semilight 48pt, only when edition exists)
    pad=12  ^
    hero    ^   TOMORROWLAND            (bold, uppercase, auto-fitted 60-130pt)
```

- Festival name: bold, uppercase, auto-fitted (start=130, min=60), letter spacing
- Edition: semilight, 48pt, only when non-empty
- Festivals without editions: single line only
- Nothing below the accent line (remove lines 905-916 for festival posters)
- Artist poster path: unchanged

### Accent line
- Keep as-is: glowing horizontal line at LINE_Y with `_draw_glow_line()`
- Color derived from base color via `_accent_from_base()` (boosts V by +0.4, S by x1.3)

## Color Extraction

### New function: `_extract_logo_color(img)`
Replaces `_visible_pixel_color()` for the festival path:
1. Get visible pixels (alpha > 128 for RGBA, all for RGB)
2. Convert to HSV
3. Filter to saturated pixels (S >= 40)
4. Call `_circular_hue_mean(h, s)` for hue (reuses existing infrastructure)
5. Mean saturation clamped to 0.4-0.7
6. V fixed at 0.4 (dark/moody, matching mockups)
7. Return RGB tuple
8. Raise `ValueError` if no saturated pixels found

### Fallback chain
1. Config `color` override (looked up by festival name, then edition)
2. Auto-extraction via `_extract_logo_color()`
3. No further fallback; raise error

### Config color override
Store brand colors (full brightness hex) in `festivals.example.json`. Poster code converts to HSV and derives dark gradient (V=0.4) and bright accent (V=0.8).

Config structure addition:
```json
"config": {
    "Tomorrowland": {
        "editions": ["Belgium", "Brasil", "Winter"],
        "color": "#9B1B5A",
        "edition_colors": {
            "Brasil": "#2A9D8F",
            "Winter": "#5B9BD5"
        }
    },
    "A State Of Trance Festival": {
        "color": "#E63312"
    }
}
```

`color` = festival-level default. `edition_colors` = per-edition overrides. Lookup: edition_colors[edition] > color > auto-extraction.

### Brand Color Map

| Festival | Brand Color | Source |
|----------|------------|--------|
| AMF | `#EA0000` | Red (Amsterdam XXX) |
| A State Of Trance Festival | `#E63312` | Scarlet (2023 rebrand) |
| Dreamstate | `#1C99D8` | Blue (Insomniac branding) |
| EDC | `#ED3895` | Pink/magenta (Insomniac) |
| Red Rocks | `#C0392B` | Terracotta (sandstone venue) |
| Tomorrowland | `#9B1B5A` | Purple/fuchsia (brand identity) |
| Tomorrowland Brasil | `#2A9D8F` | Teal (edition artwork theme) |
| Tomorrowland Winter | `#5B9BD5` | Icy blue (edition theme) |
| Ultra Music Festival | `#0693E3` | Cyan (web accent) |
| We Belong Here | `#2EA3F2` | Blue (brand CSS) |
| Mysteryland | `#FFFF7B` | Yellow (logo SVG fill) |

## Signature Changes

### `generate_album_poster()` in poster.py
Add parameter: `edition: str = ""`

### Caller in operations.py `AlbumPosterOperation.execute()`
- Pass `festival=mf.festival` (canonical name, not the merged display combo)
- Pass `edition=mf.edition`
- Look up color: `fc.get("edition_colors", {}).get(mf.edition) or fc.get("color")`
- Parse hex to RGB via `_hex_to_rgb()`, pass as `override_color`

## Files Changed

| File | Changes |
|------|---------|
| `poster.py` | Add `_extract_logo_color()`, `_hex_to_rgb()`. Add `edition` param. Remove tiled block (lines 765-797). Remove `_make_collage_bg()` (lines 552-708). Remove below-line text for festivals (lines 905-916). Add edition text rendering. |
| `operations.py` | Look up `color`/`edition_colors` from festival config. Pass `override_color` and `edition` separately. Pass canonical festival name. |
| `festivals.example.json` | Add `color` and `edition_colors` fields for all known festivals. |
| `tests/test_poster.py` | Rewrite dark-logo test. Add tests for new layout, edition text, color extraction, config override, no-logo fallback. Remove collage-related tests. |

## What Stays Unchanged
- Set posters (per-video)
- Artist album posters (hero_text path)
- Year album posters
- All helpers: `_make_gradient_bg`, `_accent_from_base`, `_center_sharp`, `_rounded_edge_mask`, `auto_fit`, `_draw_glow_line`, `_draw_centered_no_shadow`
- RGBA vs RGB logo handling
- Font system, constants (POSTER_W, POSTER_H, LINE_Y)

## Verification
1. Run existing tests: `pytest tests/test_poster.py -v`
2. Generate sample posters for all 11 festivals using curated logos
3. Visually compare with mockups at `/home/martijn/_temp/cratedigger/posters_mockup_v2/`
4. Verify festivals without logos (Mysteryland) get gradient-only poster
5. Verify festivals with editions show two-line text layout
6. Verify config color overrides produce correct gradient tones
