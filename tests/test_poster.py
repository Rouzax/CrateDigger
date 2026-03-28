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
    POSTER_W,
    POSTER_H,
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
