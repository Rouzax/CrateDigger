# Error Handling Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden CrateDigger against non-happy-path scenarios: malformed config, permission errors, broken symlinks, corrupt files, user interrupts, and silent failures — while adding structured logging so failures are diagnosable.

**Architecture:** Add a thin `logging` layer that all modules use instead of silent swallowing. Narrow broad `except Exception` catches to specific types. Add a top-level safety net in the CLI. Protect config loading and scanning at system boundaries. Keep the existing soft-fail pattern for enrichment operations (they're optional) but make failures visible via logging.

**Tech Stack:** Python stdlib `logging`, existing `pytest` test suite

---

## Conventions

- **Test file naming:** `tests/test_<module>.py` — extend existing files where they exist
- **Run tests:** `pytest tests/ -v` from repo root
- **Commit prefix:** `fix:` for error handling improvements
- **Logger per module:** `logger = logging.getLogger(__name__)`
- **Never catch `KeyboardInterrupt` or `SystemExit`** — let them propagate
- **Narrow exceptions:** `OSError` for filesystem, `subprocess.SubprocessError` for subprocesses, `json.JSONDecodeError` for JSON parsing, `(ValueError, ET.ParseError)` for XML/parsing

---

### Task 1: Add structured logging setup

**Files:**
- Create: `festival_organizer/log.py`
- Test: `tests/test_log.py`

This module provides the logging configuration. All other modules will import their logger as `logger = logging.getLogger(__name__)`. The CLI calls `setup_logging()` once at startup.

**Step 1: Write the failing test**

```python
# tests/test_log.py
import logging
from festival_organizer.log import setup_logging


def test_setup_logging_default():
    """Default setup configures WARNING level."""
    setup_logging()
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.WARNING


def test_setup_logging_verbose():
    """Verbose setup configures DEBUG level."""
    setup_logging(verbose=True)
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.DEBUG


def test_setup_logging_has_handler():
    """Setup adds a stderr handler."""
    setup_logging()
    logger = logging.getLogger("festival_organizer")
    assert len(logger.handlers) >= 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'festival_organizer.log'`

**Step 3: Write minimal implementation**

```python
# festival_organizer/log.py
"""Logging configuration for CrateDigger."""
import logging
import sys


def setup_logging(verbose: bool = False) -> None:
    """Configure the festival_organizer logger.

    Call once at CLI startup. All modules use logging.getLogger(__name__).
    """
    logger = logging.getLogger("festival_organizer")
    # Remove existing handlers to avoid duplicates on repeated calls
    logger.handlers.clear()

    level = logging.DEBUG if verbose else logging.WARNING
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    fmt = logging.Formatter("%(levelname)s: %(name)s: %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_log.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add festival_organizer/log.py tests/test_log.py
git commit -m "feat: add structured logging setup module"
```

---

### Task 2: Harden config loading against malformed JSON and permission errors

**Files:**
- Modify: `festival_organizer/config.py:280-305` (the `load_config` function)
- Test: `tests/test_config.py` (add new tests)

**Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_load_config_malformed_json(tmp_path, capsys):
    """Malformed user config prints warning and falls back to defaults."""
    user_dir = tmp_path / ".cratedigger"
    user_dir.mkdir()
    (user_dir / "config.json").write_text("{bad json!!!")
    config = load_config(user_config_dir=user_dir)
    assert config.default_layout == "artist_flat"  # fell back to default
    captured = capsys.readouterr()
    assert "config.json" in captured.err


def test_load_config_malformed_library_json(tmp_path, capsys):
    """Malformed library config prints warning, user config still applies."""
    user_dir = tmp_path / "user" / ".cratedigger"
    user_dir.mkdir(parents=True)
    (user_dir / "config.json").write_text('{"default_layout": "festival_flat"}')
    lib_dir = tmp_path / "lib" / ".cratedigger"
    lib_dir.mkdir(parents=True)
    (lib_dir / "config.json").write_text("not json")
    config = load_config(user_config_dir=user_dir, library_config_dir=lib_dir)
    assert config.default_layout == "festival_flat"  # user layer applied
    captured = capsys.readouterr()
    assert "config.json" in captured.err


def test_load_config_unreadable_file(tmp_path, capsys):
    """Unreadable config prints warning and falls back to defaults."""
    import os
    user_dir = tmp_path / ".cratedigger"
    user_dir.mkdir()
    cfg_file = user_dir / "config.json"
    cfg_file.write_text('{"default_layout": "festival_flat"}')
    os.chmod(cfg_file, 0o000)
    try:
        config = load_config(user_config_dir=user_dir)
        assert config.default_layout == "artist_flat"  # fell back to default
        captured = capsys.readouterr()
        assert "config.json" in captured.err
    finally:
        os.chmod(cfg_file, 0o644)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_load_config_malformed_json tests/test_config.py::test_load_config_malformed_library_json tests/test_config.py::test_load_config_unreadable_file -v`
Expected: FAIL — `json.JSONDecodeError` not caught

**Step 3: Modify `load_config` in `config.py`**

Replace the `load_config` function body (lines 280-305) with error-handling wrappers around each config file load. The pattern: try to open and parse, catch `(json.JSONDecodeError, OSError)`, print a warning to stderr, and continue with whatever was loaded so far.

In `festival_organizer/config.py`, add at the top:

```python
import logging
import sys
```

Then replace the config file loading sections. Wrap each `with open(...) json.load()` in a try/except:

```python
def load_config(
    config_path: Path | None = None,
    user_config_dir: Path | None = None,
    library_config_dir: Path | None = None,
) -> Config:
    data = deepcopy(DEFAULT_CONFIG)

    # Legacy path support
    if config_path and config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                _deep_merge(data, json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not read {config_path}: {e}", file=sys.stderr)
        _migrate_layout_names(data)
        return Config(data)

    # Layer 2: User config
    if user_config_dir is None:
        user_config_dir = Path.home() / ".cratedigger"
    user_file = user_config_dir / "config.json"
    if user_file.exists():
        try:
            with open(user_file, "r", encoding="utf-8") as f:
                _deep_merge(data, json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not read {user_file}: {e}", file=sys.stderr)

    # Layer 3: Library config
    if library_config_dir is not None:
        lib_file = library_config_dir / "config.json"
        if lib_file.exists():
            try:
                with open(lib_file, "r", encoding="utf-8") as f:
                    _deep_merge(data, json.load(f))
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: could not read {lib_file}: {e}", file=sys.stderr)

    _migrate_layout_names(data)
    return Config(data)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: ALL PASS (new and existing)

**Step 5: Commit**

```bash
git add festival_organizer/config.py tests/test_config.py
git commit -m "fix: handle malformed and unreadable config files gracefully"
```

---

### Task 3: Add top-level exception handler in CLI

**Files:**
- Modify: `festival_organizer/cli.py:88-243` (wrap `run()` body)
- Modify: `organize.py` (add safety net)
- Test: `tests/test_cli.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_cli.py
from unittest.mock import patch
from festival_organizer.cli import run


def test_run_no_command():
    """No command prints help and returns 1."""
    assert run([]) == 1


def test_run_nonexistent_path():
    """Nonexistent path returns 1 with error message."""
    assert run(["scan", "/nonexistent/path/abc123"]) == 1


def test_run_unexpected_error_returns_1(capsys):
    """Unexpected exception is caught, printed to stderr, returns 1."""
    with patch("festival_organizer.cli.load_config", side_effect=RuntimeError("boom")):
        result = run(["scan", "/tmp"])
    assert result == 1
    captured = capsys.readouterr()
    assert "boom" in captured.err
```

**Step 2: Run test to verify the third test fails**

Run: `pytest tests/test_cli.py -v`
Expected: `test_run_unexpected_error_returns_1` FAILS — unhandled `RuntimeError`

**Step 3: Wrap `run()` body in try/except**

In `festival_organizer/cli.py`, modify `run()`:

```python
def run(argv: list[str] | None = None) -> int:
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        return _run_command(args)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
```

Extract the rest of the current `run()` body (from "Resolve config layers" onwards) into `_run_command(args) -> int`. This keeps the safety net thin and the logic unchanged.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: ALL PASS

Run: `pytest tests/ -v`
Expected: ALL PASS (no regressions)

**Step 5: Commit**

```bash
git add festival_organizer/cli.py tests/test_cli.py
git commit -m "fix: add top-level exception handler in CLI entry point"
```

---

### Task 4: Protect `scan_folder` against permission errors

**Files:**
- Modify: `festival_organizer/scanner.py:7-32`
- Test: `tests/test_scanner.py` (add new tests)

**Step 1: Write the failing test**

Add to `tests/test_scanner.py`:

```python
import os


def test_scan_folder_permission_denied(tmp_path):
    """Scanner skips unreadable directories instead of crashing."""
    from festival_organizer.config import load_config
    from festival_organizer.scanner import scan_folder
    config = load_config()

    # Create a readable file and an unreadable subdirectory
    (tmp_path / "good.mkv").write_bytes(b"")
    bad_dir = tmp_path / "noaccess"
    bad_dir.mkdir()
    (bad_dir / "hidden.mkv").write_bytes(b"")
    os.chmod(bad_dir, 0o000)

    try:
        files = scan_folder(tmp_path, config)
        # Should find the good file without crashing
        assert any("good.mkv" in str(f) for f in files)
    finally:
        os.chmod(bad_dir, 0o755)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scanner.py::test_scan_folder_permission_denied -v`
Expected: FAIL — `PermissionError` from `rglob`

**Step 3: Modify `scan_folder` to catch PermissionError**

Replace `scan_folder` in `festival_organizer/scanner.py`:

```python
import logging
from pathlib import Path

from festival_organizer.config import Config

logger = logging.getLogger(__name__)


def scan_folder(root: Path, config: Config) -> list[Path]:
    """Recursively find all media files under root, respecting skip patterns."""
    media_exts = config.media_extensions
    files = []

    try:
        entries = sorted(root.rglob("*"))
    except OSError as e:
        logger.warning("Could not scan %s: %s", root, e)
        return files

    for item in entries:
        try:
            if not item.is_file():
                continue
        except OSError:
            continue

        if item.suffix.lower() not in media_exts:
            continue

        try:
            rel = str(item.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = item.name

        if config.should_skip(rel):
            continue

        files.append(item)

    return files
```

Note: `rglob("*")` on Python 3.12+ handles `PermissionError` internally by skipping. On older versions it raises. The `try/except OSError` around `rglob` handles both cases. The inner `try/except OSError` around `is_file()` handles broken symlinks.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scanner.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/scanner.py tests/test_scanner.py
git commit -m "fix: scanner handles permission errors and broken symlinks gracefully"
```

---

### Task 5: Protect `run_pipeline` against `is_needed()` failures

**Files:**
- Modify: `festival_organizer/runner.py:41-48`
- Test: `tests/test_runner.py` (add new test)

**Step 1: Write the failing test**

Add to `tests/test_runner.py`:

```python
from pathlib import Path
from festival_organizer.operations import Operation, OperationResult
from festival_organizer.models import MediaFile
from festival_organizer.runner import run_pipeline
from festival_organizer.progress import ProgressPrinter
from io import StringIO


def _make_mf(**kwargs):
    defaults = dict(source_path=Path("test.mkv"), artist="Test",
                    festival="TML", year="2024", content_type="festival_set")
    defaults.update(kwargs)
    return MediaFile(**defaults)


class BrokenIsNeededOp(Operation):
    name = "broken"

    def is_needed(self, file_path, media_file):
        raise OSError("broken symlink")

    def execute(self, file_path, media_file):
        return OperationResult(self.name, "done")


def test_pipeline_is_needed_failure_does_not_crash(tmp_path):
    """If is_needed() raises, the operation is marked as error, pipeline continues."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()
    ops = [BrokenIsNeededOp()]
    progress = ProgressPrinter(total=1, stream=StringIO())
    results = run_pipeline([(video, mf, ops)], progress)
    assert len(results) == 1
    assert results[0][0].status == "error"
    assert "broken symlink" in results[0][0].detail
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_runner.py::test_pipeline_is_needed_failure_does_not_crash -v`
Expected: FAIL — unhandled `OSError`

**Step 3: Wrap the `is_needed` + `execute` block in runner.py**

In `festival_organizer/runner.py`, modify the inner loop (lines 41-48):

```python
        for op in operations:
            try:
                needed = op.is_needed(current_path, media_file)
            except Exception as e:
                file_results.append(OperationResult(op.name, "error", str(e)))
                continue

            if needed:
                result = op.execute(current_path, media_file)
                # If organize succeeded, update path for downstream ops
                if op.name == "organize" and result.status == "done":
                    current_path = op.target
            else:
                result = OperationResult(op.name, "skipped", "exists")
            file_results.append(result)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/runner.py tests/test_runner.py
git commit -m "fix: pipeline catches is_needed() failures instead of crashing"
```

---

### Task 6: Narrow `except Exception` to specific types in operations.py

**Files:**
- Modify: `festival_organizer/operations.py:82,105,146,186,213`
- Test: `tests/test_operations.py` (add new tests)

The goal: change `except Exception` to `except (OSError, ValueError)` in each operation's `execute()` method. This lets `KeyboardInterrupt` and `SystemExit` propagate normally.

**Step 1: Write the failing test**

Add to `tests/test_operations.py`:

```python
def test_keyboard_interrupt_propagates_from_nfo(tmp_path):
    """KeyboardInterrupt during NFO generation propagates, not swallowed."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()
    op = NfoOperation(load_config())

    with patch("festival_organizer.operations.generate_nfo", side_effect=KeyboardInterrupt):
        import pytest
        with pytest.raises(KeyboardInterrupt):
            op.execute(video, mf)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_operations.py::test_keyboard_interrupt_propagates_from_nfo -v`
Expected: FAIL — `KeyboardInterrupt` is caught by `except Exception`, test doesn't see the raise

**Step 3: Narrow exception types**

In `festival_organizer/operations.py`, change each `except Exception as e:` to specific types:

- `OrganizeOperation.execute` (line 61): keep `except OSError as e:` (already correct)
- `NfoOperation.execute` (line 82): change to `except (OSError, ValueError) as e:`
- `ArtOperation.execute` (line 105): change to `except (OSError, subprocess.SubprocessError) as e:`
- `PosterOperation.execute` (line 146): change to `except (OSError, ValueError) as e:`
- `AlbumPosterOperation.execute` (line 186): change to `except (OSError, ValueError) as e:`
- `TagsOperation.execute` (line 213): change to `except (OSError, subprocess.SubprocessError) as e:`

Add `import subprocess` at the top of the file.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_operations.py -v`
Expected: ALL PASS

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/operations.py tests/test_operations.py
git commit -m "fix: narrow except Exception to specific types in operations"
```

---

### Task 7: Narrow `except Exception` and add logging in metadata.py

**Files:**
- Modify: `festival_organizer/metadata.py:126-187`
- Test: `tests/test_metadata.py` (add new test)

**Step 1: Write the failing test**

Add to `tests/test_metadata.py`:

```python
import logging


def test_mediainfo_failure_is_logged(tmp_path, caplog):
    """When mediainfo subprocess fails, a debug message is logged."""
    from unittest.mock import patch
    from festival_organizer.metadata import _extract_mediainfo

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")

    with patch("festival_organizer.metadata.MEDIAINFO_PATH", "/usr/bin/mediainfo"):
        with patch("festival_organizer.metadata.subprocess.run",
                   side_effect=subprocess.SubprocessError("oops")):
            with caplog.at_level(logging.DEBUG, logger="festival_organizer.metadata"):
                result = _extract_mediainfo(video)
    assert result == {}
    assert "oops" in caplog.text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_metadata.py::test_mediainfo_failure_is_logged -v`
Expected: FAIL — no logging in the except block

**Step 3: Modify metadata.py**

Add at the top of `festival_organizer/metadata.py`:

```python
import logging
logger = logging.getLogger(__name__)
```

Change `_extract_mediainfo` (line 140):
```python
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.debug("mediainfo failed for %s: %s", filepath, e)
        return {}
```

Change `_extract_ffprobe` (line 186):
```python
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.debug("ffprobe failed for %s: %s", filepath, e)
        return {}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_metadata.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/metadata.py tests/test_metadata.py
git commit -m "fix: narrow exceptions and add debug logging in metadata extraction"
```

---

### Task 8: Narrow `except Exception` and add logging in artwork.py

**Files:**
- Modify: `festival_organizer/artwork.py:60,86`
- Test: `tests/test_artwork.py` (add new test)

**Step 1: Write the failing test**

Add to `tests/test_artwork.py`:

```python
import logging


def test_keyboard_interrupt_propagates_from_extract_cover(tmp_path):
    """KeyboardInterrupt is not swallowed by artwork extraction."""
    import pytest
    from unittest.mock import patch
    from festival_organizer.artwork import extract_cover

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")

    with patch("festival_organizer.artwork._extract_mkvattachment", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            extract_cover(video, tmp_path)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_artwork.py::test_keyboard_interrupt_propagates_from_extract_cover -v`
Expected: FAIL — `KeyboardInterrupt` is caught in `_extract_mkvattachment`

Wait — `extract_cover` itself doesn't have a try/except. It calls `_extract_mkvattachment` which does. The `KeyboardInterrupt` from the mock would be raised before entering `_extract_mkvattachment`'s try block... Actually the mock replaces the function entirely, so the `KeyboardInterrupt` would propagate from `extract_cover` line 27.

Let me revise. The test should target the internal methods:

```python
def test_mkvextract_failure_logged(tmp_path, caplog):
    """MKV extraction failure is logged at debug level."""
    from unittest.mock import patch
    from festival_organizer.artwork import _extract_mkvattachment

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    thumb = tmp_path / "test-thumb.jpg"

    with patch("festival_organizer.artwork.metadata.MKVEXTRACT_PATH", "/usr/bin/mkvextract"):
        with patch("festival_organizer.artwork.subprocess.run",
                   side_effect=subprocess.SubprocessError("fail")):
            with caplog.at_level(logging.DEBUG, logger="festival_organizer.artwork"):
                result = _extract_mkvattachment(video, thumb)
    assert result is False
    assert "fail" in caplog.text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_artwork.py::test_mkvextract_failure_logged -v`
Expected: FAIL — no logging

**Step 3: Modify artwork.py**

Add at top:

```python
import logging
logger = logging.getLogger(__name__)
```

Change `_extract_mkvattachment` (line 60):
```python
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("MKV attachment extraction failed for %s: %s", source, e)
        return False
```

Change `_sample_frame_fallback` (lines 83-87):
```python
    except ImportError:
        return False
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Frame sampling failed for %s: %s", source, e)
        return False
```

**Step 4: Run tests**

Run: `pytest tests/test_artwork.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/artwork.py tests/test_artwork.py
git commit -m "fix: narrow exceptions and add debug logging in artwork extraction"
```

---

### Task 9: Narrow `except Exception` and add logging in embed_tags.py

**Files:**
- Modify: `festival_organizer/embed_tags.py:49,54`

**Step 1: Write the failing test**

Add to `tests/test_operations.py` (or create `tests/test_embed_tags.py`):

```python
# tests/test_embed_tags.py
import logging
import subprocess
from pathlib import Path
from unittest.mock import patch
from festival_organizer.embed_tags import embed_tags
from festival_organizer.models import MediaFile


def _make_mf(**kwargs):
    defaults = dict(source_path=Path("test.mkv"), artist="Test",
                    festival="TML", year="2024", content_type="festival_set")
    defaults.update(kwargs)
    return MediaFile(**defaults)


def test_embed_tags_failure_logged(tmp_path, caplog):
    """Tag embedding failure is logged."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()

    with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with patch("festival_organizer.embed_tags.subprocess.run",
                   side_effect=subprocess.SubprocessError("nope")):
            with caplog.at_level(logging.DEBUG, logger="festival_organizer.embed_tags"):
                result = embed_tags(mf, video)
    assert result is False
    assert "nope" in caplog.text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_embed_tags.py -v`
Expected: FAIL — no logging

**Step 3: Modify embed_tags.py**

Add at top:

```python
import logging
logger = logging.getLogger(__name__)
```

Change line 49:
```python
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Tag embedding failed for %s: %s", target_path, e)
        return False
```

Keep the cleanup `except Exception: pass` in `finally` — temp file cleanup should still be best-effort.

**Step 4: Run tests**

Run: `pytest tests/test_embed_tags.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/embed_tags.py tests/test_embed_tags.py
git commit -m "fix: narrow exceptions and add debug logging in tag embedding"
```

---

### Task 10: Narrow `except Exception` and add logging in chapters.py

**Files:**
- Modify: `festival_organizer/tracklists/chapters.py:172,233,308`

**Step 1: Write the failing test**

Add to `tests/test_tracklists_chapters.py`:

```python
import logging
import subprocess
from pathlib import Path
from unittest.mock import patch
from festival_organizer.tracklists.chapters import extract_existing_chapters


def test_extract_chapters_failure_logged(tmp_path, caplog):
    """Chapter extraction failure is logged at debug level."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")

    with patch("festival_organizer.tracklists.chapters.metadata.MKVEXTRACT_PATH", "/usr/bin/mkvextract"):
        with patch("festival_organizer.tracklists.chapters.subprocess.run",
                   side_effect=subprocess.SubprocessError("timeout")):
            with caplog.at_level(logging.DEBUG, logger="festival_organizer.tracklists.chapters"):
                result = extract_existing_chapters(video)
    assert result is None
    assert "timeout" in caplog.text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tracklists_chapters.py::test_extract_chapters_failure_logged -v`
Expected: FAIL — no logging

**Step 3: Modify chapters.py**

Add at top:

```python
import logging
logger = logging.getLogger(__name__)
```

Change `extract_existing_chapters` except block (line 172):
```python
    except (OSError, subprocess.SubprocessError, ET.ParseError) as e:
        logger.debug("Chapter extraction failed for %s: %s", filepath, e)
        return None
```

Change `extract_stored_tracklist_info` except block (line 233):
```python
    except (OSError, subprocess.SubprocessError, ET.ParseError, ValueError) as e:
        logger.debug("Stored tracklist extraction failed for %s: %s", filepath, e)
        return None
```

Change `embed_chapters` except block (line 308):
```python
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Chapter embedding failed for %s: %s", filepath, e)
        return False
```

Keep all `finally` cleanup blocks unchanged (best-effort temp file deletion).

**Step 4: Run tests**

Run: `pytest tests/test_tracklists_chapters.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/chapters.py tests/test_tracklists_chapters.py
git commit -m "fix: narrow exceptions and add debug logging in chapter operations"
```

---

### Task 11: Narrow `except Exception` and add logging in tracklists/api.py

**Files:**
- Modify: `festival_organizer/tracklists/api.py:257,280,314`

The cookie save/restore and session validation methods catch `Exception` broadly. Narrow to specific types and add debug logging.

**Step 1: Write the failing test**

Add to `tests/test_tracklists_api.py`:

```python
import logging


def test_cookie_save_failure_logged(tmp_path, caplog):
    """Cookie save failure is logged at debug level."""
    from festival_organizer.tracklists.api import TracklistSession

    session = TracklistSession(cookie_cache_path=tmp_path / "subdir" / "cookies.json")
    # subdir doesn't exist, so write will fail with OSError

    with caplog.at_level(logging.DEBUG, logger="festival_organizer.tracklists.api"):
        session._save_cookies("test@example.com")
    # Should not crash, should log
    assert "cookie" in caplog.text.lower() or "save" in caplog.text.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tracklists_api.py::test_cookie_save_failure_logged -v`
Expected: FAIL — no logging (currently `pass` in except block)

**Step 3: Modify api.py**

Add at top:

```python
import logging
logger = logging.getLogger(__name__)
```

Change `_validate_session` (line 257):
```python
        except (requests.RequestException, OSError) as e:
            logger.debug("Session validation failed: %s", e)
            return False
```

Change `_save_cookies` (line 280):
```python
        except (OSError, TypeError) as e:
            logger.debug("Cookie save failed: %s", e)
```

Change `_restore_cookies` (line 314):
```python
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug("Cookie restore failed: %s", e)
            return False
```

**Step 4: Run tests**

Run: `pytest tests/test_tracklists_api.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/api.py tests/test_tracklists_api.py
git commit -m "fix: narrow exceptions and add debug logging in tracklists API"
```

---

### Task 12: Fix `_request` retry loop falling through on 5xx errors

**Files:**
- Modify: `festival_organizer/tracklists/api.py:152-186`
- Test: `tests/test_tracklists_api.py` (add new test)

**Step 1: Write the failing test**

Add to `tests/test_tracklists_api.py`:

```python
from unittest.mock import patch, MagicMock
from festival_organizer.tracklists.api import TracklistSession, TracklistError


def test_request_raises_on_persistent_5xx():
    """After all retries on 502/503/504, raise TracklistError instead of returning bad response."""
    session = TracklistSession()

    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.text = "Bad Gateway"

    with patch.object(session._session, "get", return_value=mock_resp):
        import pytest
        with pytest.raises(TracklistError, match="502"):
            session._request("GET", "http://example.com", max_retries=2)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tracklists_api.py::test_request_raises_on_persistent_5xx -v`
Expected: FAIL — function returns the 502 response instead of raising

**Step 3: Fix the retry loop**

In `festival_organizer/tracklists/api.py`, modify `_request` (around line 171-177):

```python
                # Transient errors
                if resp.status_code in (502, 503, 504):
                    if attempt < max_retries - 1:
                        wait = min(2 ** attempt + random.uniform(0, 3), 30)
                        time.sleep(wait)
                        continue
                    raise TracklistError(
                        f"Server error {resp.status_code} after {max_retries} attempts"
                    )

                return resp
```

**Step 4: Run tests**

Run: `pytest tests/test_tracklists_api.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/api.py tests/test_tracklists_api.py
git commit -m "fix: raise TracklistError on persistent 5xx instead of returning bad response"
```

---

### Task 13: Narrow `except Exception` in executor.py

**Files:**
- Modify: `festival_organizer/executor.py:53`
- Test: `tests/test_executor.py` (add new test)

**Step 1: Write the failing test**

Add to `tests/test_executor.py`:

```python
from unittest.mock import patch
from festival_organizer.executor import execute_actions
from festival_organizer.models import FileAction, MediaFile
from pathlib import Path


def _make_mf():
    return MediaFile(source_path=Path("test.mkv"), artist="Test",
                     festival="TML", year="2024", content_type="festival_set")


def test_keyboard_interrupt_propagates(tmp_path):
    """KeyboardInterrupt during file move propagates, not swallowed."""
    import pytest
    source = tmp_path / "test.mkv"
    source.write_bytes(b"data")
    target = tmp_path / "dest" / "test.mkv"

    action = FileAction(source=source, target=target, action="move", media_file=_make_mf())

    with patch("festival_organizer.executor.shutil.move", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            execute_actions([action])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_executor.py::test_keyboard_interrupt_propagates -v`
Expected: FAIL — `KeyboardInterrupt` is caught by `except Exception`

**Step 3: Modify executor.py**

Change line 53 from `except Exception as e:` to `except OSError as e:`:

```python
        except OSError as e:
            action.status = "error"
            action.error = str(e)
```

**Step 4: Run tests**

Run: `pytest tests/test_executor.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/executor.py tests/test_executor.py
git commit -m "fix: narrow except Exception to OSError in executor"
```

---

### Task 14: Add logging in poster.py for image loading failures

**Files:**
- Modify: `festival_organizer/poster.py:210,320-328`

**Step 1: Write the failing test**

```python
# tests/test_poster_errors.py
import logging
from pathlib import Path
from festival_organizer.poster import get_dominant_color_from_thumbs


def test_corrupt_thumb_logged_and_skipped(tmp_path, caplog):
    """Corrupt thumbnail is logged and skipped, returns default color."""
    bad_thumb = tmp_path / "bad-thumb.jpg"
    bad_thumb.write_bytes(b"not an image")

    with caplog.at_level(logging.DEBUG, logger="festival_organizer.poster"):
        color = get_dominant_color_from_thumbs([bad_thumb])
    assert color == (40, 80, 180)  # default blue fallback
    assert "bad-thumb.jpg" in caplog.text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_poster_errors.py -v`
Expected: FAIL — no logging in the except block

**Step 3: Modify poster.py**

Add at top:

```python
import logging
logger = logging.getLogger(__name__)
```

Change `get_dominant_color_from_thumbs` except block (line 327):
```python
        except (OSError, ValueError) as e:
            logger.debug("Could not read thumbnail %s: %s", path, e)
            continue
```

Add a try/except around `Image.open` in `generate_set_poster` (line 210):
```python
    try:
        frame = Image.open(source_image_path).convert("RGB")
    except (OSError, ValueError) as e:
        raise OSError(f"Cannot open source image {source_image_path}: {e}") from e
```

This re-raises as `OSError` so the caller (`PosterOperation.execute`) catches it properly with the narrowed exception types from Task 6.

**Step 4: Run tests**

Run: `pytest tests/test_poster_errors.py -v && pytest tests/test_poster.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add festival_organizer/poster.py tests/test_poster_errors.py
git commit -m "fix: add logging for image failures in poster generation"
```

---

### Task 15: Wire up logging in CLI and add --verbose/-v debug output

**Files:**
- Modify: `festival_organizer/cli.py` (import and call `setup_logging`)

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
import logging


def test_verbose_flag_enables_debug_logging():
    """The --verbose flag enables DEBUG logging for the package."""
    from unittest.mock import patch, MagicMock
    with patch("festival_organizer.cli.scan_folder", return_value=[]):
        with patch("festival_organizer.cli.find_library_root", return_value=None):
            run(["scan", "/tmp", "--verbose"])
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.DEBUG
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_verbose_flag_enables_debug_logging -v`
Expected: FAIL — `setup_logging` not called, logger level not set

**Step 3: Modify cli.py**

Add import:
```python
from festival_organizer.log import setup_logging
```

In `_run_command` (the extracted function from Task 3), after parsing `verbose`, add:
```python
    setup_logging(verbose=verbose)
```

This must happen before `scan_folder` and any operations that now use `logger.debug(...)`.

**Step 4: Run tests**

Run: `pytest tests/test_cli.py -v`
Expected: ALL PASS

Run: `pytest tests/ -v`
Expected: ALL PASS — full regression check

**Step 5: Commit**

```bash
git add festival_organizer/cli.py tests/test_cli.py
git commit -m "feat: wire up structured logging, --verbose enables debug output"
```

---

### Task 16: Final regression check

**Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 2: Smoke test the CLI**

Run: `python -m festival_organizer.cli scan /tmp/cratedigger_test --verbose 2>&1 | head -20`
Expected: No crash. If `/tmp/cratedigger_test` has files, they're scanned. Debug output visible on stderr.

Run: `python -m festival_organizer.cli scan /nonexistent`
Expected: `Error: path does not exist: /nonexistent` on stderr, exit code 1.

**Step 3: Commit any final adjustments**

If smoke tests reveal issues, fix and commit.

---

## Summary of Changes

| # | What | Why |
|---|------|-----|
| 1 | `log.py` — logging setup | All modules need a logger |
| 2 | `config.py` — catch JSON/OS errors | Malformed config shouldn't crash |
| 3 | `cli.py` — top-level try/except | Unhandled errors shouldn't dump tracebacks |
| 4 | `scanner.py` — catch PermissionError | Unreadable dirs shouldn't crash scan |
| 5 | `runner.py` — protect `is_needed()` | Broken symlinks shouldn't crash pipeline |
| 6 | `operations.py` — narrow exceptions | Let KeyboardInterrupt propagate |
| 7 | `metadata.py` — narrow + log | Diagnosable failures |
| 8 | `artwork.py` — narrow + log | Diagnosable failures |
| 9 | `embed_tags.py` — narrow + log | Diagnosable failures |
| 10 | `chapters.py` — narrow + log | Diagnosable failures |
| 11 | `api.py` — narrow + log | Diagnosable failures |
| 12 | `api.py` — fix 5xx fallthrough | Bug: bad response treated as success |
| 13 | `executor.py` — narrow exceptions | Let KeyboardInterrupt propagate |
| 14 | `poster.py` — log + protect Image.open | Corrupt images shouldn't crash |
| 15 | `cli.py` — wire up logging | `--verbose` shows debug output |
| 16 | Full regression | Verify nothing broke |
