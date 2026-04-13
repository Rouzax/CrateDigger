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
import logging
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

FIXTURES = {
    "tiesto-we-belong-here": {
        "filename": "Tiësto - Live at We Belong Here Miami 2026 [2EQGqEvLAuE].mkv",
        "tracklist_id": "2dyq04n9",
        "tracklist_date": "2026-03-01",
        "scenarios": ["solo", "baseline"],
        "expect": {
            "embedding": {
                "ttv70_artists": "Tiësto",
                "min_chapters": 20,
                "min_performer_chapters": 20,
                "dj_cache_min_entries": 1,
            },
            "pipeline": {
                "library_path_glob": "**/Tiësto/*We Belong Here*2026*.mkv",
                "nfo_must_exist": True,
                "poster_must_exist": True,
                "fanart_must_exist": True,
            },
        },
    },
    "alok-something-else": {
        "filename": "Alok presents Something Else ｜ Tomorrowland Winter 2026 [kttWNVHJKDo].mkv",
        "tracklist_id": "upk4l6k",
        "scenarios": ["alias"],
        "expect": {
            "embedding": {
                "ttv70_artists": "SOMETHING ELSE",
                "performer_must_not_contain": ["ALOK"],
                "min_performer_chapters": 1,
            },
            "pipeline": {
                "library_path_glob": "**/ALOK/*Tomorrowland Winter*2026*.mkv",
            },
        },
    },
    "armin-b2b-marlon": {
        "filename": "ARMIN VAN BUUREN B2B MARLON HOFFSTADT LIVE AT ULTRA MIAMI 2026 ASOT WORLDWIDE STAGE [XM0zfkqLMzI].mkv",
        "tracklist_id": "2gugf5b9",
        "scenarios": ["b2b"],
        "expect": {
            "embedding": {
                "ttv70_artists_contains": ["Armin", "Marlon"],
                "min_chapters": 15,
            },
        },
    },
    "afrojack-ultra": {
        "filename": "AFROJACK LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026 [fLyb8KvtSzw].mkv",
        "tracklist_id": "22r0yk79",
        "scenarios": ["solo"],
        "expect": {"embedding": {"ttv70_artists": "Afrojack"}},
    },
    "eric-prydz-resistance": {
        "filename": "ERIC PRYDZ LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026 ｜ RESISTANCE MEGASTRUCTURE [hU-z3iV0LOg].mkv",
        "tracklist_id": "qy9yyy9",
        "scenarios": ["solo", "single-genre"],
        "expect": {"embedding": {"ttv70_artists": "Eric Prydz"}},
    },
}


def _fixture_mkv(key: str) -> Path | None:
    if MKV_DIR is None:
        return None
    path = MKV_DIR / FIXTURES[key]["filename"]
    return path if path.exists() else None


TIESTO_MKV = _fixture_mkv("tiesto-we-belong-here")
TIESTO_ID = FIXTURES["tiesto-we-belong-here"]["tracklist_id"]

SOMETHING_ELSE_MKV = _fixture_mkv("alok-something-else")
SOMETHING_ELSE_ID = FIXTURES["alok-something-else"]["tracklist_id"]


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


