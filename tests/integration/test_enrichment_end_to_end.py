"""End-to-end re-enrichment against real MKVs.

This test is opt-in and machine-local. It requires three things on the
machine running it, none of which are committed to the repo:

- ``CRATEDIGGER_TEST_CONFIG``: path to a ``config.json`` with 1001TL credentials.
- ``CRATEDIGGER_TEST_COOKIES``: path to the 1001TL cookies jar used by the
  ``TracklistSession`` login flow.
- ``CRATEDIGGER_TEST_MKV_DIR``: directory containing the fixture MKVs
  (``tiesto-we-belong-here.mkv`` and ``something-else-tomorrowland-winter.mkv``).

Tests auto-skip when any of these are absent. Use with:

    CRATEDIGGER_TEST_CONFIG=~/.cratedigger/config.json \\
    CRATEDIGGER_TEST_COOKIES=~/.1001tl-cookies.json \\
    CRATEDIGGER_TEST_MKV_DIR=~/mkvs \\
    pytest tests/integration/ -m integration

Assertions cover: clean UTF-8 in all tag values, per-chapter PERFORMER tags at
TTV=30, and the display-vs-canonical split between TTV=50 ARTIST (filesystem
canonical), TTV=70 CRATEDIGGER_1001TL_ARTISTS (1001TL display form), and
TTV=30 PERFORMER (1001TL display form, no alias resolution).
"""
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


def _env_path(name: str) -> Path | None:
    """Return an expanded Path from env var, or None if unset/missing."""
    raw = os.environ.get(name)
    if not raw:
        return None
    path = Path(os.path.expanduser(raw))
    return path if path.exists() else None


CONFIG = _env_path("CRATEDIGGER_TEST_CONFIG")
COOKIES = _env_path("CRATEDIGGER_TEST_COOKIES")
MKV_DIR = _env_path("CRATEDIGGER_TEST_MKV_DIR")

TIESTO_MKV = (MKV_DIR / "tiesto-we-belong-here.mkv") if MKV_DIR else None
TIESTO_ID = "2dyq04n9"

SOMETHING_ELSE_MKV = (MKV_DIR / "something-else-tomorrowland-winter.mkv") if MKV_DIR else None
SOMETHING_ELSE_ID = "upk4l6k"


pytestmark = pytest.mark.skipif(
    not (CONFIG and COOKIES and MKV_DIR),
    reason=(
        "Set CRATEDIGGER_TEST_CONFIG, CRATEDIGGER_TEST_COOKIES, and "
        "CRATEDIGGER_TEST_MKV_DIR to run integration tests"
    ),
)


def _run_enrich(mkv: Path, tracklist_id: str, tmp_path: Path, tracklist_date: str | None = None):
    """Re-enrich *mkv* through the real pipeline. Returns the loaded Tags and
    Chapters XML roots."""
    from festival_organizer.config import load_config
    from festival_organizer.tracklists.api import TracklistSession
    from festival_organizer.tracklists.chapters import embed_chapters, parse_tracklist_lines
    from festival_organizer.tracklists.dj_cache import DjCache
    from festival_organizer.tracklists.source_cache import SourceCache

    cfg = load_config(config_path=CONFIG)
    email, password = cfg.tracklists_credentials
    dj_cache = DjCache(cache_path=tmp_path / "dj_cache.json", ttl_days=90)
    src_cache = SourceCache(cache_path=tmp_path / "source_cache.json", ttl_days=365)
    sess = TracklistSession(
        cookie_cache_path=COOKIES, source_cache=src_cache, dj_cache=dj_cache, delay=5
    )
    sess.login(email, password)

    export = sess.export_tracklist(tracklist_id)
    chapters = parse_tracklist_lines(export.lines)
    assert chapters, "parse_tracklist_lines returned no chapters"

    ok = embed_chapters(
        mkv,
        chapters,
        tracklist_url=export.url,
        tracklist_title=export.title,
        tracklist_id=tracklist_id,
        tracklist_date=tracklist_date,
        genres=export.genres,
        dj_artwork_url=export.dj_artwork_url,
        stage_text=export.stage_text,
        sources_by_type=export.sources_by_type,
        dj_artists=export.dj_artists,
        country=export.country,
        tracks=export.tracks,
        dj_cache=dj_cache,
        alias_resolver=cfg.resolve_artist,
    )
    assert ok, "embed_chapters returned False"

    tags_xml = tmp_path / "tags.xml"
    subprocess.run(["mkvextract", str(mkv), "tags", str(tags_xml)], check=True)
    chapters_xml = tmp_path / "chapters.xml"
    subprocess.run(["mkvextract", str(mkv), "chapters", str(chapters_xml)], check=True)
    return ET.parse(tags_xml).getroot(), ET.parse(chapters_xml).getroot()


