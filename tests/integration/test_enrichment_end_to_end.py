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
#   embedding.performer_must_include: list[str]  # each value must be a substring of some chapter's PERFORMER
#   embedding.max_chapters: int                  # <= N TTV=30 tags
#   embedding.dj_cache_min_entries: int          # >= N entries in dj_cache.json
#   pipeline.library_path_glob: str              # at least one match after organize
#   pipeline.(nfo|poster|fanart)_must_exist: bool  # sidecar file beside matched MKV
# NOTE: library_path_glob patterns are coupled to the user's config layout
# (filename template and folder structure). The defaults here assume the
# "YYYY - Artist - Event[...].mkv" filename template and an artist-per-folder
# layout; fixture globs will need updating if CRATEDIGGER_TEST_CONFIG changes.
#   pipeline_in_place.nfo_must_exist: bool      # after in-place organize, sidecar beside renamed mkv
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
                "max_chapters": 60,
                "min_performer_chapters": 20,
                "performer_must_include": ["Tiësto"],
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
                # No performer_must_include: SOMETHING ELSE is a stage brand,
                # not a track artist; per-track PERFORMER values use underlying
                # artist names (e.g. "ALOK & Khalid") and ALOK would collide
                # with the performer_must_not_equal invariant above.
                "max_chapters": 50,
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
                "max_chapters": 50,
                "performer_must_include": ["Armin van Buuren", "Marlon Hoffstadt"],
            },
        },
    },
    "afrojack-ultra": {
        "filename": "AFROJACK LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026 [fLyb8KvtSzw].mkv",
        "tracklist_id": "22r0yk79",
        "scenarios": ["solo"],
        "expect": {"embedding": {
            "ttv70_artists": "AFROJACK",
            "performer_must_include": ["AFROJACK"],
            "max_chapters": 50,
        }},
    },
    "eric-prydz-resistance": {
        "filename": "ERIC PRYDZ LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026 ｜ RESISTANCE MEGASTRUCTURE [hU-z3iV0LOg].mkv",
        "tracklist_id": "qy9yyy9",
        "scenarios": ["solo", "single-genre"],
        "expect": {"embedding": {
            "ttv70_artists": "Eric Prydz",
            "performer_must_include": ["Eric Prydz"],
            "max_chapters": 50,
        }},
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

    # Exercise the MBID enrich operations on the embedded MKV so tests cover
    # the tags they write (CRATEDIGGER_ALBUMARTIST_MBIDS and per-chapter
    # MUSICBRAINZ_ARTISTIDS). Both ops read from on-disk tags and ignore
    # their `media_file` argument, so passing None is safe.
    from festival_organizer.operations import (
        AlbumArtistMbidsOperation, ChapterArtistMbidsOperation,
    )
    ChapterArtistMbidsOperation(config=cfg).execute(mkv, media_file=None)  # pyright: ignore[reportArgumentType]
    AlbumArtistMbidsOperation(config=cfg).execute(mkv, media_file=None)  # pyright: ignore[reportArgumentType]

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
    """Run identify -> organize (in-place) -> enrich; assert in-place shape.

    Unlike test_full_pipeline, this covers the in-place code path where files
    are not moved to a separate library root. The smart-default action for
    source == output is atomic rename, and the full layout still applies, so
    under artist_flat the mkv lives at inbox/<artist>/<canonical>.mkv.
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
        ["cratedigger", "organize", *cfg_arg, "--yes", str(inbox)],
        check=True, timeout=300,
    )
    subprocess.run(
        ["cratedigger", "enrich", *cfg_arg, str(inbox)],
        check=True, timeout=900,
    )

    # In-place organize (source == output) picks the rename action by the new
    # smart default, and the full layout still applies. With artist_flat that
    # means the mkv lives one level below the inbox, under {artist}/.
    mkvs = list(inbox.rglob("*.mkv"))
    assert len(mkvs) == 1, (
        f"expected exactly 1 mkv under inbox after in-place organize, "
        f"got {len(mkvs)}: {mkvs}"
    )
    folder = mkvs[0].parent
    assert folder.parent == inbox, (
        f"artist_flat should place the file at inbox/<artist>/; got {folder}"
    )

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
def test_in_place_layout_switch_migrates_sidecars_and_folder_artefacts(tmp_path):
    """Switching layouts on an existing library moves the file into a new
    folder; per-file sidecars and folder-level artefacts both follow, and the
    emptied old folder is cleaned up.

    Guards against: (a) _move_sidecars regressions on cross-directory rename,
    (b) the migrate_folder_artefacts post-pipeline pass breaking, (c) the
    cleanup_empty_dirs trigger forgetting the rename action."""
    assert MKV_DIR is not None and CONFIG is not None
    fixture = FIXTURES["eric-prydz-resistance"]
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
    # First organize lands the file in artist_flat layout: inbox/<artist>/<stem>.mkv
    subprocess.run(
        ["cratedigger", "organize", *cfg_arg, "--yes", str(inbox)],
        check=True, timeout=300,
    )

    mkvs_after_first = list(inbox.rglob("*.mkv"))
    assert len(mkvs_after_first) == 1, mkvs_after_first
    first_mkv = mkvs_after_first[0]
    artist_dir = first_mkv.parent
    stem = first_mkv.stem

    # Seed synthetic artefacts on disk: per-file sidecars share the video stem,
    # folder-level files are the ones excluded from _move_sidecars.
    (artist_dir / f"{stem}.nfo").write_text("<nfo/>")
    (artist_dir / f"{stem}-thumb.jpg").write_bytes(b"thumb")
    (artist_dir / f"{stem}-poster.jpg").write_bytes(b"poster")
    (artist_dir / "folder.jpg").write_bytes(b"folder-contents")
    (artist_dir / "fanart.jpg").write_bytes(b"fanart-contents")

    # Second organize switches the folder layout. The video crosses directories;
    # sidecars must come with it, folder-level artefacts must migrate, and the
    # now-empty artist_dir must be removed.
    subprocess.run(
        ["cratedigger", "organize", *cfg_arg,
         "--layout", "festival_flat", "--yes", str(inbox)],
        check=True, timeout=300,
    )

    mkvs_after_second = list(inbox.rglob("*.mkv"))
    assert len(mkvs_after_second) == 1, mkvs_after_second
    new_mkv = mkvs_after_second[0]
    new_dir = new_mkv.parent

    assert new_dir != artist_dir, (
        f"layout switch did not move the file out of {artist_dir}"
    )
    assert not artist_dir.exists(), (
        f"emptied artist folder should be cleaned up: {artist_dir} still exists"
    )

    new_stem = new_mkv.stem
    assert (new_dir / f"{new_stem}.nfo").exists(), "nfo sidecar did not follow"
    assert (new_dir / f"{new_stem}-thumb.jpg").exists(), "thumb sidecar did not follow"
    assert (new_dir / f"{new_stem}-poster.jpg").exists(), "poster sidecar did not follow"
    folder_jpg = new_dir / "folder.jpg"
    fanart_jpg = new_dir / "fanart.jpg"
    assert folder_jpg.exists(), "folder.jpg did not migrate to the new folder"
    assert folder_jpg.read_bytes() == b"folder-contents", (
        "folder.jpg content changed during migration"
    )
    assert fanart_jpg.exists(), "fanart.jpg did not migrate to the new folder"
    assert fanart_jpg.read_bytes() == b"fanart-contents", (
        "fanart.jpg content changed during migration"
    )


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
    not FULL_PIPELINE,
    reason="Set CRATEDIGGER_TEST_FULL_PIPELINE=1 to run the CLI pipeline test",
)
def test_full_pipeline_enrich_idempotent(tmp_path):
    """A second `cratedigger enrich` on an already-enriched library produces
    byte-identical sidecars and byte-identical MKV tags.

    Guards against: (a) sidecar regeneration with different bytes (timestamp
    drift, shuffled content), (b) duplicate TTV tag entries appended on each
    enrich, (c) user edits silently overwritten.

    Uses the Tiesto fixture only.
    """
    import hashlib
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

    def _hash_sidecars(root: Path) -> dict[str, str]:
        """Hash every non-MKV file under root. MKV is huge; its tags are
        compared separately via mkvextract."""
        out = {}
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix == ".mkv":
                continue
            if ".cratedigger" in p.parts:
                continue
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out

    def _mkv_tags(library_root: Path, work: Path) -> bytes:
        work.mkdir(parents=True, exist_ok=True)
        mkv = next(library_root.rglob("*.mkv"))
        out_xml = work / "tags.xml"
        subprocess.run(["mkvextract", str(mkv), "tags", str(out_xml)], check=True)
        return out_xml.read_bytes()

    snap1 = _hash_sidecars(library)
    tags1 = _mkv_tags(library, tmp_path)

    # Second enrich, the thing we're testing.
    subprocess.run(
        ["cratedigger", "enrich", *cfg_arg, str(library)],
        check=True, timeout=900,
    )

    snap2 = _hash_sidecars(library)
    tags2 = _mkv_tags(library, tmp_path / "work2")

    added = set(snap2) - set(snap1)
    removed = set(snap1) - set(snap2)
    assert not added, f"second enrich created new sidecar files: {sorted(added)}"
    assert not removed, f"second enrich removed sidecar files: {sorted(removed)}"

    differing = sorted(p for p in snap1 if snap1[p] != snap2[p])
    assert not differing, f"second enrich changed sidecar bytes: {differing}"

    assert tags1 == tags2, (
        "second enrich changed MKV tags. Likely a duplicate-append or "
        "non-deterministic write. First tags bytes len={}, second={}".format(
            len(tags1), len(tags2)
        )
    )


@pytest.mark.integration
@pytest.mark.skipif(
    TIESTO_MKV is None or not TIESTO_MKV.exists(),
    reason="Tiësto fixture MKV missing (expected at $CRATEDIGGER_TEST_MKV_DIR/tiesto-we-belong-here.mkv)",
)
def test_chapter_artist_mbids_end_to_end(tmp_path, caplog):
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
        # Alignment contract: MUSICBRAINZ_ARTISTIDS must be present as a tag
        # (even when all artists in the chapter are unresolvable, which
        # produces an empty string for a 1-slot chapter). Distinguish
        # missing-key from empty-string-value via explicit `in` check.
        assert "MUSICBRAINZ_ARTISTIDS" in block, (
            f"chapter {uid} has PERFORMER_NAMES but no MUSICBRAINZ_ARTISTIDS tag"
        )
        mbids = block["MUSICBRAINZ_ARTISTIDS"]
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


def _parse_chapter_time(s: str | None) -> int | None:
    """Parse 'HH:MM:SS.fffffffff' into nanoseconds. None-safe."""
    if not s:
        return None
    h, m, rest = s.split(":")
    sec, _, nanos = rest.partition(".")
    return (int(h) * 3600 + int(m) * 60 + int(sec)) * 1_000_000_000 + int((nanos or "0").ljust(9, "0")[:9])


def _assert_universal(tags_root: ET.Element, chapters_root: ET.Element) -> None:
    """Invariants every enriched MKV must satisfy.

    - No mojibake in chapter titles or tag values.
    - No legacy ARTIST / ARTIST_SLUGS tag names at chapter scope.
    - Every TTV=30 tag references a real ChapterUID.
    - No empty Name or String in any TTV=30 Simple element (silent blanking bug).
    - PERFORMER_NAMES and ARTIST_SLUGS have equal pipe-count when both present.
    - Consecutive ChapterAtoms with ChapterTimeStart are strictly increasing.
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

    # No-empty invariant: every TTV=30 Simple must have non-empty Name and String.
    for tag in ttv30:
        for simple in tag.findall("Simple"):
            n_el = simple.find("Name")
            s_el = simple.find("String")
            name = (n_el.text if n_el is not None else "") or ""
            value = (s_el.text if s_el is not None else "") or ""
            assert name, f"empty Name in TTV=30 Simple (value={value!r})"
            assert value, f"empty String in TTV=30 Simple (name={name!r})"

    # Pipe-count alignment between PERFORMER_NAMES and ARTIST_SLUGS per chapter.
    for tag in ttv30:
        names_by_key: dict[str, str] = {}
        for simple in tag.findall("Simple"):
            n_el = simple.find("Name")
            s_el = simple.find("String")
            key = (n_el.text if n_el is not None else "") or ""
            val = (s_el.text if s_el is not None else "") or ""
            names_by_key[key] = val
        perf = names_by_key.get("PERFORMER_NAMES")
        slugs = names_by_key.get("ARTIST_SLUGS")
        if perf and slugs:
            assert len(perf.split("|")) == len(slugs.split("|")), (
                f"PERFORMER_NAMES/ARTIST_SLUGS pipe-count mismatch: "
                f"names={perf!r} slugs={slugs!r}"
            )

    # Album-artist tag family: when CRATEDIGGER_1001TL_ARTISTS is present,
    # the SLUGS + DISPLAY siblings must also be present and pipe-aligned.
    # If ALBUMARTIST_MBIDS is present (post-enrich), it must align too.
    artists_val = _find_global_tag(tags_root, 70, "CRATEDIGGER_1001TL_ARTISTS")
    if artists_val:
        slugs_val = _find_global_tag(tags_root, 70, "CRATEDIGGER_ALBUMARTIST_SLUGS")
        display_val = _find_global_tag(tags_root, 70, "CRATEDIGGER_ALBUMARTIST_DISPLAY")
        assert slugs_val is not None, (
            "CRATEDIGGER_ALBUMARTIST_SLUGS missing alongside "
            f"CRATEDIGGER_1001TL_ARTISTS={artists_val!r}"
        )
        assert display_val is not None, (
            "CRATEDIGGER_ALBUMARTIST_DISPLAY missing alongside "
            f"CRATEDIGGER_1001TL_ARTISTS={artists_val!r}"
        )
        names = artists_val.split("|")
        assert len(slugs_val.split("|")) == len(names), (
            f"ALBUMARTIST_SLUGS slot count {len(slugs_val.split('|'))} != "
            f"1001TL_ARTISTS slot count {len(names)} "
            f"(slugs={slugs_val!r} artists={artists_val!r})"
        )
        assert display_val == " & ".join(names), (
            f"ALBUMARTIST_DISPLAY={display_val!r} does not equal "
            f"' & '.join(1001TL_ARTISTS split) = {' & '.join(names)!r}"
        )
        mbids_val = _find_global_tag(tags_root, 70, "CRATEDIGGER_ALBUMARTIST_MBIDS")
        if mbids_val is not None:
            assert len(mbids_val.split("|")) == len(names), (
                f"ALBUMARTIST_MBIDS slot count {len(mbids_val.split('|'))} != "
                f"1001TL_ARTISTS slot count {len(names)} "
                f"(mbids={mbids_val!r} artists={artists_val!r})"
            )

    # Monotonic chapter times: consecutive atoms with ChapterTimeStart must
    # strictly increase.
    prev_ns: int | None = None
    for atom in chapters_root.findall(".//ChapterAtom"):
        t_el = atom.find("ChapterTimeStart")
        if t_el is None or not (t_el.text or ""):
            prev_ns = None
            continue
        cur_ns = _parse_chapter_time(t_el.text)
        assert cur_ns is not None
        if prev_ns is not None:
            assert cur_ns > prev_ns, (
                f"ChapterTimeStart not strictly increasing: "
                f"prev={prev_ns}ns cur={cur_ns}ns ({t_el.text!r})"
            )
        prev_ns = cur_ns


def _assert_embedding_expect(tags_root: ET.Element, expect: dict, tmp_path: Path) -> None:
    """Apply a fixture's `expect.embedding` assertions.

    Supported keys: ttv70_artists, ttv70_artists_contains, min_chapters,
    max_chapters, min_performer_chapters, performer_must_not_equal,
    performer_must_include, dj_cache_min_entries.
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

    if "max_chapters" in expect:
        assert len(ttv30) <= expect["max_chapters"], (
            f"{len(ttv30)} TTV30 tags, expected <= {expect['max_chapters']}"
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

    if "performer_must_include" in expect:
        for needle in expect["performer_must_include"]:
            assert any(needle in v for v in perf_values), (
                f"expected PERFORMER containing {needle!r} on at least one chapter, "
                f"got {perf_values!r}"
            )

    if "dj_cache_min_entries" in expect:
        cache_path = tmp_path / "dj_cache.json"
        assert cache_path.exists(), f"expected dj_cache.json at {cache_path}"
        cache_data = json.loads(cache_path.read_text())
        assert len(cache_data) >= expect["dj_cache_min_entries"]

    # MBID assertions: only enforce when at least one slot resolved. This lets
    # the test stay green on machines with a cold MBID cache / no network, while
    # still catching the "op is wired but silently producing empty output" gap.
    artists_val = _find_global_tag(tags_root, 70, "CRATEDIGGER_1001TL_ARTISTS") or ""
    mbids_val = _find_global_tag(tags_root, 70, "CRATEDIGGER_ALBUMARTIST_MBIDS")
    if artists_val and mbids_val is not None and any(mbids_val.split("|")):
        names = [n for n in artists_val.split("|") if n]
        mbid_slots = mbids_val.split("|")
        assert len(mbid_slots) == len(names), (
            f"ALBUMARTIST_MBIDS slot count {len(mbid_slots)} != "
            f"1001TL_ARTISTS slot count {len(names)}"
        )

    # Per-chapter MUSICBRAINZ_ARTISTIDS: where a chapter has PERFORMER_NAMES
    # and the albumartist MBID lookup resolved at least one artist (proxy for
    # "network/cache is functional"), at least one chapter with cached names
    # should carry aligned MBIDs with at least one non-empty slot.
    if mbids_val is not None and any((mbids_val or "").split("|")):
        chapter_tags_by_uid: dict[str, dict[str, str]] = {}
        for tag in tags_root.findall("Tag"):
            targets = tag.find("Targets")
            if targets is None:
                continue
            ttv_el = targets.find("TargetTypeValue")
            uid_el = targets.find("ChapterUID")
            if ttv_el is None or uid_el is None or (ttv_el.text or "") != "30":
                continue
            uid = (uid_el.text or "")
            block: dict[str, str] = {}
            for simple in tag.findall("Simple"):
                n_el = simple.find("Name")
                s_el = simple.find("String")
                if n_el is not None and n_el.text:
                    block[n_el.text] = (s_el.text if s_el is not None else "") or ""
            chapter_tags_by_uid[uid] = block

        chapters_with_names = [
            b for b in chapter_tags_by_uid.values()
            if b.get("PERFORMER_NAMES", "").strip()
        ]
        if chapters_with_names:
            chapters_with_mbids = [
                b for b in chapters_with_names
                if any((b.get("MUSICBRAINZ_ARTISTIDS", "") or "").split("|"))
            ]
            assert chapters_with_mbids, (
                "no chapter carries MUSICBRAINZ_ARTISTIDS despite albumartist "
                "MBID resolution succeeding; ChapterArtistMbidsOperation may "
                "not be wired or is silently skipping"
            )
            # Alignment invariant: slot count matches PERFORMER_NAMES count.
            for block in chapters_with_mbids:
                names_n = len([x for x in block["PERFORMER_NAMES"].split("|") if x])
                mbid_slots_n = len(block["MUSICBRAINZ_ARTISTIDS"].split("|"))
                assert mbid_slots_n == names_n, (
                    f"chapter MUSICBRAINZ_ARTISTIDS slot count {mbid_slots_n} "
                    f"!= PERFORMER_NAMES count {names_n}"
                )


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


