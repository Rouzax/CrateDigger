# Fix NFO/Art Generation for Already-Organized Files

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** NFO generation and art extraction must run for files already at their target location (status "skipped"), not just for freshly moved files (status "done").

**Architecture:** The root cause is in `cli.py:174` — post-move tasks only fire when `a.status == "done"`. Files already in place get `status = "skipped"` from the executor and are silently ignored. The fix separates "post-processing" (NFO/art) from "file movement" so they run regardless of move status. The executor stays untouched — it correctly skips moves. The CLI orchestration layer gets the fix.

**Tech Stack:** Python, pytest

---

## Problem Analysis

Current flow for `execute` command:
1. Scan, analyse, classify, plan actions
2. `execute_actions()` runs — sets `status = "done"` or `"skipped"`
3. Post-processing loop checks `if a.status == "done":` — **skipped files never get NFO/art**

The `nfo` and `extract-art` standalone subcommands work correctly (they bypass the executor entirely), so the bug is isolated to the `execute` subcommand with `--generate-nfo` / `--extract-art` flags.

## Design Decision: Where the file lives after execution

For **done** actions: the file is at `a.target` (it was moved there).
For **skipped** actions: the file is at `a.source` (it didn't move; `source == target` after resolve).

Both `generate_nfo()` and `extract_cover()` need the path to the actual file on disk. We need to use the right path depending on status.

## File Structure

- Modify: `festival_organizer/cli.py:167-178` — fix post-processing condition
- Modify: `festival_organizer/logging_util.py:63-76` — show NFO/art activity for skipped files
- Test: `tests/test_executor.py` — add test for NFO/art on skipped files
- Test: `tests/test_cli_postprocess.py` (new) — end-to-end test of execute with flags on already-organized files

---

### Task 1: Add unit test for post-processing on skipped files

**Files:**
- Create: `tests/test_cli_postprocess.py`

- [ ] **Step 1: Write the failing test**

```python
"""Test that --generate-nfo and --extract-art work for files already at target."""
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from festival_organizer.models import FileAction, MediaFile


def _make_media_file(path: Path) -> MediaFile:
    return MediaFile(
        source_path=path,
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        content_type="festival_set",
        extension=".mkv",
        has_cover=True,
    )


def test_execute_generates_nfo_for_skipped_file():
    """When a file is already at target, --generate-nfo should still create an NFO."""
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "Artist" / "2024 - AMF - Martin Garrix.mkv"
        video.parent.mkdir(parents=True)
        video.write_text("fake video")

        mf = _make_media_file(video)
        action = FileAction(
            source=video,
            target=video,  # same path = will be skipped
            media_file=mf,
            action="move",
            generate_nfo=True,
            extract_art=False,
        )

        from festival_organizer.executor import execute_actions
        execute_actions([action])
        assert action.status == "skipped"

        # Now simulate what CLI does post-execution
        from festival_organizer.cli import _run_post_processing
        from festival_organizer.config import Config, DEFAULT_CONFIG
        config = Config(DEFAULT_CONFIG)

        _run_post_processing(action, config)

        nfo_path = video.with_suffix(".nfo")
        assert nfo_path.exists(), "NFO should be generated for skipped file"


def test_execute_extracts_art_for_skipped_file():
    """When a file is already at target, --extract-art should still attempt extraction."""
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "Artist" / "2024 - AMF - Martin Garrix.mkv"
        video.parent.mkdir(parents=True)
        video.write_text("fake video")

        mf = _make_media_file(video)
        action = FileAction(
            source=video,
            target=video,
            media_file=mf,
            action="move",
            generate_nfo=False,
            extract_art=True,
        )

        from festival_organizer.executor import execute_actions
        execute_actions([action])

        from festival_organizer.cli import _run_post_processing
        from festival_organizer.config import Config, DEFAULT_CONFIG
        config = Config(DEFAULT_CONFIG)

        with patch("festival_organizer.cli.extract_cover") as mock_extract:
            mock_extract.return_value = video.parent / "poster.png"
            _run_post_processing(action, config)
            mock_extract.assert_called_once_with(video, video.parent)


def test_no_post_processing_for_errored_file():
    """Errored files should NOT get post-processing."""
    action = FileAction(
        source=Path("C:/nonexistent.mkv"),
        target=Path("C:/out.mkv"),
        media_file=MediaFile(source_path=Path("C:/nonexistent.mkv")),
        action="move",
        status="error",
        error="file not found",
        generate_nfo=True,
        extract_art=True,
    )

    from festival_organizer.cli import _run_post_processing
    from festival_organizer.config import Config, DEFAULT_CONFIG
    config = Config(DEFAULT_CONFIG)

    with patch("festival_organizer.cli.generate_nfo") as mock_nfo:
        with patch("festival_organizer.cli.extract_cover") as mock_art:
            _run_post_processing(action, config)
            mock_nfo.assert_not_called()
            mock_art.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_postprocess.py -v`
Expected: FAIL — `_run_post_processing` does not exist yet

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_postprocess.py
git commit -m "test: add failing tests for NFO/art on skipped files"
```

---

### Task 2: Extract post-processing into a helper function in cli.py

**Files:**
- Modify: `festival_organizer/cli.py:167-178`

- [ ] **Step 1: Add the `_run_post_processing` helper function**

Add this function before the `run()` function in `cli.py`:

```python
def _run_post_processing(action: FileAction, config) -> None:
    """Run NFO generation and art extraction for a completed or skipped action.

    For 'done' actions the file is at action.target.
    For 'skipped' actions the file is at action.source (it never moved).
    """
    if action.status not in ("done", "skipped"):
        return

    file_path = action.target if action.status == "done" else action.source

    if action.generate_nfo:
        generate_nfo(action.media_file, file_path, config)

    if action.extract_art and action.media_file.has_cover:
        extract_cover(file_path, file_path.parent)
```

- [ ] **Step 2: Update the execute loop to use the helper**

Replace the post-move block in `run()` (lines ~173-178):

```python
        # Execute
        execute_actions(actions)
        for a in actions:
            logger.log_action(a)
            _run_post_processing(a, config)
```

This replaces the old inline `if a.status == "done":` block.

- [ ] **Step 3: Run the new tests to verify they pass**

Run: `pytest tests/test_cli_postprocess.py -v`
Expected: All 3 tests PASS

- [ ] **Step 4: Run the full test suite**

Run: `pytest tests/ -v --ignore=tests/test_integration.py`
Expected: All tests PASS, no regressions

- [ ] **Step 5: Commit**

```bash
git add festival_organizer/cli.py
git commit -m "fix: run NFO/art generation for files already at target location"
```

---

### Task 3: Update logger output to show NFO/art activity for skipped files

**Files:**
- Modify: `festival_organizer/logging_util.py:63-76`

Currently, skipped files show `[SKIP]` with only the error message. After the fix, skipped files may still get NFO/art generated. The log output should reflect this so the user sees what happened.

- [ ] **Step 1: Write a test for the updated log output**

Add to `tests/test_logging_util.py`:

```python
def test_log_skipped_with_nfo(capsys):
    """Skipped files with generate_nfo should show the NFO note."""
    mf = MediaFile(source_path=Path("E:/Concerts/test.mkv"), content_type="festival_set")
    action = FileAction(
        source=Path("E:/Concerts/test.mkv"),
        target=Path("E:/Concerts/test.mkv"),
        media_file=mf,
        status="skipped",
        error="Already at target location",
        generate_nfo=True,
        extract_art=True,
    )
    logger = ActionLogger(verbose=True)
    logger.log_action(action)
    output = capsys.readouterr().out
    assert "SKIP" in output
    assert "Already at target location" in output
```

- [ ] **Step 2: Run test to verify it passes (existing behavior is fine)**

Run: `pytest tests/test_logging_util.py -v`
Expected: PASS — the logger already shows the error message for skipped files. No code change needed if the output is acceptable as-is.

- [ ] **Step 3: Commit (only if changes were made)**

```bash
git commit -m "style: update log output for skipped files with post-processing"
```

---

### Task 4: Manual verification

- [ ] **Step 1: Run against real collection in dry-run to sanity check**

```bash
python organize.py scan "E:\Data\Concerts"
```

Expected: Same output as before, no regressions.

- [ ] **Step 2: Run execute with flags on a small subset**

Test on a single artist folder:

```bash
python organize.py execute "E:\Data\Concerts\Martin Garrix" --generate-nfo --extract-art
```

Expected: Files show `[SKIP]` but `.nfo` files and `poster.png` appear in the artist subfolders.

- [ ] **Step 3: Verify generated files**

Check that `.nfo` files contain valid XML and `poster.png` files exist where covers were embedded.

- [ ] **Step 4: Final commit if any adjustments needed**
