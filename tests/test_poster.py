"""Tests for poster generation module."""
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from festival_organizer.fonts import get_font_path
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


# --- split_artist tests ---

def test_split_artist_parenthetical():
    line1, line2 = split_artist("Everything Always (Dom Dolla & John Summit)")
    assert line1 == "Everything Always"
    assert line2 == "Dom Dolla & John Summit"


def test_split_artist_ampersand():
    line1, line2 = split_artist("Martin Garrix & Alesso")
    assert line1 == "Martin Garrix"
    assert line2 == "& Alesso"


def test_split_artist_b2b():
    line1, line2 = split_artist("Artist1 B2B Artist2")
    assert line1 == "Artist1"
    assert line2 == "B2B Artist2"


def test_split_artist_no_split():
    lines = split_artist("Swedish House Mafia")
    assert lines == ["Swedish House Mafia"]


def test_split_artist_single_name():
    lines = split_artist("Hardwell")
    assert lines == ["Hardwell"]


# --- accent color tests ---

def test_get_accent_color_returns_rgb():
    img = Image.new("RGB", (100, 100), (200, 50, 50))
    color = get_accent_color(img)
    assert isinstance(color, tuple)
    assert len(color) == 3
    assert all(0 <= c <= 255 for c in color)


# --- format_date_display tests ---

def test_format_date_full():
    assert format_date_display("2025-03-28", "2025") == "28 March 2025"


def test_format_date_year_only():
    assert format_date_display("", "2025") == "2025"


def test_format_date_no_data():
    assert format_date_display("", "") == ""


# --- auto_fit tests ---

def test_auto_fit_short_name():
    font, size = auto_fit("HI", "bold", 900, start=110, minimum=50)
    assert size == 110  # short text fits at max size


def test_auto_fit_long_name():
    font, size = auto_fit("A" * 50, "bold", 900, start=110, minimum=50)
    assert size <= 110  # long text should be smaller


# --- generate_set_poster tests ---

def test_generate_set_poster_creates_file(tmp_path):
    src = tmp_path / "source.png"
    Image.new("RGB", (1280, 720), (100, 50, 200)).save(str(src))

    output = tmp_path / "poster.jpg"
    result = generate_set_poster(
        source_image_path=src,
        output_path=output,
        artist="Martin Garrix",
        festival="AMF",
        date="2024-10-19",
        year="2024",
        detail="Johan Cruijff ArenA",
    )

    assert result == output
    assert output.exists()
    with Image.open(output) as img:
        assert img.size == (POSTER_W, POSTER_H)


def test_generate_set_poster_with_b2b(tmp_path):
    src = tmp_path / "source.png"
    Image.new("RGB", (1920, 1080), (50, 100, 200)).save(str(src))

    output = tmp_path / "poster.jpg"
    generate_set_poster(
        source_image_path=src,
        output_path=output,
        artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        year="2025",
    )

    assert output.exists()
    with Image.open(output) as img:
        assert img.size == (POSTER_W, POSTER_H)


# --- generate_album_poster tests ---

def test_generate_album_poster_creates_file(tmp_path):
    output = tmp_path / "album_poster.jpg"
    result = generate_album_poster(
        output_path=output,
        festival="AMF",
        date_or_year="19 October 2024",
        detail="Johan Cruijff ArenA, Amsterdam",
        override_color=(40, 80, 180),
    )

    assert result == output
    assert output.exists()
    with Image.open(output) as img:
        assert img.size == (POSTER_W, POSTER_H)


def test_generate_album_poster_with_thumbs(tmp_path):
    thumbs = []
    for i in range(3):
        t = tmp_path / f"thumb_{i}.png"
        Image.new("RGB", (320, 180), (100 + i * 30, 50, 200)).save(str(t))
        thumbs.append(t)

    output = tmp_path / "album_poster.jpg"
    generate_album_poster(
        output_path=output,
        festival="Tomorrowland Belgium",
        date_or_year="2025",
        thumb_paths=thumbs,
    )

    assert output.exists()
    with Image.open(output) as img:
        assert img.size == (POSTER_W, POSTER_H)


def test_generate_album_poster_with_transparent_png(tmp_path):
    """Album poster handles transparent PNG logos (RGBA) without artifacts."""
    logo = tmp_path / "logo.png"
    img = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    # Draw a colored circle on transparent background
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.ellipse([50, 50, 450, 450], fill=(200, 50, 100, 255))
    img.save(str(logo))

    output = tmp_path / "poster.jpg"
    generate_album_poster(
        output_path=output,
        festival="Test Festival",
        date_or_year="2025",
        background_image_path=logo,
    )
    assert output.exists()
    with Image.open(output) as result:
        assert result.size == (POSTER_W, POSTER_H)
        assert result.mode == "RGB"


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


def test_set_poster_with_venue(tmp_path):
    """Poster generates without error when venue is provided."""
    source = tmp_path / "source.png"
    Image.new("RGB", (1280, 720), (100, 50, 200)).save(str(source))
    output = tmp_path / "poster.jpg"
    generate_set_poster(
        source_image_path=source,
        output_path=output,
        artist="Armin van Buuren",
        festival="A State Of Trance Festival",
        date="2026-02-27",
        detail="25 Years Celebration Set, Area One",
        venue="Ahoy Rotterdam",
    )
    assert output.exists()
    img = Image.open(output)
    assert img.size == (POSTER_W, POSTER_H)


