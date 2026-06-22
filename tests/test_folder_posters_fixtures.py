"""Folder-poster tests on committed tiny tagged MKV fixtures (mount-free, CI-able).

The fixtures in tests/fixtures/folder_posters/ are ~30 KB MKVs carrying the
container tags an identified 1001TL set has, plus chapters and both cover
attachments (regenerate with build_folder_poster_fixtures.py). Reading them needs
ffprobe; rendering needs Pillow. Background priorities are forced to gradient so
the tests are deterministic and never touch the network.
"""

import shutil
from pathlib import Path

import pytest

from festival_organizer.analyzer import analyse_file
from festival_organizer.classifier import classify
from festival_organizer.config import load_config
from festival_organizer.library import cleanup_empty_dirs
from festival_organizer.models import MediaFile
from festival_organizer.operations import AlbumPosterOperation
from festival_organizer.poster import read_poster_stamp
from festival_organizer.templates import render_filename, render_folder

FIX = Path(__file__).parent / "fixtures" / "folder_posters"
pytestmark = pytest.mark.skipif(
    shutil.which("ffprobe") is None or not list(FIX.glob("*.mkv")),
    reason="ffprobe + committed folder-poster fixtures required",
)


def _config():
    config = load_config(FIX / "config.toml")
    # Deterministic + offline: gradient backgrounds only (no curated logo / artwork).
    config._data["poster_settings"] = {
        "artist_background_priority": ["gradient"],
        "place_background_priority": ["gradient"],
        "year_background_priority": ["gradient"],
    }
    return config


def _organize_into(lib: Path, layout: str, config) -> list[tuple[Path, MediaFile]]:
    """Place each fixture into `lib` per `layout` (mimics an organize move/copy)."""
    config._data["default_layout"] = layout
    placed = []
    for src in sorted(FIX.glob("*.mkv")):
        mf = analyse_file(src, src.parent, config)
        mf.content_type = classify(
            mf, src.parent, config
        )  # pipeline sets this post-analyse
        dest = lib / render_folder(mf, config) / render_filename(mf, config)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
        placed.append((dest, mf))
    return placed


def _enrich_posters(lib: Path, placed, config) -> AlbumPosterOperation:
    op = AlbumPosterOperation(config=config, library_root=lib)
    for video, mf in placed:
        if op.is_needed(video, mf):
            assert op.execute(video, mf).status == "done"
    return op


def _stamp(folder_jpg: Path) -> list[str]:
    raw = read_poster_stamp(folder_jpg)
    assert raw is not None, f"no folder-poster stamp in {folder_jpg}"
    return raw.decode().split("\x1f")


def test_place_nested_all_levels_and_edition(tmp_path):
    lib = tmp_path / "lib"
    config = _config()
    placed = _organize_into(lib, "place_nested", config)
    _enrich_posters(lib, placed, config)

    # Every produced folder.jpg is a real 1000x1500 JPEG carrying a CDFOLDER stamp.
    jpgs = list(lib.rglob("folder.jpg"))
    assert jpgs
    from PIL import Image

    for fj in jpgs:
        with Image.open(fj) as img:
            assert img.size == (1000, 1500)
        assert _stamp(fj)[0] == "CDFOLDER1"

    # place_nested {place}{ edition}/{year}/{artist}: typed per depth.
    assert _stamp(lib / "EDC Las Vegas" / "folder.jpg")[:5] == [
        "CDFOLDER1",
        "festival",
        "EDC Las Vegas",
        "",
        "",
    ]
    assert _stamp(lib / "EDC Las Vegas" / "2025" / "folder.jpg")[:5] == [
        "CDFOLDER1",
        "year",
        "EDC Las Vegas",
        "2025",
        "",
    ]
    assert _stamp(lib / "EDC Las Vegas" / "2025" / "AFROJACK" / "folder.jpg")[:5] == [
        "CDFOLDER1",
        "artist",
        "AFROJACK",
        "",
        "",
    ]

    # Edition set: place resolves to Tomorrowland + Winter; the year folder carries it.
    assert _stamp(lib / "Tomorrowland Winter" / "folder.jpg")[:5] == [
        "CDFOLDER1",
        "festival",
        "Tomorrowland",
        "",
        "Winter",
    ]
    assert _stamp(lib / "Tomorrowland Winter" / "2026" / "folder.jpg")[:5] == [
        "CDFOLDER1",
        "year",
        "Tomorrowland",
        "2026",
        "Winter",
    ]

    # Re-running enriches nothing (all stamps match).
    op2 = AlbumPosterOperation(config=config, library_root=lib)
    assert all(not op2.is_needed(v, mf) for v, mf in placed)


def test_layout_change_place_to_artist_regenerates(tmp_path):
    lib = tmp_path / "lib"
    config = _config()

    # Start in place_nested and generate posters.
    placed = _organize_into(lib, "place_nested", config)
    _enrich_posters(lib, placed, config)
    assert (lib / "EDC Las Vegas" / "folder.jpg").exists()

    # Library change: re-organize the same files into artist_nested (move in place).
    config._data["default_layout"] = "artist_nested"
    relocated = []
    for video, mf in placed:
        new = lib / render_folder(mf, config) / render_filename(mf, config)
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(video), str(new))
        relocated.append((new, mf))
    cleanup_empty_dirs(lib)

    # Old place-rooted tree is gone (emptied folders + their stale folder.jpg cleaned).
    assert not (lib / "EDC Las Vegas").exists()

    # Re-enrich: posters regenerate, now typed for artist_nested {artist}/{place}/{year}.
    _enrich_posters(lib, relocated, config)
    assert _stamp(lib / "AFROJACK" / "folder.jpg")[:3] == [
        "CDFOLDER1",
        "artist",
        "AFROJACK",
    ]
    assert _stamp(lib / "AFROJACK" / "EDC Las Vegas" / "folder.jpg")[:3] == [
        "CDFOLDER1",
        "festival",
        "EDC Las Vegas",
    ]
    assert _stamp(lib / "AFROJACK" / "EDC Las Vegas" / "2025" / "folder.jpg")[:5] == [
        "CDFOLDER1",
        "year",
        "EDC Las Vegas",
        "2025",
        "",
    ]
