# Display Artist Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve B2B/collab artist names in filenames and TITLE tags while keeping the primary artist for folder grouping and Plex's ARTIST tag.

**Architecture:** New `display_artist` field on `MediaFile` holds the full multi-artist name (e.g. "Martin Garrix & Alesso"). Derived from 1001TL title or filename parsing — never from the ARTIST tag (which intentionally stores the primary-only artist for Plex grouping). Used in filenames and TITLE tags. Additionally, scan output shows the full target path, and organize defaults to copy.

**Tech Stack:** Python, pytest, mkvpropedit (MKV tags)

---

### Task 1: Add `display_artist` field to MediaFile

**Files:**
- Modify: `festival_organizer/models.py:7-17`
- Test: `tests/test_models.py`

**Step 1: Write the failing test**

In `tests/test_models.py`, add:

```python
def test_display_artist_defaults_empty():
    mf = MediaFile(source_path=Path("test.mkv"))
    assert mf.display_artist == ""


def test_display_artist_set_explicitly():
    mf = MediaFile(source_path=Path("test.mkv"), display_artist="Martin Garrix & Alesso")
    assert mf.display_artist == "Martin Garrix & Alesso"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_display_artist_defaults_empty tests/test_models.py::test_display_artist_set_explicitly -v`
Expected: FAIL with `TypeError` (unexpected keyword argument)

**Step 3: Write minimal implementation**

In `festival_organizer/models.py`, add after `artist: str = ""` (line 12):

```python
    display_artist: str = ""  # Full multi-artist name for filenames/titles
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add festival_organizer/models.py tests/test_models.py
git commit -m "feat: add display_artist field to MediaFile"
```

---

### Task 2: Populate `display_artist` in analyzer

The `display_artist` must be derived from the same priority stack as `artist` but **skipping the ARTIST tag** (Layer 3 direct tag). This is because `embed_tags` intentionally writes the primary-only artist to ARTIST for Plex grouping — reading it back would lose the B2B info.

**Priority for `display_artist`:**
1. 1001TL title parse → artist field (highest, Layer 4)
2. Filename parse (Layer 2)
3. Parent directory (Layer 1, lowest)
4. ARTIST tag — **NEVER** used for display_artist

Then normalize but do NOT run `resolve_artist()`.

**Files:**
- Modify: `festival_organizer/analyzer.py:29-147`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing tests**

Add to `tests/test_analyzer.py`:

```python
def test_display_artist_from_1001tl_b2b():
    """display_artist preserves full B2B name from 1001TL title."""
    fake_meta = {
        "title": "MARTIN GARRIX B2B ALESSO LIVE @ RED ROCKS 2025",
        "tracklists_title": "Martin Garrix & Alesso @ Red Rocks Amphitheatre, United States 2025-10-24",
        "tracklists_url": "https://www.1001tracklists.com/tracklist/20uhfc4k/",
        "artist_tag": "Martin Garrix, Alesso",
        "date_tag": "",
        "duration_seconds": 3600.0, "width": 1920, "height": 1080,
        "video_format": "VP9", "audio_format": "Opus",
        "audio_bitrate": "", "overall_bitrate": "",
        "has_cover": True, "description": "", "comment": "", "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("D:/TEMP/_ORG/MARTIN GARRIX B2B ALESSO LIVE @ RED ROCKS 2025 [J8P_X7Fc5as].mkv"),
            Path("D:/TEMP/_ORG"),
            CFG,
        )
    assert mf.artist == "Martin Garrix"  # primary for folders
    assert mf.display_artist == "Martin Garrix & Alesso"  # full for filenames


def test_display_artist_solo_matches_artist():
    """For solo artists, display_artist equals artist."""
    fake_meta = {
        "title": "MARTIN GARRIX LIVE @ AMF 2024",
        "tracklists_title": "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands 2024-10-19",
        "tracklists_url": "https://www.1001tracklists.com/tracklist/qv6kl89/",
        "artist_tag": "",
        "date_tag": "",
        "duration_seconds": 7200.0, "width": 3840, "height": 2160,
        "video_format": "VP9", "audio_format": "Opus",
        "audio_bitrate": "125000", "overall_bitrate": "13500000",
        "has_cover": True, "description": "", "comment": "", "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("//hyperv/Data/Concerts/AMF/2024 - AMF/MARTIN GARRIX LIVE @ AMF 2024.mkv"),
            Path("//hyperv/Data/Concerts"),
            CFG,
        )
    assert mf.artist == "Martin Garrix"
    assert mf.display_artist == "Martin Garrix"


def test_display_artist_ignores_artist_tag():
    """display_artist is NOT derived from ARTIST tag (which stores primary only)."""
    fake_meta = {
        "title": "", "tracklists_title": "", "tracklists_url": "",
        "artist_tag": "Martin Garrix",  # primary only, written by embed_tags
        "date_tag": "", "duration_seconds": None,
        "width": None, "height": None,
        "video_format": "", "audio_format": "",
        "audio_bitrate": "", "overall_bitrate": "",
        "has_cover": False, "description": "", "comment": "", "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("/library/Martin Garrix/2025 - Red Rocks - Martin Garrix & Alesso.mkv"),
            Path("/library"),
            CFG,
        )
    # Filename gives "Martin Garrix & Alesso", ARTIST tag gives "Martin Garrix"
    # display_artist should come from filename (skip ARTIST tag)
    assert mf.display_artist == "Martin Garrix & Alesso"
    assert mf.artist == "Martin Garrix"  # resolved primary


def test_display_artist_filename_only_b2b():
    """display_artist works from filename alone (no tags)."""
    with patch("festival_organizer.analyzer.extract_metadata", return_value={}):
        mf = analyse_file(
            Path("/downloads/MARTIN GARRIX B2B ALESSO LIVE @ RED ROCKS 2025.mkv"),
            Path("/downloads"),
            CFG,
        )
    assert mf.display_artist == "Martin Garrix B2B Alesso"
    assert mf.artist == "Martin Garrix"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py -v -k "display_artist"`
