"""Physical per-level folder-poster tests against the real library.

Opt-in and machine-local (``-m integration``); skips when the library is not
mounted. The mount is treated as READ-ONLY: real MKVs are copied into
``tmp_path`` and every poster is written under ``tmp_path``, never to the mount.

    CRATEDIGGER_TEST_LIBRARY=/mnt/hyperv/Data/Festivals/Video \\
        pytest tests/integration/ -m integration -k folder_poster

These cover what the unit tests can't with synthetic data: real editions/brand
colors from the library's ``places.json`` (e.g. Tomorrowland Winter), real
artist/place metadata, and actual JPEG rendering at every folder level.
"""
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image

from festival_organizer.analyzer import analyse_file
from festival_organizer.config import load_config
from festival_organizer.operations import AlbumPosterOperation
from festival_organizer.poster import read_poster_stamp


def _library() -> Path | None:
    raw = os.environ.get("CRATEDIGGER_TEST_LIBRARY", "/mnt/hyperv/Data/Festivals/Video")
    p = Path(os.path.expanduser(raw))
    return p if p.exists() else None


SRC_LIB = _library()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        SRC_LIB is None,
        reason="real library not mounted (set CRATEDIGGER_TEST_LIBRARY)",
    ),
]


def _config():
    """Library's curated config (places.json with editions/colors) if present."""
    cfg = SRC_LIB / ".cratedigger" / "config.toml"
    config = load_config(cfg if cfg.exists() else None)
    config._data["default_layout"] = "place_nested"
    return config


def _first_video(place_dir_name: str) -> Path | None:
    d = SRC_LIB / place_dir_name
    if not d.exists():
        return None
    for f in sorted(d.rglob("*")):
        if f.suffix.lower() in (".mkv", ".mp4", ".webm"):
            return f
    return None


def _stamp(folder_jpg: Path) -> list[str] | None:
    raw = read_poster_stamp(folder_jpg)
    return raw.decode().split("\x1f") if raw else None


def _build_place_nested(src_video: Path, lib: Path, config):
    """Build a place_nested library (Place/Year/Artist) for a real set under lib.

    Returns (placeholder_video_path, media_file). The real file is analysed in
    place (read-only, no copy of multi-GB media); the tmp library gets a name-only
    placeholder plus the small ``-thumb.jpg`` sidecar, which is all the poster
    pipeline reads (metadata comes from the analyzed real file). Uses the real
    analyzer so place/edition/year/artist are canonical via the library places.json.
    """
    mf = analyse_file(src_video, src_video.parent, config)
    place_disp = config.get_place_display(mf.place, mf.edition) if mf.place else "Unknown"
    dest = lib / (place_disp or "Unknown") / (mf.year or "Unknown") / (mf.artist or "Unknown")
    dest.mkdir(parents=True, exist_ok=True)
    placeholder = dest / src_video.name
    placeholder.write_bytes(b"")  # name-only stand-in; poster pipeline reads no video content
    thumb = src_video.with_name(src_video.stem + "-thumb.jpg")
    if thumb.exists():
        shutil.copy(thumb, dest / thumb.name)
    return placeholder, mf


def test_folder_poster_all_levels_real(tmp_path):
    """A real set in place_nested gets a stamped folder.jpg at every level."""
    src = _first_video("EDC Las Vegas") or _first_video("UMF Miami")
    if src is None:
        pytest.skip("no EDC Las Vegas / UMF Miami MKV on the mount")
    lib = tmp_path / "lib"
    config = _config()
    video, mf = _build_place_nested(src, lib, config)

    op = AlbumPosterOperation(config=config, library_root=lib)
    assert op.execute(video, mf).status == "done"

    levels = op._layout_levels(video, mf)
    assert [t for _, t, _ in levels] == ["festival", "year", "artist"]
    for folder, ptype, _ in levels:
        fj = folder / "folder.jpg"
        assert fj.exists(), f"missing {fj}"
        with Image.open(fj) as img:          # real, valid JPEG
            assert img.size == (1000, 1500)
        fields = _stamp(fj)
        assert fields is not None and fields[0] == "CDFOLDER1"
        assert fields[1] == ptype            # stamp records the level's type

    # Re-run: everything is up to date (stamps match) -> nothing needed.
    op2 = AlbumPosterOperation(config=config, library_root=lib)
    assert op2.is_needed(video, mf) is False


def test_folder_poster_edition_real(tmp_path):
    """A Tomorrowland Winter set renders the edition on its place/year folders."""
    src = _first_video("Tomorrowland Winter")
    if src is None:
        pytest.skip("no Tomorrowland Winter MKV on the mount")
    lib = tmp_path / "lib"
    config = _config()
    video, mf = _build_place_nested(src, lib, config)
    if not mf.edition:
        pytest.skip("sampled set carries no edition")

    op = AlbumPosterOperation(config=config, library_root=lib)
    assert op.execute(video, mf).status == "done"

    # Year folder is parented by the place, so its stamp carries place name + edition.
    year_folder = next(f for f, t, _ in op._layout_levels(video, mf) if t == "year")
    fields = _stamp(year_folder / "folder.jpg")
    assert fields is not None
    # fields = [version, poster_type, name, year, edition]
    assert fields[1] == "year"
    assert fields[2] == mf.place
    assert fields[4] == mf.edition