def test_generate_set_poster_with_rgba_source(tmp_path):
    """Set poster handles RGBA source images."""
    source = tmp_path / "cover.png"
    img = Image.new("RGBA", (800, 600), (100, 150, 200, 200))
    img.save(str(source))

    output = tmp_path / "poster.jpg"
    from festival_organizer.poster import generate_set_poster
    generate_set_poster(
        source_image_path=source,
        output_path=output,
        artist="Test Artist",
        festival="Test Fest",
        year="2025",
    )
    assert output.exists()
    with Image.open(output) as result:
        assert result.mode == "RGB"


# --- font resolver tests ---

def test_get_font_path_returns_bundled():
    """Bundled font path exists and is a real file."""
    path = get_font_path("bold")
    assert Path(path).is_file()


def test_get_font_path_all_weights():
    """All four font weights resolve to existing files."""
    for weight in ("bold", "light", "semilight", "regular"):
        path = get_font_path(weight)
        assert Path(path).is_file(), f"Missing font for weight: {weight}"


def test_get_font_path_config_override(tmp_path):
    """Config override takes priority over bundled fonts."""
    fake_font = tmp_path / "custom.ttf"
    fake_font.write_bytes(b"fake")
    overrides = {"bold": str(fake_font)}
    path = get_font_path("bold", overrides=overrides)
    assert path == str(fake_font)


def test_get_font_path_config_override_missing_falls_back(tmp_path):
    """Missing config override file falls back to bundled."""
    overrides = {"bold": "/nonexistent/font.ttf"}
    path = get_font_path("bold", overrides=overrides)
    # Falls back to bundled — must be a real file
    assert Path(path).is_file()


def test_set_poster_venue_dedup_exact_match(tmp_path):
    """Venue identical to detail line should not appear twice."""
    source = tmp_path / "source.png"
    Image.new("RGB", (1280, 720), (100, 50, 200)).save(str(source))
    output = tmp_path / "poster.jpg"
    # Tiësto case: stage and venue are the same string
    generate_set_poster(
        source_image_path=source,
        output_path=output,
        artist="Tiësto",
        festival="We Belong Here",
        date="2026-03-01",
        detail="Historic Virginia Key Park",
        venue="Historic Virginia Key Park",
    )
    assert output.exists()


def test_set_poster_venue_dedup_substring(tmp_path):
    """Venue that is a substring of a detail part should be deduplicated."""
    source = tmp_path / "source.png"
    Image.new("RGB", (1280, 720), (100, 50, 200)).save(str(source))
    output = tmp_path / "poster.jpg"
    # AMF case: detail has "Johan Cruijff ArenA", venue has "Johan Cruijff ArenA Amsterdam"
    generate_set_poster(
        source_image_path=source,
        output_path=output,
        artist="Martin Garrix",
        festival="AMF",
        date="2024-10-19",
        detail="Johan Cruijff ArenA, Amsterdam Dance Event",
        venue="Johan Cruijff ArenA Amsterdam",
    )
    assert output.exists()


def test_set_poster_venue_no_dedup_when_different(tmp_path):
    """Venue unrelated to detail renders normally."""
    source = tmp_path / "source.png"
    Image.new("RGB", (1280, 720), (100, 50, 200)).save(str(source))
    output = tmp_path / "poster.jpg"
    generate_set_poster(
        source_image_path=source,
        output_path=output,
        artist="Armin van Buuren",
        festival="ASOT",
        date="2026-02-27",
        detail="Mainstage",
        venue="Ahoy Rotterdam",
    )
    assert output.exists()


# --- _filter_venue_parts tests ---

def test_filter_venue_parts_exact_duplicate():
    """Exact duplicate venue part is filtered out."""
    assert _filter_venue_parts("Historic Virginia Key Park", "Historic Virginia Key Park") == []


def test_filter_venue_parts_detail_substring_of_venue():
    """Venue containing a detail part as substring is filtered."""
    assert _filter_venue_parts("Johan Cruijff ArenA Amsterdam", "Johan Cruijff ArenA, Amsterdam Dance Event") == []


def test_filter_venue_parts_unrelated():
    """Unrelated venue parts pass through."""
    assert _filter_venue_parts("Ahoy Rotterdam", "Mainstage") == ["Ahoy Rotterdam"]


def test_filter_venue_parts_empty_detail():
    """Empty detail means all venue parts pass through."""
    assert _filter_venue_parts("Ahoy Rotterdam", "") == ["Ahoy Rotterdam"]


def test_filter_venue_parts_empty_venue():
    """Empty venue returns empty list."""
    assert _filter_venue_parts("", "Mainstage") == []


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


def test_generate_album_poster_edition_text_layout(tmp_path):
    """Festival poster with edition has nothing below accent line."""
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
        import numpy as np
        arr = np.array(result)
        # Below the accent line area should be mostly dark (no text)
        bottom_strip = arr[LINE_Y + 50:, :]
        mean_bottom = bottom_strip.mean()
        assert mean_bottom < 40, f"Bottom area too bright ({mean_bottom:.1f}), text may be below accent line"