@pytest.mark.integration
@pytest.mark.skipif(
    TIESTO_MKV is None or not TIESTO_MKV.exists(),
    reason="Tiësto fixture MKV missing (expected at $CRATEDIGGER_TEST_MKV_DIR/tiesto-we-belong-here.mkv)",
)
def test_tiesto_enrichment(tmp_path):
    """Re-enrich a solo-DJ MKV; covers core plumbing + UTF-8 cleanliness."""
    assert TIESTO_MKV is not None  # narrow for type checker
    mkv = tmp_path / "test.mkv"
    shutil.copy(TIESTO_MKV, mkv)

    tags_root, chapters_root = _run_enrich(mkv, TIESTO_ID, tmp_path, tracklist_date="2026-03-01")

    # TTV=70 display tag uses DjCache canonical casing.
    assert _find_global_tag(tags_root, 70, "CRATEDIGGER_1001TL_ARTISTS") == "Tiësto"

    # Per-chapter PERFORMER tags exist on most chapters.
    ttv30 = _find_chapter_tags(tags_root)
    assert len(ttv30) >= 20
    perf_blocks = [t for t in ttv30 if any(
        (s.find("Name").text or "") == "PERFORMER" for s in t.findall("Simple")
    )]
    assert len(perf_blocks) >= 20

    # No legacy ARTIST/ARTIST_SLUGS leaked at chapter scope.
    for tag in ttv30:
        for simple in tag.findall("Simple"):
            n_el = simple.find("Name")
            name = n_el.text if n_el is not None else ""
            assert name not in ("ARTIST", "ARTIST_SLUGS"), (
                f"Per-chapter tag still using legacy name {name!r}"
            )

    # Every TTV=30 tag references a real ChapterUID in the chapters XML.
    atom_uids = set()
    for a in chapters_root.findall(".//ChapterAtom"):
        u_el = a.find("ChapterUID")
        if u_el is not None and u_el.text:
            atom_uids.add(u_el.text)
    for tag in ttv30:
        uid_el = tag.find("Targets/ChapterUID")
        assert uid_el is not None and uid_el.text in atom_uids

    # No mojibake anywhere in chapter titles or tag values.
    for atom in chapters_root.findall(".//ChapterAtom"):
        title_el = atom.find("ChapterDisplay/ChapterString")
        title = (title_el.text if title_el is not None else "") or ""
        assert "├" not in title, f"mojibake in chapter: {title!r}"
    for simple in tags_root.iter("Simple"):
        str_el = simple.find("String")
        value = (str_el.text if str_el is not None else "") or ""
        assert "├" not in value, f"mojibake in tag: {value!r}"

    # DjCache captured at least the set-owner entry.
    cache_data = json.loads((tmp_path / "dj_cache.json").read_text())
    assert len(cache_data) >= 1


@pytest.mark.integration
@pytest.mark.skipif(
    SOMETHING_ELSE_MKV is None or not SOMETHING_ELSE_MKV.exists(),
    reason=(
        "SOMETHING ELSE fixture MKV missing (expected at "
        "$CRATEDIGGER_TEST_MKV_DIR/something-else-tomorrowland-winter.mkv)"
    ),
)
def test_something_else_display_preserved_per_chapter(tmp_path):
    """Verify the display-vs-canonical tag semantics in a real file where the
    1001TL set owner is an alias (SOMETHING ELSE -> ALOK per artists.json):

    - TTV=70 CRATEDIGGER_1001TL_ARTISTS preserves the 1001TL display form.
    - TTV=30 PERFORMER values are 1001TL display forms; none get silently
      substituted to the aliased filesystem form ('ALOK').
    """
    assert SOMETHING_ELSE_MKV is not None
    mkv = tmp_path / "test.mkv"
    shutil.copy(SOMETHING_ELSE_MKV, mkv)

    tags_root, _ = _run_enrich(mkv, SOMETHING_ELSE_ID, tmp_path)

    # Display tag: preserves what 1001TL actually renders.
    assert _find_global_tag(tags_root, 70, "CRATEDIGGER_1001TL_ARTISTS") == "SOMETHING ELSE"

    # Per-chapter PERFORMER values should be display forms, not aliased.
    ttv30 = _find_chapter_tags(tags_root)
    perf_values = []
    for tag in ttv30:
        for simple in tag.findall("Simple"):
            n_el = simple.find("Name")
            if n_el is not None and (n_el.text or "") == "PERFORMER":
                s_el = simple.find("String")
                perf_values.append(s_el.text if s_el is not None else "")
    assert perf_values, "expected at least some per-chapter PERFORMER values"
    # alias_resolver leaking into per-chapter tags would surface as 'ALOK'.
    assert all(v != "ALOK" for v in perf_values), (
        "per-chapter PERFORMER must not be alias-resolved"
    )


def _find_global_tag(root: ET.Element, ttv: int, name: str) -> str | None:
    """Return the String value of the Simple element at the given global TTV."""
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is None:
            continue
        ttv_el = targets.find("TargetTypeValue")
        if ttv_el is None or ttv_el.text != str(ttv):
            continue
        if targets.find("ChapterUID") is not None:
            continue
        for simple in tag.findall("Simple"):
            n_el = simple.find("Name")
            if n_el is not None and (n_el.text or "") == name:
                str_el = simple.find("String")
                return str_el.text if str_el is not None else None
    return None


def _find_chapter_tags(root: ET.Element) -> list[ET.Element]:
    """Return all TTV=30 Tag elements (chapter-scoped)."""
    out = []
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is None:
            continue
        ttv_el = targets.find("TargetTypeValue")
        if ttv_el is not None and ttv_el.text == "30":
            out.append(tag)
    return out
