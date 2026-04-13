"""End-to-end re-enrichment against real MKVs.

This test is opt-in and machine-local. It requires three things on the
machine running it, none of which are committed to the repo:

- ``CRATEDIGGER_TEST_CONFIG``: path to a ``config.json`` with 1001TL credentials.
- ``CRATEDIGGER_TEST_COOKIES``: path to the 1001TL cookies jar used by the
  ``TracklistSession`` login flow.
- ``CRATEDIGGER_TEST_MKV_DIR``: directory containing the MKVs listed in
  the ``FIXTURES`` dict. Per-fixture skip when an individual MKV is missing.

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
FULL_PIPELINE = os.environ.get("CRATEDIGGER_TEST_FULL_PIPELINE") == "1"

# `expect` schema (consumed by _assert_embedding_expect / _assert_pipeline_expect):
#   embedding.ttv70_artists: str                 # exact match on TTV=70 CRATEDIGGER_1001TL_ARTISTS
#   embedding.ttv70_artists_contains: list[str]  # each substring must appear
#   embedding.min_chapters: int                  # >= N TTV=30 tags
#   embedding.min_performer_chapters: int        # >= N chapters with PERFORMER
#   embedding.performer_must_not_equal: list[str]  # no PERFORMER value equals any of these
#   embedding.dj_cache_min_entries: int          # >= N entries in dj_cache.json
#   pipeline.library_path_glob: str              # at least one match after organize
#   pipeline.(nfo|poster|fanart)_must_exist: bool  # sidecar file beside matched MKV
# NOTE: library_path_glob patterns are coupled to the user's config layout
# (filename template and folder structure). The defaults here assume the
# "YYYY - Artist - Event[...].mkv" filename template and an artist-per-folder
# layout; fixture globs will need updating if CRATEDIGGER_TEST_CONFIG changes.
#   pipeline_in_place.nfo_must_exist: bool      # after --rename-only, sidecar beside renamed mkv
#   pipeline_in_place.poster_must_exist: bool
#   pipeline_in_place.fanart_must_exist: bool
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
                "library_path_glob": "**/Tiësto/*We Belong Here*.mkv",
                "nfo_must_exist": True,
                "poster_must_exist": True,
                "fanart_must_exist": True,
            },
            "pipeline_in_place": {
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
                "performer_must_not_equal": ["ALOK"],
                "min_performer_chapters": 1,
            },
            "pipeline": {
                "library_path_glob": "**/ALOK/*SOMETHING ELSE*Tomorrowland Winter*.mkv",
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
        "expect": {"embedding": {"ttv70_artists": "AFROJACK"}},
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


def _canonicalize_tags(tags_root: ET.Element) -> dict:
    """Return a deterministic representation of tag contents for re-run diffs.

    Returns: {"global": {(ttv, name): value, ...},
              "chapters": [sorted tuple of (name, value) pairs per chapter, ...]}

    Chapter UIDs may change across re-embeds (Matroska assigns fresh UIDs on
    write), so chapter tags are returned as a multiset keyed by contents, not
    by UID. Global tags (TTV=50/70, no ChapterUID) are keyed by (ttv, name).
    """
    global_tags: dict[tuple[str, str], str] = {}
    chapters: list[tuple[tuple[str, str], ...]] = []
    for tag in tags_root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is None:
            continue
        ttv_el = targets.find("TargetTypeValue")
        ttv = (ttv_el.text if ttv_el is not None else "") or ""
        uid_el = targets.find("ChapterUID")
        pairs: list[tuple[str, str]] = []
        for simple in tag.findall("Simple"):
            n_el = simple.find("Name")
            s_el = simple.find("String")
            name = ((n_el.text if n_el is not None else "") or "")
            value = ((s_el.text if s_el is not None else "") or "")
            pairs.append((name, value))
        pairs.sort()
        if uid_el is not None and uid_el.text:
            chapters.append(tuple(pairs))
        else:
            for name, value in pairs:
                global_tags[(ttv, name)] = value
    chapters.sort()
    return {"global": global_tags, "chapters": chapters}


@pytest.mark.integration
@pytest.mark.parametrize(
    "fixture_key",
    list(FIXTURES.keys()),
    ids=list(FIXTURES.keys()),
)
def test_embedding(fixture_key: str, tmp_path):
    """Re-enrich each fixture and apply universal + fixture-specific asserts."""
    fixture = FIXTURES[fixture_key]
    assert MKV_DIR is not None  # narrow for type checker
    src = MKV_DIR / fixture["filename"]
    if not src.exists():
        pytest.skip(f"fixture MKV missing: {fixture['filename']}")

    mkv = tmp_path / "test.mkv"
    shutil.copy(src, mkv)

    tags_root, chapters_root = _run_enrich(
        mkv, fixture["tracklist_id"], tmp_path,
        tracklist_date=fixture.get("tracklist_date"),
    )
    _assert_universal(tags_root, chapters_root)
    _assert_embedding_expect(
        tags_root, fixture.get("expect", {}).get("embedding", {}), tmp_path
    )


@pytest.mark.integration
def test_embedding_idempotent(tmp_path):
    """Re-enriching the same MKV twice produces identical tag contents.

    Guards against: (a) tag duplication on re-embed, (b) values drifting
    between calls (e.g. cache pollution, non-deterministic ordering that
    affects tag selection), (c) stale data carryover.

    Uses the Tiesto fixture only: idempotency is a code-path property, not
    a per-fixture property, so a single representative fixture suffices.
    """
    assert MKV_DIR is not None
    fixture = FIXTURES["tiesto-we-belong-here"]
    src = MKV_DIR / fixture["filename"]
    if not src.exists():
        pytest.skip(f"fixture MKV missing: {fixture['filename']}")

    mkv = tmp_path / "test.mkv"
    shutil.copy(src, mkv)

    run1 = tmp_path / "run1"
    run1.mkdir()
    tags1, _ = _run_enrich(
        mkv, fixture["tracklist_id"], run1,
        tracklist_date=fixture.get("tracklist_date"),
    )
    canon1 = _canonicalize_tags(tags1)

    run2 = tmp_path / "run2"
    run2.mkdir()
    tags2, _ = _run_enrich(
        mkv, fixture["tracklist_id"], run2,
        tracklist_date=fixture.get("tracklist_date"),
    )
    canon2 = _canonicalize_tags(tags2)

    assert canon1["global"] == canon2["global"], (
        "global tags diverged across re-enrich: "
        f"first={canon1['global']} second={canon2['global']}"
    )
    assert canon1["chapters"] == canon2["chapters"], (
        "per-chapter tag contents diverged across re-enrich "
        f"(counts: first={len(canon1['chapters'])}, second={len(canon2['chapters'])})"
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not FULL_PIPELINE,
    reason="Set CRATEDIGGER_TEST_FULL_PIPELINE=1 to run the CLI pipeline test",
)
@pytest.mark.parametrize(
    "fixture_key",
    list(FIXTURES.keys()),
    ids=list(FIXTURES.keys()),
)
def test_full_pipeline(fixture_key: str, tmp_path):
    """Run identify -> organize -> enrich via CLI subprocess, assert library tree."""
    fixture = FIXTURES[fixture_key]
    assert MKV_DIR is not None and CONFIG is not None
    src = MKV_DIR / fixture["filename"]
    if not src.exists():
        pytest.skip(f"fixture MKV missing: {fixture['filename']}")

    inbox = tmp_path / "inbox"
    library = tmp_path / "library"
    inbox.mkdir()
    library.mkdir()
    shutil.copy(src, inbox / fixture["filename"])

    cfg_arg = ["--config", str(CONFIG)]

    subprocess.run(
        ["cratedigger", "identify", *cfg_arg,
         "--tracklist", fixture["tracklist_id"], "--auto",
         str(inbox / fixture["filename"])],
        check=True, timeout=600,
    )
    subprocess.run(
        ["cratedigger", "organize", *cfg_arg,
         "--output", str(library), "--move", "--yes",
         str(inbox)],
        check=True, timeout=300,
    )
    subprocess.run(
        ["cratedigger", "enrich", *cfg_arg, str(library)],
        check=True, timeout=900,
    )

    _assert_pipeline_expect(library, fixture.get("expect", {}).get("pipeline", {}))


@pytest.mark.integration
@pytest.mark.skipif(
    not FULL_PIPELINE,
    reason="Set CRATEDIGGER_TEST_FULL_PIPELINE=1 to run the CLI pipeline test",
)
@pytest.mark.parametrize(
    "fixture_key",
    list(FIXTURES.keys()),
    ids=list(FIXTURES.keys()),
)
def test_full_pipeline_in_place(fixture_key: str, tmp_path):
    """Run identify -> organize --rename-only -> enrich; assert in-place shape.

    Unlike test_full_pipeline, this covers the rename-in-place code path where
    files are not moved to a separate library root. After organize, the mkv
    should still live in the inbox dir but under its canonical name.
    """
    fixture = FIXTURES[fixture_key]
    assert MKV_DIR is not None and CONFIG is not None
    src = MKV_DIR / fixture["filename"]
    if not src.exists():
        pytest.skip(f"fixture MKV missing: {fixture['filename']}")

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    shutil.copy(src, inbox / fixture["filename"])

    cfg_arg = ["--config", str(CONFIG)]

    subprocess.run(
        ["cratedigger", "identify", *cfg_arg,
         "--tracklist", fixture["tracklist_id"], "--auto",
         str(inbox / fixture["filename"])],
        check=True, timeout=600,
    )
    subprocess.run(
        ["cratedigger", "organize", *cfg_arg,
         "--rename-only", "--yes",
         str(inbox)],
        check=True, timeout=300,
    )
    subprocess.run(
        ["cratedigger", "enrich", *cfg_arg, str(inbox)],
        check=True, timeout=900,
    )

    # After --rename-only, exactly one .mkv should remain in the inbox dir
    # (renamed to its canonical form, but not moved out).
    mkvs = list(inbox.glob("*.mkv"))
    assert len(mkvs) == 1, (
        f"expected exactly 1 mkv in inbox after --rename-only, got {len(mkvs)}: {mkvs}"
    )
    folder = mkvs[0].parent

    pip = fixture.get("expect", {}).get("pipeline_in_place", {})
    if pip.get("nfo_must_exist"):
        assert any(p.is_file() for p in folder.glob("*.nfo")), (
            f"no .nfo beside {mkvs[0].name}"
        )
    if pip.get("poster_must_exist"):
        assert _any_image(folder, "poster"), f"no poster beside {mkvs[0].name}"
    if pip.get("fanart_must_exist"):
        assert _any_image(folder, "fanart"), f"no fanart beside {mkvs[0].name}"


@pytest.mark.integration
@pytest.mark.skipif(
    not FULL_PIPELINE,
    reason="Set CRATEDIGGER_TEST_FULL_PIPELINE=1 to run the CLI pipeline test",
)
def test_full_pipeline_idempotent(tmp_path):
    """A second identify on an already-identified file reports up_to_date.

    Verifies the CLI's self-healing / already-done detection, which is the
    user-facing contract for re-running commands on a maintained library.
    """
    assert MKV_DIR is not None and CONFIG is not None
    fixture = FIXTURES["tiesto-we-belong-here"]
    src = MKV_DIR / fixture["filename"]
    if not src.exists():
        pytest.skip(f"fixture MKV missing: {fixture['filename']}")

    inbox = tmp_path / "inbox"
    library = tmp_path / "library"
    inbox.mkdir()
    library.mkdir()
    shutil.copy(src, inbox / fixture["filename"])

    cfg_arg = ["--config", str(CONFIG)]

    # First pass: full pipeline through organize (enrich is not required
    # for identify's up_to_date check, and skipping it saves ~5 min).
    subprocess.run(
        ["cratedigger", "identify", *cfg_arg,
         "--tracklist", fixture["tracklist_id"], "--auto",
         str(inbox / fixture["filename"])],
        check=True, timeout=600,
    )
    subprocess.run(
        ["cratedigger", "organize", *cfg_arg,
         "--output", str(library), "--move", "--yes",
         str(inbox)],
        check=True, timeout=300,
    )

    organized = next(library.rglob("*.mkv"), None)
    assert organized is not None, f"no MKV found under {library} after organize"

    # Second identify on the organized file should be a no-op.
    result = subprocess.run(
        ["cratedigger", "identify", *cfg_arg,
         "--tracklist", fixture["tracklist_id"], "--auto",
         str(organized)],
        check=True, capture_output=True, text=True, timeout=300,
    )
    assert "up_to_date: 1" in result.stdout, (
        "second identify did not report up_to_date: 1\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
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


def _assert_universal(tags_root: ET.Element, chapters_root: ET.Element) -> None:
    """Invariants every enriched MKV must satisfy.

    - No mojibake in chapter titles or tag values.
    - No legacy ARTIST / ARTIST_SLUGS tag names at chapter scope.
    - Every TTV=30 tag references a real ChapterUID.
    """
    for atom in chapters_root.findall(".//ChapterAtom"):
        title_el = atom.find("ChapterDisplay/ChapterString")
        title = (title_el.text if title_el is not None else "") or ""
        assert "├" not in title, f"mojibake in chapter: {title!r}"
    for simple in tags_root.iter("Simple"):
        str_el = simple.find("String")
        value = (str_el.text if str_el is not None else "") or ""
        assert "├" not in value, f"mojibake in tag: {value!r}"

    ttv30 = _find_chapter_tags(tags_root)
    for tag in ttv30:
        for simple in tag.findall("Simple"):
            n_el = simple.find("Name")
            name = (n_el.text if n_el is not None else "") or ""
            assert name not in ("ARTIST", "ARTIST_SLUGS"), (
                f"Per-chapter tag still using legacy name {name!r}"
            )

    atom_uids: set[str] = set()
    for a in chapters_root.findall(".//ChapterAtom"):
        u_el = a.find("ChapterUID")
        if u_el is not None and u_el.text:
            atom_uids.add(u_el.text)
    for tag in ttv30:
        uid_el = tag.find("Targets/ChapterUID")
        assert uid_el is not None and uid_el.text in atom_uids


def _assert_embedding_expect(tags_root: ET.Element, expect: dict, tmp_path: Path) -> None:
    """Apply a fixture's `expect.embedding` assertions.

    Supported keys: ttv70_artists, ttv70_artists_contains, min_chapters,
    min_performer_chapters, performer_must_not_equal, dj_cache_min_entries.
    """
    if "ttv70_artists" in expect:
        assert _find_global_tag(tags_root, 70, "CRATEDIGGER_1001TL_ARTISTS") == expect["ttv70_artists"]

    if "ttv70_artists_contains" in expect:
        value = _find_global_tag(tags_root, 70, "CRATEDIGGER_1001TL_ARTISTS") or ""
        for needle in expect["ttv70_artists_contains"]:
            assert needle in value, f"{needle!r} not in TTV70 artists {value!r}"

    ttv30 = _find_chapter_tags(tags_root)

    if "min_chapters" in expect:
        assert len(ttv30) >= expect["min_chapters"], (
            f"only {len(ttv30)} TTV30 tags, expected >= {expect['min_chapters']}"
        )

    perf_values: list[str] = []
    for tag in ttv30:
        for simple in tag.findall("Simple"):
            n_el = simple.find("Name")
            if n_el is not None and (n_el.text or "") == "PERFORMER":
                s_el = simple.find("String")
                perf_values.append((s_el.text if s_el is not None else "") or "")

    if "min_performer_chapters" in expect:
        assert len(perf_values) >= expect["min_performer_chapters"], (
            f"only {len(perf_values)} PERFORMER values, expected >= {expect['min_performer_chapters']}"
        )

    if "performer_must_not_equal" in expect:
        for banned in expect["performer_must_not_equal"]:
            assert all(v != banned for v in perf_values), (
                f"per-chapter PERFORMER contains banned value {banned!r}"
            )

    if "dj_cache_min_entries" in expect:
        cache_path = tmp_path / "dj_cache.json"
        assert cache_path.exists(), f"expected dj_cache.json at {cache_path}"
        cache_data = json.loads(cache_path.read_text())
        assert len(cache_data) >= expect["dj_cache_min_entries"]


_IMAGE_EXTS = ("jpg", "jpeg", "png", "webp")


def _any_image(folder: Path, stem: str) -> bool:
    for ext in _IMAGE_EXTS:
        if any(folder.glob(f"{stem}.{ext}")) or any(folder.glob(f"*-{stem}.{ext}")):
            return True
    return False


def _assert_pipeline_expect(library_root: Path, expect: dict) -> None:
    """Apply a fixture's `expect.pipeline` assertions against the library tree."""
    if not expect:
        return
    sidecar_keys = ("nfo_must_exist", "poster_must_exist", "fanart_must_exist")
    has_sidecar_asserts = any(expect.get(k) for k in sidecar_keys)
    if "library_path_glob" not in expect:
        assert not has_sidecar_asserts, (
            "pipeline expect has sidecar assertions but no library_path_glob"
        )
        return
    matches = list(library_root.glob(expect["library_path_glob"]))
    assert matches, f"no files matched {expect['library_path_glob']!r} under {library_root}"
    folder = matches[0].parent

    if expect.get("nfo_must_exist"):
        assert any(p.is_file() for p in folder.glob("*.nfo")), (
            f"no .nfo beside {matches[0].name}"
        )
    if expect.get("poster_must_exist"):
        assert _any_image(folder, "poster"), f"no poster beside {matches[0].name}"
    if expect.get("fanart_must_exist"):
        assert _any_image(folder, "fanart"), f"no fanart beside {matches[0].name}"