Expected: FAIL (MediaFile doesn't have display_artist populated)

**Step 3: Write the implementation**

In `festival_organizer/analyzer.py`, modify the section after Layer 4 (around line 100). The key change is building a separate `display_artist` value that uses the same priority stack but skips the ARTIST tag:

```python
    # Build display_artist: same priority but skip ARTIST tag (Layer 3 direct)
    # This preserves full B2B/collab names in filenames and TITLE tags,
    # while ARTIST tag (written by embed_tags) holds primary-only for Plex.
    display_artist_info: dict[str, str] = {"artist": ""}
    # Layer 1: parent dir
    if parent_info.get("artist"):
        display_artist_info["artist"] = parent_info["artist"]
    # Layer 2: filename parse (overwrites)
    if filename_info.get("artist"):
        display_artist_info["artist"] = filename_info["artist"]
    # Layer 3: SKIP the ARTIST tag — intentionally omitted
    # Layer 4: 1001TL (highest priority, overwrites)
    if tracklists_info and tracklists_info.get("artist"):
        display_artist_info["artist"] = tracklists_info["artist"]

    display_artist = normalise_name(display_artist_info["artist"])
```

Then in the MediaFile constructor (around line 115), add:

```python
        display_artist=display_artist,
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `pytest -x`
Expected: ALL PASS (no regressions — display_artist defaults to "" everywhere else)

**Step 6: Commit**

```bash
git add festival_organizer/analyzer.py tests/test_analyzer.py
git commit -m "feat: populate display_artist from 1001TL/filename, skip ARTIST tag"
```

---

### Task 3: Use `display_artist` in filename rendering

The filename template `{year} - {festival} - {artist}` should use `display_artist` for the artist substitution in **filenames only**. Folder templates must keep using `artist` (primary).

**Files:**
- Modify: `festival_organizer/templates.py:63-79` (`_build_values`)
- Modify: `festival_organizer/templates.py:26-60` (`render_filename`)
- Test: `tests/test_templates.py`

**Step 1: Write the failing tests**

Add to `tests/test_templates.py`:

```python
def test_render_filename_uses_display_artist():
    """Filename uses display_artist (full B2B name), not artist (primary)."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        year="2025",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2025 - Red Rocks - Martin Garrix & Alesso.mkv"


def test_render_filename_display_artist_empty_falls_back():
    """When display_artist is empty, filename falls back to artist."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="",
        festival="AMF",
        year="2024",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2024 - AMF - Martin Garrix.mkv"


def test_render_folder_uses_primary_artist_not_display():
    """Folder path uses primary artist, never display_artist."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        year="2025",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG)
    assert result == "Martin Garrix"
    result_nested = render_folder(mf, CFG, layout_name="artist_nested")
    assert result_nested == "Martin Garrix/Red Rocks/2025"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_templates.py -v -k "display_artist"`
Expected: FAIL (filename still uses primary artist)

**Step 3: Write the implementation**

Change `_build_values` to accept a `for_filename` flag, or better: have `render_filename` pass `display_artist` into the values dict.

In `festival_organizer/templates.py`, modify `_build_values` to accept an optional `display_artist` override:

```python
def _build_values(media_file: MediaFile, config: Config, *, for_filename: bool = False) -> dict[str, str]:
    """Build the substitution values dict for a media file."""
    festival = media_file.festival
    if festival:
        festival = config.get_festival_display(festival, media_file.location)

    # For filenames, use display_artist (full B2B name); for folders, use artist (primary)
    artist = media_file.artist
    if for_filename and media_file.display_artist:
        artist = media_file.display_artist

    return {
        "artist": safe_filename(artist),
        "festival": safe_filename(festival),
        "year": media_file.year,
        "date": media_file.date,
        "location": safe_filename(media_file.location),
        "stage": safe_filename(media_file.stage),
        "set_title": safe_filename(media_file.set_title),
        "title": safe_filename(media_file.title or media_file.set_title),
    }
```

In `render_filename` (line 39), change the call to:

```python
    values = _build_values(media_file, config, for_filename=True)
```

`render_folder` (line 22) stays unchanged — it already calls `_build_values(media_file, config)` which defaults to `for_filename=False`.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_templates.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/templates.py tests/test_templates.py
git commit -m "feat: filename rendering uses display_artist for B2B names"
```

---

### Task 4: Use `display_artist` in TITLE tags (embed_tags + NFO)

Both `embed_tags.py` and `nfo.py` construct a TITLE like `"Artist @ Stage, Festival"`. The artist portion should use `display_artist`. The ARTIST tag and NFO `<artist>` element stay as `media_file.artist` (primary only, for Plex grouping).

**Files:**
- Modify: `festival_organizer/embed_tags.py:36-54`
- Modify: `festival_organizer/nfo.py:24-41`
- Test: `tests/test_embed_tags.py`
- Test: `tests/test_nfo.py`

**Step 1: Write the failing tests**

Add to `tests/test_embed_tags.py`:

```python
def test_embed_tags_b2b_artist_in_title_not_artist_tag(tmp_path):
    """TITLE uses display_artist (B2B), ARTIST stays primary for Plex."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        year="2025",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    assert tags_dict[50]["ARTIST"] == "Martin Garrix"  # primary for Plex
    assert tags_dict[50]["TITLE"] == "Martin Garrix & Alesso"  # display for title


def test_embed_tags_b2b_with_stage_in_title(tmp_path):
    """TITLE with stage uses display_artist for B2B."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        stage="Main Stage",
        year="2025",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    assert tags_dict[50]["ARTIST"] == "Martin Garrix"
    assert tags_dict[50]["TITLE"] == "Martin Garrix & Alesso @ Main Stage, Red Rocks"
```

Add to `tests/test_nfo.py`:

```python
def test_nfo_title_uses_display_artist_for_b2b(tmp_path):
    """NFO title uses display_artist for B2B sets."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        stage="Main Stage",
        festival="Red Rocks",
        year="2025",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix & Alesso @ Main Stage, Red Rocks"
    assert root.find("artist").text == "Martin Garrix"  # primary for Plex


def test_nfo_title_display_artist_no_stage(tmp_path):
    """NFO title without stage still uses display_artist."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        year="2025",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix & Alesso"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embed_tags.py tests/test_nfo.py -v -k "b2b or display_artist"`
Expected: FAIL

**Step 3: Write the implementation**

In `festival_organizer/embed_tags.py`, change the TITLE construction (lines 39-52) to use `display_artist`:

```python
    if media_file.content_type == "festival_set":
        title_artist = media_file.display_artist or media_file.artist or "Unknown Artist"
        if media_file.stage:
            parts = [f"{title_artist} @ {media_file.stage}"]
            if media_file.festival:
                festival = media_file.festival
                if media_file.set_title:
                    festival = f"{festival} {media_file.set_title}"
                parts.append(festival)
            title = ", ".join(parts)
        else:
            title = title_artist
    else:
        title = media_file.title or media_file.set_title or ""
```

Note: line 37 `tags["ARTIST"] = media_file.artist` stays unchanged (primary for Plex).

In `festival_organizer/nfo.py`, make the same change (lines 24-35):

```python
    if mf.content_type == "festival_set":
        title_artist = mf.display_artist or mf.artist or "Unknown Artist"
        if mf.stage:
            parts = [f"{title_artist} @ {mf.stage}"]
            if mf.festival:
                festival = mf.festival
                if mf.set_title:
                    festival = f"{festival} {mf.set_title}"
                parts.append(festival)
            title = ", ".join(parts)
        else:
            title = title_artist
    else:
        title = mf.title or mf.artist or "Unknown"
```

Note: line 41 `_add(root, "artist", mf.artist or "Unknown Artist")` stays unchanged.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embed_tags.py tests/test_nfo.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/embed_tags.py festival_organizer/nfo.py tests/test_embed_tags.py tests/test_nfo.py
git commit -m "feat: TITLE tags use display_artist for B2B, ARTIST stays primary"
```

---

### Task 5: Scan output shows full target path

Currently scan shows only `-> Martin Garrix/`. It should show `-> Martin Garrix/2025 - Red Rocks - Martin Garrix & Alesso.mkv`.

The runner.py also has a bug: it shows only `op.target.parent.name` (last path component) instead of the relative path.

**Files:**
- Modify: `festival_organizer/cli.py:257-263`
- Modify: `festival_organizer/runner.py:29-34`
- Modify: `festival_organizer/progress.py:49-57`
- Test: `tests/test_cli.py` (or manual verification)

**Step 1: Check existing test coverage for scan output**

Read `tests/test_cli.py` to see if scan output is tested. If not, add a test.

**Step 2: Write the implementation**

In `festival_organizer/cli.py`, change the scan display (lines 257-263):

```python
        if args.command == "scan":
            target_folder = render_folder(mf, config)
            target_name = render_filename(mf, config)
            target = output / target_folder / target_name
            progress.file_start(fp, target_folder + "/" + target_name)
            progress.file_done([])
            continue
```

In `festival_organizer/runner.py`, fix the organize display (lines 29-34) to show relative path from output dir:

```python
        target_folder = ""
        for op in operations:
            if op.name == "organize" and hasattr(op, "target"):
                target_folder = str(op.target.parent.name) + "/" + op.target.name
                break
```

**Step 3: Run tests**

Run: `pytest tests/test_cli.py tests/test_runner.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add festival_organizer/cli.py festival_organizer/runner.py
git commit -m "feat: scan and organize output show full target path"
```

---

### Task 6: Default organize to copy, make move opt-in

**Files:**
- Modify: `festival_organizer/cli.py:65-68` (argument parsing)
- Modify: `festival_organizer/cli.py:270-271` (action selection)
- Modify: `festival_organizer/cli.py:323-325` (post-pipeline cleanup)

**Step 1: Write the implementation**

In `festival_organizer/cli.py`, change the organize argument (line 67):

Replace:
```python
    org_p.add_argument("--copy", action="store_true", help="Copy instead of move")
```

With:
```python
    org_p.add_argument("--move", action="store_true", help="Move instead of copy (default: copy)")
```

Change the action selection (lines 270-271):

Replace:
```python
            action = "copy" if getattr(args, "copy", False) else \
                     "rename" if getattr(args, "rename_only", False) else "move"
```

With:
```python
            action = "move" if getattr(args, "move", False) else \
                     "rename" if getattr(args, "rename_only", False) else "copy"
```

Change the post-pipeline cleanup check (lines 323-325):

Replace:
```python
            action = "copy" if getattr(args, "copy", False) else \
                     "rename" if getattr(args, "rename_only", False) else "move"
            if action == "move" and root.resolve() != output.resolve():
```

With:
```python
            action = "move" if getattr(args, "move", False) else \
                     "rename" if getattr(args, "rename_only", False) else "copy"
            if action == "move" and root.resolve() != output.resolve():
```

**Step 2: Run tests**

Run: `pytest tests/test_cli.py tests/test_cli_postprocess.py -v`
Expected: Check for any tests that assume `--copy` flag or default move behavior and update them.

**Step 3: Commit**

```bash
git add festival_organizer/cli.py
git commit -m "feat: organize defaults to copy, --move flag for move"
```

---

### Task 7: Add `display_artist` to CSV logging

**Files:**
- Modify: `festival_organizer/logging_util.py:18-24` (CSV_FIELDS)
- Modify: `festival_organizer/logging_util.py:37-57` (log_action row)

**Step 1: Write the implementation**

In `festival_organizer/logging_util.py`, add `"display_artist"` to `CSV_FIELDS` after `"artist"`:

```python
CSV_FIELDS = [
    "status", "source", "target",
    "artist", "display_artist", "festival", "year", "date", "set_title",
    "stage", "location", "content_type", "file_type",
    "resolution", "duration", "video_format", "audio_format",
    "metadata_source", "tracklists_url", "error",
]
```

In `log_action`, add the field to the row dict:

```python
            "artist": mf.artist,
            "display_artist": mf.display_artist,
```

**Step 2: Run tests**

Run: `pytest tests/test_logging_util.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add festival_organizer/logging_util.py
git commit -m "feat: include display_artist in CSV action logs"
```

---

### Task 8: Full integration test and regression check

**Step 1: Run the full test suite**

Run: `pytest -v`
Expected: ALL PASS

**Step 2: Verify existing tests still pass with correct semantics**

Key tests to verify haven't broken:
- `test_analyse_with_1001tl_overrides_filename` — artist should still be "Martin Garrix"
- `test_render_filename_festival_set` — should still produce "2024 - AMF - Martin Garrix.mkv" (no display_artist set)
- `test_embed_tags_calls_write_merged_tags` — ARTIST should still be "Afrojack"
- `test_nfo_title_includes_set_title` — set_title WE2 should still work alongside display_artist

**Step 3: Commit all remaining changes (if any)**

```bash
git commit -m "test: verify display_artist integration, no regressions"
```