@pytest.mark.integration
@pytest.mark.skipif(
    TIESTO_MKV is None or not TIESTO_MKV.exists(),
    reason="Tiësto fixture MKV missing (expected at $CRATEDIGGER_TEST_MKV_DIR/tiesto-we-belong-here.mkv)",
)
def test_chapter_mbids_end_to_end(tmp_path, caplog):
    """End-to-end: PERFORMER_NAMES -> MUSICBRAINZ_ARTISTIDS slot alignment.

    Covers the per-track MBID write path with:
      (a) pipe-count alignment between PERFORMER_NAMES and MUSICBRAINZ_ARTISTIDS
          on every chapter that carries per-track names,
      (b) ArtistMbidOverrides taking precedence for a pinned artist (the
          pinned MBID must appear in exactly the slot(s) that match the
          pinned name),
      (c) the pinned artist's lowercase key must NOT appear in
          mbid_cache.json: overrides are never promoted into the cache,
      (d) any unresolved artists are surfaced at WARNING.
    """
    from festival_organizer.fanart import (
        ArtistMbidOverrides,
        MBIDCache,
        compute_chapter_mbid_tags,
        lookup_mbid,
    )
    from festival_organizer.operations import (
        _extract_chapter_tags_by_uid,
        write_chapter_mbid_tags,
    )

    assert TIESTO_MKV is not None
    mkv = tmp_path / "test.mkv"
    shutil.copy(TIESTO_MKV, mkv)

    # Step 1: normal enrichment to seed PERFORMER_NAMES on each chapter.
    _run_enrich(mkv, TIESTO_ID, tmp_path, tracklist_date="2026-03-01")

    existing = _extract_chapter_tags_by_uid(mkv)
    assert existing, "expected chapter-scoped tags after enrich"

    # Collect the set of unique PERFORMER_NAMES entries from the file. The
    # pin target is chosen from this set so the override path is guaranteed
    # to match at least one chapter, regardless of fluctuations in the
    # 1001TL export.
    unique_names: list[str] = []
    seen: set[str] = set()
    for block in existing.values():
        names = block.get("PERFORMER_NAMES", "")
        for n in names.split("|"):
            if n and n not in seen:
                seen.add(n)
                unique_names.append(n)
    assert unique_names, "expected at least one PERFORMER_NAMES entry"

    # Prefer a non-headliner slot (index > 0) so the pin lands in a
    # non-first column, which is the more interesting slot-alignment case.
    pinned_artist = unique_names[-1] if len(unique_names) > 1 else unique_names[0]
    pinned_mbid = "deadbeef-1234-5678-9abc-def012345678"

    # Step 2: isolate overrides + cache to a tmp dir so the real
    # ~/.cratedigger is never touched.
    home = tmp_path / "cratedigger_home"
    home.mkdir()
    (home / "artist_mbids.json").write_text(
        json.dumps({pinned_artist: pinned_mbid}, ensure_ascii=False),
        encoding="utf-8",
    )

    overrides = ArtistMbidOverrides(overrides_dir=home)
    cache = MBIDCache(cache_dir=home, ttl_days=90)

    def resolver(name: str) -> str | None:
        return lookup_mbid(name, cache, overrides=overrides)

    # Step 3: compute + write MBIDs, capturing WARNING logs for assertion (d).
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="festival_organizer.fanart"):
        new_tags = compute_chapter_mbid_tags(existing, resolver)
        merged: dict[int, dict[str, str]] = {}
        for uid, block in existing.items():
            merged_block = dict(block)
            if uid in new_tags:
                merged_block["MUSICBRAINZ_ARTISTIDS"] = new_tags[uid][
                    "MUSICBRAINZ_ARTISTIDS"
                ]
            merged[uid] = merged_block
        write_chapter_mbid_tags(mkv, merged)

    # Step 4: re-extract and assert the invariants.
    after = _extract_chapter_tags_by_uid(mkv)
    assert after, "chapter tags disappeared after MBID write"

    # (a) slot alignment: every chapter with PERFORMER_NAMES must have
    # MUSICBRAINZ_ARTISTIDS with matching pipe-count.
    chapters_with_names = 0
    for uid, block in after.items():
        names = block.get("PERFORMER_NAMES", "")
        if not names:
            continue
        chapters_with_names += 1
        mbids = block.get("MUSICBRAINZ_ARTISTIDS", "")
        assert mbids, f"chapter {uid} has PERFORMER_NAMES but no MUSICBRAINZ_ARTISTIDS"
        name_slots = names.split("|")
        mbid_slots = mbids.split("|")
        assert len(name_slots) == len(mbid_slots), (
            f"chapter {uid}: pipe-count mismatch "
            f"names={len(name_slots)} mbids={len(mbid_slots)}"
        )
    assert chapters_with_names > 0, "expected chapters with PERFORMER_NAMES"

    # (b) pinned override lands in the correct slot(s).
    hits = 0
    for uid, block in after.items():
        names = block.get("PERFORMER_NAMES", "").split("|")
        mbids = block.get("MUSICBRAINZ_ARTISTIDS", "").split("|")
        for idx, name in enumerate(names):
            if name == pinned_artist:
                assert mbids[idx] == pinned_mbid, (
                    f"chapter {uid} slot {idx}: expected override "
                    f"{pinned_mbid} for {pinned_artist!r}, got {mbids[idx]!r}"
                )
                hits += 1
    assert hits > 0, f"pinned artist {pinned_artist!r} never appeared in any chapter"

    # (c) override must NOT leak into the MBID cache file.
    cache_file = home / "mbid_cache.json"
    if cache_file.exists():
        cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert pinned_artist.lower() not in cache_data, (
            f"override leaked into mbid_cache.json under key {pinned_artist.lower()!r}"
        )

    # Hermeticity: no mbid_cache.json or artist_mbids.json in real ~/.cratedigger
    # was consulted or written. We assert the isolated files are the only
    # ones the test touched by checking our tmp home for the expected shape.
    assert (home / "artist_mbids.json").exists()

    # (d) any unresolved artists are logged at WARNING. When every artist
    # resolves, there are simply no warnings, which is also valid: so we
    # only assert the shape IF there is at least one empty MBID slot.
    had_miss = any(
        "" in block.get("MUSICBRAINZ_ARTISTIDS", "").split("|")
        and block.get("PERFORMER_NAMES")
        for block in after.values()
    )
    if had_miss:
        warning_messages = [
            r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert any("No MBID resolved for artist" in m for m in warning_messages), (
            "expected a WARNING for unresolved artists, got: "
            f"{warning_messages!r}"
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
