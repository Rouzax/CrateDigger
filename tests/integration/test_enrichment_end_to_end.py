"""End-to-end re-enrichment against a real MKV.

Skipped unless a test MKV exists at the expected path and 1001TL credentials
are available. This is the integration gate for per-chapter-tags work:
asserts the full pipeline produces canonical names, per-chapter PERFORMER
tags at TTV=30, no mojibake, and no ARTIST tag collision.

Run with: pytest tests/integration/ -m integration
"""
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


FIXTURE_MKV = Path(
    "/home/martijn/_temp/cratedigger/data/2026 - Tiësto - We Belong Here.mkv"
)
CONFIG = Path("/home/martijn/_temp/cratedigger/.cratedigger/config.json")
COOKIES = Path("/home/martijn/.1001tl-cookies.json")
TRACKLIST_ID = "2dyq04n9"


pytestmark = pytest.mark.skipif(
    not (FIXTURE_MKV.exists() and CONFIG.exists() and COOKIES.exists()),
    reason="Fixture MKV or 1001TL credentials not available",
)


@pytest.mark.integration
def test_end_to_end_enrichment(tmp_path):
    """Re-enrich the Tiësto MKV and assert every design-level guarantee."""
    from festival_organizer.config import load_config
    from festival_organizer.tracklists.api import TracklistSession
    from festival_organizer.tracklists.chapters import embed_chapters, parse_tracklist_lines
    from festival_organizer.tracklists.dj_cache import DjCache
    from festival_organizer.tracklists.source_cache import SourceCache

    mkv = tmp_path / "test.mkv"
    shutil.copy(FIXTURE_MKV, mkv)

    cfg = load_config(config_path=CONFIG)
    email, password = cfg.tracklists_credentials
    dj_cache = DjCache(cache_path=tmp_path / "dj_cache.json", ttl_days=90)
    src_cache = SourceCache(cache_path=tmp_path / "source_cache.json", ttl_days=365)
    sess = TracklistSession(
        cookie_cache_path=COOKIES, source_cache=src_cache, dj_cache=dj_cache, delay=5
    )
    sess.login(email, password)

    export = sess.export_tracklist(TRACKLIST_ID)
    chapters = parse_tracklist_lines(export.lines)
    assert chapters, "parse_tracklist_lines returned no chapters"

    def fetcher(slug):
        profile = sess._fetch_dj_profile(slug)
        profile["name"] = slug.replace("-", " ").title()
        return profile

    ok = embed_chapters(
        mkv,
        chapters,
        tracklist_url=export.url,
        tracklist_title=export.title,
        tracklist_id=TRACKLIST_ID,
        tracklist_date="2026-03-01",
        genres=export.genres,
        dj_artwork_url=export.dj_artwork_url,
        stage_text=export.stage_text,
        sources_by_type=export.sources_by_type,
        dj_artists=export.dj_artists,
        country=export.country,
        tracks=export.tracks,
        dj_cache=dj_cache,
        fetcher=fetcher,
    )
    assert ok

    tags_xml = tmp_path / "tags.xml"
    subprocess.run(["mkvextract", str(mkv), "tags", str(tags_xml)], check=True)
    chapters_xml = tmp_path / "chapters.xml"
    subprocess.run(["mkvextract", str(mkv), "chapters", str(chapters_xml)], check=True)

    tags_root = ET.parse(tags_xml).getroot()
    chapters_root = ET.parse(chapters_xml).getroot()

    # Assert 1: TTV=50 ARTIST is preserved / set-level canonical.
    set_artist = _find_global_tag(tags_root, 50, "ARTIST")
    assert set_artist == "Tiësto"

    # Assert 2: CRATEDIGGER_1001TL_ARTISTS uses canonical name.
    cd_artists = _find_global_tag(tags_root, 70, "CRATEDIGGER_1001TL_ARTISTS")
    assert cd_artists == "Tiësto"

    # Assert 3: Per-chapter PERFORMER tags exist for a meaningful fraction.
    ttv30 = _find_chapter_tags(tags_root)
    assert len(ttv30) >= 20, f"Expected many per-chapter tags, got {len(ttv30)}"
    performers = [t for t in ttv30 if any(
        s.find("Name").text == "PERFORMER" for s in t.findall("Simple")
    )]
    assert len(performers) >= 20

    # Assert 4: No per-chapter ARTIST/ARTIST_SLUGS leaked through the rename.
    for tag in ttv30:
        for simple in tag.findall("Simple"):
            name = simple.find("Name").text
            assert name not in ("ARTIST", "ARTIST_SLUGS"), (
                f"Per-chapter tag still using legacy name {name!r}"
            )

    # Assert 5: Every PERFORMER tag references a real ChapterUID.
    atom_uids = {
        a.find("ChapterUID").text
        for a in chapters_root.findall(".//ChapterAtom")
    }
    for tag in ttv30:
        uid = tag.find("Targets/ChapterUID").text
        assert uid in atom_uids, f"TTV=30 tag references orphan UID {uid}"

    # Assert 6: No mojibake anywhere in chapter titles or tag values.
    for atom in chapters_root.findall(".//ChapterAtom"):
        title = atom.find("ChapterDisplay/ChapterString").text or ""
        assert "├" not in title, f"Mojibake in chapter: {title!r}"
    for simple in tags_root.iter("Simple"):
        value = (simple.find("String").text if simple.find("String") is not None else "") or ""
        assert "├" not in value, f"Mojibake in tag value: {value!r}"

    # Assert 7: DjCache grew (fetched per-track artists).
    cache_data = json.loads((tmp_path / "dj_cache.json").read_text())
    assert len(cache_data) > 0


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
            if (simple.find("Name").text or "") == name:
                return simple.find("String").text
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
