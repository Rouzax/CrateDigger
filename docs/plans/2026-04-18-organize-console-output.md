# Organize Console Output Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Apply the console output contract to the `organize` command so users see clear per-file verdict lines showing exactly what happened (or would happen in dry-run), replacing today's opaque two-line output and classification-only dry-run summary.

**Architecture:** New `OrganizeContractProgress` class in `progress.py` replaces `ProgressPrinter` for pure-organize runs (no `--enrich`). Three new primitives in `console.py`: `preview` badge, `organize_summary_panel`, `library_sync_summary_line`. Identify is retrofitted to use the `preview` badge in the same change. Kodi sync phases wrap in `StepProgress` and emit a `library_sync_summary_line` at the end. The `--enrich` path is untouched.

**Tech Stack:** Python 3.11+, Rich (console, panels, text), pytest

**Design doc:** `docs/plans/2026-04-16-organize-console-output-design.md`

---

## Phase 1: Primitives

### Task 1: Add `preview` badge to `verdict()`

**Files:**
- Modify: `festival_organizer/console.py:316-322`
- Test: `tests/test_console_verdict.py`

**Step 1: Write the failing tests**

Add to `tests/test_console_verdict.py`:

```python
# In the parametrized test_verdict_badge_colours, add a new tuple:
#   ("preview", "cyan"),

# In the parametrized test_verdict_has_gap_between_badge_and_counter, add:
#   "preview" to the list

def test_verdict_preview_shape():
    row = verdict(
        status="preview",
        index=1,
        total=5,
        filename="my_set.mkv",
        detail="would copy to Festivals/Ultra Miami 2026/",
        elapsed_s=0.0,
    )
    plain = row.plain
    assert plain.startswith("  preview")
    assert "[1/5]" in plain
    assert "would copy to" in plain
    assert "s" not in plain.split("->")[-1]  # no elapsed for 0.0s
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_console_verdict.py -v`
Expected: FAIL with "Unknown verdict status: preview"

**Step 3: Write minimal implementation**

In `festival_organizer/console.py`, add to `_VERDICT_STYLES` dict (after line 318):

```python
_VERDICT_STYLES = {
    "done":       ("done",        "green"),
    "updated":    ("updated",     "cyan"),
    "up-to-date": ("up-to-date",  "dim green"),
    "preview":    ("preview",     "cyan"),
    "skipped":    ("skipped",     "yellow"),
    "error":      ("error",       "red"),
}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_console_verdict.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add festival_organizer/console.py tests/test_console_verdict.py
git commit -m "feat(console): add preview badge to verdict primitive"
```

---

### Task 2: Implement `organize_summary_panel`

**Files:**
- Modify: `festival_organizer/console.py` (add after `identify_summary_panel`)
- Create: `tests/test_console_organize_summary.py`

**Step 1: Write the failing tests**

Create `tests/test_console_organize_summary.py`:

```python
"""Tests for organize_summary_panel."""
import io
from rich.console import Console
from rich.panel import Panel
from festival_organizer.console import organize_summary_panel


def _render(renderable) -> str:
    buf = io.StringIO()
    Console(file=buf, width=120, no_color=True).print(renderable)
    return buf.getvalue()


def test_returns_panel():
    p = organize_summary_panel(
        stats={"done": 3, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
    )
    assert isinstance(p, Panel)


def test_stats_row_shows_all_counts():
    p = organize_summary_panel(
        stats={"done": 3, "up_to_date": 1, "preview": 0, "skipped": 2, "error": 1},
    )
    out = _render(p)
    assert "done" in out and "3" in out
    assert "up_to_date" in out and "1" in out
    assert "skipped" in out and "2" in out
    assert "error" in out and "1" in out


def test_destinations_breakdown():
    p = organize_summary_panel(
        stats={"done": 5, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
        destinations={"Festivals/Ultra Miami 2026": 3, "Artists/Afrojack": 2},
    )
    out = _render(p)
    assert "Festivals/Ultra Miami 2026" in out
    assert "3" in out
    assert "Artists/Afrojack" in out


def test_destinations_truncation_at_10():
    dests = {f"Festival/{i}": i + 1 for i in range(15)}
    p = organize_summary_panel(
        stats={"done": 15, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
        destinations=dests,
    )
    out = _render(p)
    assert "+5 more" in out


def test_skipped_reasons_shown():
    p = organize_summary_panel(
        stats={"done": 0, "up_to_date": 0, "preview": 0, "skipped": 3, "error": 0},
        skipped_reasons={"not a video": 2, "unrecognized": 1},
    )
    out = _render(p)
    assert "not a video" in out
    assert "2" in out


def test_skipped_reasons_omitted_when_empty():
    p = organize_summary_panel(
        stats={"done": 1, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
    )
    out = _render(p)
    assert "not a video" not in out


def test_errors_list_shown():
    p = organize_summary_panel(
        stats={"done": 0, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 2},
        errors=[("file1.mkv", "Permission denied"), ("file2.mkv", "Disk full")],
    )
    out = _render(p)
    assert "file1.mkv" in out
    assert "Permission denied" in out


def test_errors_capped_at_10():
    errors = [(f"file{i}.mkv", "err") for i in range(15)]
    p = organize_summary_panel(
        stats={"done": 0, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 15},
        errors=errors,
    )
    out = _render(p)
    assert "+5 more" in out


def test_elapsed_shown():
    p = organize_summary_panel(
        stats={"done": 1, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
        elapsed_s=83.2,
    )
    out = _render(p)
    assert "Elapsed" in out
    assert "1m 23s" in out


def test_elapsed_omitted_when_none():
    p = organize_summary_panel(
        stats={"done": 1, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
    )
    out = _render(p)
    assert "Elapsed" not in out
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_console_organize_summary.py -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

In `festival_organizer/console.py`, add after `identify_summary_panel` (after line 478):

```python
def organize_summary_panel(
    stats: dict[str, int],
    destinations: dict[str, int] | None = None,
    skipped_reasons: dict[str, int] | None = None,
    errors: list[tuple[str, str]] | None = None,
    elapsed_s: float | None = None,
) -> Panel:
    """Summary panel for the organize command."""
    body = Text()

    # Stats row
    first = True
    _ORG_STAT_STYLES = {
        "done": "green", "up_to_date": "dim green", "preview": "cyan",
        "skipped": "yellow", "error": "red",
    }
    for key, value in stats.items():
        if not first:
            body.append("  ")
        first = False
        style = _ORG_STAT_STYLES.get(key, "dim")
        body.append(f"{key}: ", style="bold")
        body.append(str(value), style=style)

    # Destinations breakdown
    if destinations:
        body.append("\n\n")
        body.append("Destinations: ", style="bold")
        sorted_dests = sorted(destinations.items(), key=lambda x: -x[1])
        for i, (folder, count) in enumerate(sorted_dests[:10]):
            body.append(f"\n  {folder}: ")
            body.append(str(count), style="green")
        remaining = len(sorted_dests) - 10
        if remaining > 0:
            body.append(f"\n  ... +{remaining} more", style="dim")

    # Skipped reasons
    if skipped_reasons:
        body.append("\n\n")
        body.append("Skipped: ", style="bold")
        for reason, count in skipped_reasons.items():
            body.append(f"\n  {reason}: ")
            body.append(str(count), style="yellow")

    # Errors
    if errors:
        body.append("\n\n")
        body.append("Errors: ", style="bold")
        for filename, detail in errors[:10]:
            body.append(f"\n  {filename}", style="red")
            body.append(f" -> {detail}", style="red")
        remaining = len(errors) - 10
        if remaining > 0:
            body.append(f"\n  ... +{remaining} more", style="dim")

    if elapsed_s is not None:
        body.append("\n\n")
        body.append("Elapsed: ", style="bold")
        body.append(_format_elapsed(elapsed_s), style="dim")

    return Panel(body, title="Summary", expand=True)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_console_organize_summary.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add festival_organizer/console.py tests/test_console_organize_summary.py
git commit -m "feat(console): add organize_summary_panel primitive"
```

---

### Task 3: Implement `library_sync_summary_line`

**Files:**
- Modify: `festival_organizer/console.py`
- Create: `tests/test_console_library_sync.py`

**Step 1: Write the failing tests**

Create `tests/test_console_library_sync.py`:

```python
"""Tests for library_sync_summary_line."""
from festival_organizer.console import library_sync_summary_line


def test_shape_includes_name_and_stats():
    line = library_sync_summary_line(
        "Kodi", {"refreshed": 5, "not yet in library": 2}, elapsed_s=3.4,
    )
    plain = line.plain
    assert "done" in plain
    assert "Kodi sync" in plain
    assert "refreshed 5" in plain
    assert "not yet in library 2" in plain
    assert "3.4s" in plain


def test_short_elapsed_omitted():
    line = library_sync_summary_line(
        "Kodi", {"refreshed": 3}, elapsed_s=0.2,
    )
    assert "s" not in line.plain.split("->")[-1] or "0.2s" not in line.plain


def test_generic_name():
    line = library_sync_summary_line(
        "Lyrion", {"refreshed": 1}, elapsed_s=1.0,
    )
    assert "Lyrion sync" in line.plain


def test_zero_stats_omitted():
    line = library_sync_summary_line(
        "Kodi", {"refreshed": 5, "not yet in library": 0}, elapsed_s=1.0,
    )
    assert "not yet in library" not in line.plain
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_console_library_sync.py -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

In `festival_organizer/console.py`, add after `organize_summary_panel`:

```python
def library_sync_summary_line(
    name: str,
    stats: dict[str, int],
    elapsed_s: float,
) -> Text:
    """One-line contract-styled summary for a library sync sub-phase.

    Shape: ``done  <name> sync  ->  refreshed N, M not yet in library  .  Ns``
    """
    label, style = _VERDICT_STYLES["done"]
    text = Text()
    text.append("  ")
    text.append(label, style=style)
    pad = _VERDICT_BADGE_WIDTH - len(label) - 2
    if pad > 0:
        text.append(" " * pad)

    text.append(f"{name} sync")
    parts = [f"{key} {value}" for key, value in stats.items() if value]
    if parts:
        text.append("  ->  ")
        text.append(", ".join(parts))
    if elapsed_s >= _ELAPSED_THRESHOLD_S:
        text.append("  .  ")
        text.append(f"{elapsed_s:.1f}s", style="dim")
    return text
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_console_library_sync.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add festival_organizer/console.py tests/test_console_library_sync.py
git commit -m "feat(console): add library_sync_summary_line primitive"
```

---

## Phase 2: Identify Retrofit

### Task 4: Switch identify preview to `status="preview"`

**Files:**
- Modify: `festival_organizer/tracklists/cli_handler.py:638`
- Modify: `festival_organizer/console.py:439`
- Modify: `tests/test_console.py:319,337`

**Step 1: Update the identify preview return**

In `festival_organizer/tracklists/cli_handler.py`, line 638, change:

```python
return ("previewed", "done", f"{export.title} . {len(chapters)} chapters (preview)")
```

to:

```python
return ("previewed", "preview", f"{export.title} . {len(chapters)} chapters")
```

**Step 2: Update identify_summary_panel colour map**

In `festival_organizer/console.py`, line 439, change:

```python
style = "green" if key in ("added", "done", "up_to_date", "previewed") else (
```

to:

```python
style = "green" if key in ("added", "done", "up_to_date") else (
    "cyan" if key in ("updated", "previewed") else (
        "red" if key == "error" else "dim"
    )
)
```

Note: this replaces the entire nested ternary (lines 439-442). The `"updated"` check was already there at level 2; now `"previewed"` joins it at the cyan level.

**Step 3: Run tests**

Run: `pytest tests/test_console.py tests/test_console_verdict.py -v`
Expected: PASS (the `previewed: 0` in test stats means the new cyan colour path doesn't visually change those tests; the preview badge test from Task 1 covers the status itself)

**Step 4: Commit**

```bash
git add festival_organizer/tracklists/cli_handler.py festival_organizer/console.py
git commit -m "refactor(identify): use preview badge instead of done+suffix for preview mode"
```

---

## Phase 3: Organize Adoption

### Task 5: Implement `_organize_detail` helper

**Files:**
- Modify: `festival_organizer/progress.py`
- Create: `tests/test_organize_detail.py`

**Step 1: Write the failing tests**

Create `tests/test_organize_detail.py`:

```python
"""Tests for the context-aware organize detail string builder."""
from pathlib import Path
import pytest
from festival_organizer.progress import _organize_detail


class TestLiveRun:
    def test_rename_only_shows_new_filename(self):
        detail = _organize_detail(
            source=Path("/lib/old_name.mkv"),
            target=Path("/lib/new_name.mkv"),
            output_root=Path("/lib"),
            action="rename",
            dry_run=False,
        )
        assert detail == "new_name.mkv"

    def test_import_only_shows_relative_folder(self):
        detail = _organize_detail(
            source=Path("/inbox/file.mkv"),
            target=Path("/lib/Festivals/Ultra Miami 2026/file.mkv"),
            output_root=Path("/lib"),
            action="copy",
            dry_run=False,
        )
        assert detail == "Festivals/Ultra Miami 2026/"

    def test_both_changed_shows_full_relative(self):
        detail = _organize_detail(
            source=Path("/inbox/raw.mkv"),
            target=Path("/lib/Festivals/Ultra/clean.mkv"),
            output_root=Path("/lib"),
            action="copy",
            dry_run=False,
        )
        assert detail == "Festivals/Ultra/clean.mkv"

    def test_up_to_date(self):
        p = Path("/lib/file.mkv")
        detail = _organize_detail(
            source=p, target=p, output_root=Path("/lib"),
            action="rename", dry_run=False,
        )
        assert detail == "already at target"


class TestDryRun:
    def test_rename_only_preview(self):
        detail = _organize_detail(
            source=Path("/lib/old.mkv"),
            target=Path("/lib/new.mkv"),
            output_root=Path("/lib"),
            action="rename",
            dry_run=True,
        )
        assert detail == "would rename to new.mkv"

    def test_copy_preview(self):
        detail = _organize_detail(
            source=Path("/inbox/f.mkv"),
            target=Path("/lib/Fests/f.mkv"),
            output_root=Path("/lib"),
            action="copy",
            dry_run=True,
        )
        assert detail == "would copy to Fests/"

    def test_move_both_changed_preview(self):
        detail = _organize_detail(
            source=Path("/inbox/raw.mkv"),
            target=Path("/lib/Fests/Ultra/clean.mkv"),
            output_root=Path("/lib"),
            action="move",
            dry_run=True,
        )
        assert detail == "would move to Fests/Ultra/clean.mkv"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_organize_detail.py -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

In `festival_organizer/progress.py`, add at module level (after imports):

```python
def _organize_detail(
    *,
    source: Path,
    target: Path,
    output_root: Path,
    action: str,
    dry_run: bool,
) -> str:
    """Build the context-aware detail string for an organize verdict.

    Shows only what changed: new filename, new folder, or both.
    """
    if str(source) == str(target):
        return "already at target"

    folder_changed = str(source.parent) != str(target.parent)
    name_changed = source.name != target.name

    if folder_changed and name_changed:
        try:
            rel = target.relative_to(output_root)
        except ValueError:
            rel = target
        base = str(rel)
    elif folder_changed:
        try:
            rel = target.parent.relative_to(output_root)
        except ValueError:
            rel = target.parent
        base = str(rel) + "/"
    elif name_changed:
        base = target.name
    else:
        return "already at target"

    if dry_run:
        return f"would {action} to {base}"
    return base
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_organize_detail.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add festival_organizer/progress.py tests/test_organize_detail.py
git commit -m "feat(progress): add _organize_detail helper for context-aware verdict strings"
```

---

### Task 6: Add `sidecars_moved` attribute to `OrganizeOperation`

**Files:**
- Modify: `festival_organizer/operations.py:53-131`
- Modify: `tests/test_operations.py`

**Step 1: Write the failing test**

Add to `tests/test_operations.py`:

```python
def test_organize_op_tracks_sidecars_moved(tmp_path):
    """OrganizeOperation.sidecars_moved counts sidecars after execute."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"video")
    (tmp_path / "test.nfo").write_text("<nfo/>")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")

    target = tmp_path / "sub" / "test.mkv"
    op = OrganizeOperation(target=target, action="copy")
    result = op.execute(video, _make_mf())
    assert result.status == "done"
    assert op.sidecars_moved == 2


def test_organize_op_sidecars_moved_zero_when_none(tmp_path):
    """sidecars_moved is 0 when no sidecars exist."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"video")

    target = tmp_path / "sub" / "test.mkv"
    op = OrganizeOperation(target=target, action="copy")
    result = op.execute(video, _make_mf())
    assert result.status == "done"
    assert op.sidecars_moved == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_operations.py::test_organize_op_tracks_sidecars_moved tests/test_operations.py::test_organize_op_sidecars_moved_zero_when_none -v`
Expected: FAIL with AttributeError: 'OrganizeOperation' object has no attribute 'sidecars_moved'

**Step 3: Write implementation**

In `festival_organizer/operations.py`:

1. In `OrganizeOperation.__init__` (line 57), add `self.sidecars_moved = 0`:

```python
def __init__(self, target: Path, action: str = "move"):
    self.target = target
    self.action = action
    self.sidecars_moved = 0
```

2. Change `_move_sidecars` return type to `int` and return the count. Replace lines 100-131:

```python
def _move_sidecars(self, old_dir: Path, old_stem: str,
                   new_dir: Path, new_stem: str,
                   shutil, action: str) -> int:
    """Move/copy sidecar files from old_dir to new_dir, renaming stems.
    Returns the number of sidecars successfully moved/copied."""
    sidecars: list[Path] = []
    for candidate in old_dir.iterdir():
        if candidate.name in self.FOLDER_LEVEL_FILES:
            continue
        name = candidate.name
        if name.startswith(old_stem + ".") or name.startswith(old_stem + "-"):
            if not candidate.exists():
                continue
            sidecars.append(candidate)

    moved = 0
    for sidecar in sidecars:
        suffix = sidecar.name[len(old_stem):]
        new_name = new_stem + suffix
        new_path = new_dir / new_name

        try:
            if action == "copy":
                shutil.copy2(sidecar, new_path)
            elif action == "rename":
                sidecar.rename(new_path)
            else:
                shutil.move(str(sidecar), str(new_path))
            logger.debug("Sidecar %s: %s -> %s", action, sidecar.name, new_path.name)
            moved += 1
        except OSError as e:
            logger.warning("Failed to %s sidecar %s: %s", action, sidecar.name, e)
    return moved
```

3. In `execute` (around line 93-96), capture the return value:

```python
self.sidecars_moved = self._move_sidecars(
    old_dir, old_stem, target.parent, new_stem,
    shutil, self.action,
)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_operations.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add festival_organizer/operations.py tests/test_operations.py
git commit -m "feat(operations): track sidecars_moved count on OrganizeOperation"
```

---

### Task 7: Implement `OrganizeContractProgress` class

**Files:**
- Modify: `festival_organizer/progress.py`
- Create: `tests/test_organize_contract_progress.py`

**Step 1: Write the failing tests**

Create `tests/test_organize_contract_progress.py`:

```python
"""Tests for OrganizeContractProgress."""
import io
from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

from festival_organizer.operations import OrganizeOperation, OperationResult
from festival_organizer.progress import OrganizeContractProgress


def _console():
    return Console(file=io.StringIO(), width=120, no_color=True)


def _mf(content_type="festival_set"):
    m = MagicMock()
    m.content_type = content_type
    return m


def _capture(con) -> str:
    return con.file.getvalue()


class TestFileDone:
    def test_emits_done_verdict_for_rename(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="festival_nested",
        )
        op = OrganizeOperation(target=Path("/lib/new.mkv"), action="rename")
        op.sidecars_moved = 0
        result = OperationResult("organize", "done")
        p.file_done(
            source=Path("/lib/old.mkv"), media_file=_mf(),
            op=op, result=result, elapsed_s=0.1,
        )
        out = _capture(con)
        assert "done" in out
        assert "new.mkv" in out

    def test_emits_up_to_date_when_same_path(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="festival_nested",
        )
        target = Path("/lib/same.mkv")
        op = OrganizeOperation(target=target, action="rename")
        op.sidecars_moved = 0
        result = OperationResult("organize", "skipped", "exists")
        p.file_done(
            source=target, media_file=_mf(),
            op=op, result=result, elapsed_s=0.0,
        )
        out = _capture(con)
        assert "up-to-date" in out
        assert "already at target" in out

    def test_emits_error_verdict(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="copy", layout="festival_flat",
        )
        op = OrganizeOperation(target=Path("/lib/out/f.mkv"), action="copy")
        op.sidecars_moved = 0
        result = OperationResult("organize", "error", "Permission denied")
        p.file_done(
            source=Path("/in/f.mkv"), media_file=_mf(),
            op=op, result=result, elapsed_s=0.3,
        )
        out = _capture(con)
        assert "error" in out
        assert "Permission denied" in out

    def test_quiet_suppresses_output(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=True, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="festival_nested",
        )
        op = OrganizeOperation(target=Path("/lib/new.mkv"), action="rename")
        op.sidecars_moved = 0
        result = OperationResult("organize", "done")
        p.file_done(
            source=Path("/lib/old.mkv"), media_file=_mf(),
            op=op, result=result, elapsed_s=0.1,
        )
        assert _capture(con).strip() == ""


class TestFilePreview:
    def test_emits_preview_verdict(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=True,
            action="copy", layout="festival_flat",
        )
        p.file_preview(
            source=Path("/in/f.mkv"), media_file=_mf(),
            target=Path("/lib/Fests/Ultra/f.mkv"),
        )
        out = _capture(con)
        assert "preview" in out
        assert "would copy to" in out


class TestVerboseMetadata:
    def test_metadata_line_emitted(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=True,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="festival_nested",
        )
        op = OrganizeOperation(target=Path("/lib/new.mkv"), action="rename")
        op.sidecars_moved = 2
        result = OperationResult("organize", "done")
        p.file_done(
            source=Path("/lib/old.mkv"), media_file=_mf("festival_set"),
            op=op, result=result, elapsed_s=0.1,
        )
        out = _capture(con)
        assert "festival_set" in out
        assert "festival_nested" in out
        assert "2 sidecars" in out

    def test_metadata_line_absent_when_not_verbose(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="festival_nested",
        )
        op = OrganizeOperation(target=Path("/lib/new.mkv"), action="rename")
        op.sidecars_moved = 2
        result = OperationResult("organize", "done")
        p.file_done(
            source=Path("/lib/old.mkv"), media_file=_mf("festival_set"),
            op=op, result=result, elapsed_s=0.1,
        )
        out = _capture(con)
        assert "festival_set" not in out


class TestSummary:
    def test_prints_summary_panel(self):
        con = _console()
        p = OrganizeContractProgress(
            total=2, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="copy", layout="festival_flat",
        )
        op1 = OrganizeOperation(target=Path("/lib/Fests/Ultra/a.mkv"), action="copy")
        op1.sidecars_moved = 0
        p.file_done(
            source=Path("/in/a.mkv"), media_file=_mf(),
            op=op1, result=OperationResult("organize", "done"),
            elapsed_s=1.0,
        )
        op2 = OrganizeOperation(target=Path("/lib/Fests/Ultra/b.mkv"), action="copy")
        op2.sidecars_moved = 0
        p.file_done(
            source=Path("/in/b.mkv"), media_file=_mf(),
            op=op2, result=OperationResult("organize", "done"),
            elapsed_s=0.5,
        )
        p.print_summary(elapsed_s=1.5)
        out = _capture(con)
        assert "Summary" in out
        assert "done" in out
        assert "Fests/Ultra" in out
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_organize_contract_progress.py -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

In `festival_organizer/progress.py`, add `OrganizeContractProgress` class after `ProgressPrinter`:

```python
from festival_organizer.console import (
    escape, header_panel, make_console, organize_summary_panel,
    status_text, summary_panel, verdict,
)
# ... (update the import at top of file)


class OrganizeContractProgress:
    """Contract-compliant progress output for pure organize runs."""

    def __init__(
        self,
        total: int,
        console: Console | None = None,
        quiet: bool = False,
        verbose: bool = False,
        *,
        output_root: Path,
        dry_run: bool,
        action: str,
        layout: str,
    ):
        self.total = total
        self.console = console or make_console()
        self.quiet = quiet
        self.verbose = verbose
        self.output_root = output_root
        self.dry_run = dry_run
        self.action = action
        self.layout = layout
        self._file_index = 0
        self._stats: dict[str, int] = {
            "done": 0, "up_to_date": 0, "preview": 0,
            "skipped": 0, "error": 0,
        }
        self._destinations: dict[str, int] = {}
        self._skipped_reasons: dict[str, int] = {}
        self._errors: list[tuple[str, str]] = []

    def print_header(
        self,
        command: str,
        rows: dict[str, str],
        missing_tools: list[str] | None = None,
    ) -> None:
        self.console.print(header_panel(f"CrateDigger: {command}", rows))
        if missing_tools:
            for tool in missing_tools:
                self.console.print(
                    f"  [yellow]Warning: {tool} not found"
                    f" (some features may be limited)[/yellow]"
                )

    def file_start(self, filename: Path, target_folder: str) -> None:
        pass

    def file_done(
        self,
        source: Path,
        media_file,
        op: "OrganizeOperation",
        result: OperationResult,
        elapsed_s: float,
    ) -> None:
        self._file_index += 1

        # Determine verdict status and detail
        if result.status == "error":
            vstatus = "error"
            detail = result.detail or "unknown error"
            self._stats["error"] += 1
            self._errors.append((source.name, detail))
        elif result.status == "skipped" and str(source) == str(op.target):
            vstatus = "up-to-date"
            detail = "already at target"
            self._stats["up_to_date"] += 1
        elif result.status == "skipped":
            vstatus = "skipped"
            detail = result.detail or "skipped"
            self._stats["skipped"] += 1
            self._skipped_reasons[detail] = self._skipped_reasons.get(detail, 0) + 1
        else:
            vstatus = "done"
            detail = _organize_detail(
                source=source, target=op.target,
                output_root=self.output_root,
                action=self.action, dry_run=False,
            )
            self._stats["done"] += 1
            self._record_destination(op.target)

        if self.quiet:
            return

        console_width = self.console.size.width if self.console.size else 120
        self.console.print(verdict(
            status=vstatus, index=self._file_index, total=self.total,
            filename=source.name, detail=detail, elapsed_s=elapsed_s,
            width=console_width,
        ))

        if self.verbose and vstatus in ("done", "up-to-date"):
            self._print_metadata(media_file, op)

    def file_preview(
        self,
        source: Path,
        media_file,
        target: Path,
    ) -> None:
        self._file_index += 1
        detail = _organize_detail(
            source=source, target=target,
            output_root=self.output_root,
            action=self.action, dry_run=True,
        )
        if detail == "already at target":
            vstatus = "up-to-date"
            self._stats["up_to_date"] += 1
        else:
            vstatus = "preview"
            self._stats["preview"] += 1
            self._record_destination(target)

        if self.quiet:
            return

        console_width = self.console.size.width if self.console.size else 120
        self.console.print(verdict(
            status=vstatus, index=self._file_index, total=self.total,
            filename=source.name, detail=detail, elapsed_s=0.0,
            width=console_width,
        ))

        if self.verbose and vstatus == "preview":
            self._print_metadata(media_file, None)

    def _record_destination(self, target: Path) -> None:
        try:
            rel = target.parent.relative_to(self.output_root)
            folder = str(rel) if str(rel) != "." else "./"
        except ValueError:
            folder = str(target.parent)
        self._destinations[folder] = self._destinations.get(folder, 0) + 1

    def _print_metadata(self, media_file, op) -> None:
        parts = [media_file.content_type]
        parts.append(f"layout: {self.layout}")
        if op is not None and getattr(op, "sidecars_moved", 0) > 0:
            parts.append(f"{op.sidecars_moved} sidecars moved")
        self.console.print(f"    [dim]{' . '.join(parts)}[/dim]")

    def record_results(self, results: list[OperationResult]) -> None:
        pass

    def print_summary(self, elapsed_s: float | None = None, log_path: Path | None = None) -> None:
        self.console.print()
        self.console.print(organize_summary_panel(
            stats=self._stats,
            destinations=self._destinations or None,
            skipped_reasons=self._skipped_reasons or None,
            errors=self._errors or None,
            elapsed_s=elapsed_s,
        ))
```

Update the module imports at the top of `progress.py`:

```python
from festival_organizer.console import (
    escape, header_panel, make_console, organize_summary_panel,
    status_text, summary_panel, verdict,
)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_organize_contract_progress.py tests/test_organize_detail.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add festival_organizer/progress.py tests/test_organize_contract_progress.py
git commit -m "feat(progress): add OrganizeContractProgress class"
```

---

### Task 8: Wire CLI to use `OrganizeContractProgress`

**Files:**
- Modify: `festival_organizer/cli.py`
- Modify: `festival_organizer/runner.py`

This task requires careful surgery across both files. No new tests; existing tests + E2E verification validate.

**Step 1: Update runner.py to pass source/op/elapsed to file_done**

In `festival_organizer/runner.py`, the loop needs to pass extra data when the progress printer supports it. Replace the entire `run_pipeline` function:

```python
import time

def run_pipeline(
    files: list[tuple[Path, MediaFile, list[Operation]]],
    progress: ProgressPrinter,
) -> list[list[OperationResult]]:
    """Run operations for each file, emitting live progress."""
    all_results = []

    for file_path, media_file, operations in files:
        target_folder = ""
        for op in operations:
            if op.name == "organize" and hasattr(op, "target"):
                target_folder = str(op.target.parent.name) + "/" + op.target.name
                break

        progress.file_start(file_path, target_folder)

        file_results = []
        current_path = file_path
        file_start_time = time.perf_counter()

        for op in operations:
            op_display = getattr(op, "display_name", "") or ""
            try:
                needed = op.is_needed(current_path, media_file)
            except Exception as e:
                file_results.append(OperationResult(op.name, "error", str(e), display_name=op_display))
                continue

            if needed:
                result = op.execute(current_path, media_file)
                result.display_name = op_display
                if op.name == "organize" and result.status == "done":
                    current_path = op.target
            else:
                result = OperationResult(op.name, "skipped", "exists", display_name=op_display)
            file_results.append(result)

        elapsed = time.perf_counter() - file_start_time

        # Contract-aware progress: pass organize-specific context
        from festival_organizer.progress import OrganizeContractProgress
        if isinstance(progress, OrganizeContractProgress):
            organize_op = None
            organize_result = None
            for op, r in zip(operations, file_results):
                if op.name == "organize":
                    organize_op = op
                    organize_result = r
                    break
            if organize_op and organize_result:
                progress.file_done(
                    source=file_path, media_file=media_file,
                    op=organize_op, result=organize_result,
                    elapsed_s=elapsed,
                )
            else:
                progress.file_done(file_results)
        else:
            progress.file_done(file_results)

        progress.record_results(file_results)
        all_results.append(file_results)

    return all_results
```

**Step 2: Update cli.py to branch progress class and restructure dry-run**

In `festival_organizer/cli.py`, make these changes:

1. Update imports (at top, line 35):

```python
from festival_organizer.progress import ProgressPrinter, OrganizeContractProgress
```

2. Replace the progress creation block (around line 430). Change:

```python
progress = ProgressPrinter(total=0, console=console, quiet=quiet, verbose=verbose)
```

to:

```python
use_contract = (args.command == "organize" and not getattr(args, "enrich", False))
if use_contract:
    progress = OrganizeContractProgress(
        total=0, console=console, quiet=quiet, verbose=verbose,
        output_root=output,
        dry_run=getattr(args, "dry_run", False),
        action=header_action if getattr(args, "dry_run", False) else action,
        layout=config.default_layout,
    )
else:
    progress = ProgressPrinter(total=0, console=console, quiet=quiet, verbose=verbose)
```

Note: `header_action` is computed at line 459; the progress creation at line 430 runs before the header_action block. This needs restructuring: move the `header_action` computation BEFORE the progress creation. The header/action block at lines 457-473 must be moved before line 430, or `header_action` must be computed inline. The cleanest fix: compute `header_action` earlier (after `action` is computed at line 389-395).

Move lines 458-461 (the `header_action` computation) to right after line 395:

```python
if args.command == "organize":
    dry_run = getattr(args, "dry_run", False)
    header_action = action if not dry_run else (
        "move" if getattr(args, "move", False) else
        "rename" if source_inside_or_equals_output(root, output) else "copy"
    )
```

Then at the progress creation site, reference `header_action`.

3. Replace the dry-run shortcut block (lines 549-556). Change:

```python
if getattr(args, "dry_run", False):
    target_folder = render_folder(mf, config)
    target_name = render_filename(mf, config)
    target = output / target_folder / target_name
    progress.file_start(fp, target_folder + "/" + target_name)
    progress.file_done([])
    continue
```

to:

```python
if getattr(args, "dry_run", False):
    target_folder = render_folder(mf, config)
    target_name = render_filename(mf, config)
    target = output / target_folder / target_name
    if use_contract:
        progress.file_preview(source=fp, media_file=mf, target=target)
    else:
        progress.file_start(fp, target_folder + "/" + target_name)
        progress.file_done([])
    continue
```

4. Replace the classification_summary_panel block (lines 596-608). Change:

```python
if getattr(args, "dry_run", False):
    from festival_organizer.console import classification_summary_panel
    festival_count = sum(1 for _, mf in media_files if mf.content_type == "festival_set")
    concert_count = sum(1 for _, mf in media_files if mf.content_type == "concert_film")
    unrecognized = [fp.name for fp, mf in media_files if mf.content_type in ("unknown", "")]
    console.print()
    console.print(classification_summary_panel(
        total=len(media_files),
        festival_sets=festival_count,
        concerts=concert_count,
        unrecognized=unrecognized,
    ))
    return 0
```

to:

```python
if getattr(args, "dry_run", False):
    if use_contract:
        elapsed = time.monotonic() - start_time
        progress.print_summary(elapsed_s=elapsed)
    else:
        from festival_organizer.console import classification_summary_panel
        festival_count = sum(1 for _, mf in media_files if mf.content_type == "festival_set")
        concert_count = sum(1 for _, mf in media_files if mf.content_type == "concert_film")
        unrecognized = [fp.name for fp, mf in media_files if mf.content_type in ("unknown", "")]
        console.print()
        console.print(classification_summary_panel(
            total=len(media_files),
            festival_sets=festival_count,
            concerts=concert_count,
            unrecognized=unrecognized,
        ))
    return 0
```

5. Update the summary call (line 641). Change:

```python
progress.print_summary()
```

to:

```python
if use_contract:
    elapsed = time.monotonic() - start_time
    progress.print_summary(elapsed_s=elapsed)
else:
    progress.print_summary()
```

6. Remove the `Completed in Xs` line for contract runs (around line 657-659). Change:

```python
if not quiet:
    elapsed = time.monotonic() - start_time
    console.print(f"[dim]Completed in {elapsed:.1f}s[/dim]")
```

to:

```python
if not quiet and not use_contract:
    elapsed = time.monotonic() - start_time
    console.print(f"[dim]Completed in {elapsed:.1f}s[/dim]")
```

**Step 3: Run existing tests**

Run: `pytest tests/ -v --timeout=30`
Expected: PASS (no existing tests exercise the full CLI pipeline with real files, so structural changes are safe)

**Step 4: Commit**

```bash
git add festival_organizer/cli.py festival_organizer/runner.py
git commit -m "feat(organize): wire OrganizeContractProgress into CLI and runner"
```

---

## Phase 4: Kodi Sync Alignment

### Task 9: Refactor `sync_library` to use contract primitives

**Files:**
- Modify: `festival_organizer/kodi.py:189-307`
- Modify: `festival_organizer/cli.py` (pass suppressed flag)
- Modify: `tests/test_kodi.py`

**Step 1: Refactor `sync_library` signature and body**

In `festival_organizer/kodi.py`, update the function. Replace `sync_library` (lines 189-307):

```python
def sync_library(
    client: KodiClient,
    changed_paths: list[Path],
    console: Console,
    quiet: bool = False,
    path_mapping: dict | None = None,
    suppressed: bool = False,
) -> None:
    """Sync changed files with Kodi: refresh existing, scan for new, clean stale."""
    if not changed_paths:
        return

    import time
    from rich.text import Text
    from festival_organizer.console import (
        StepProgress, library_sync_summary_line,
    )

    logger.info("Syncing %d updated items with Kodi", len(changed_paths))
    phase_start = time.perf_counter()

    if not quiet:
        console.print()
        console.rule("Kodi sync", style="dim")

    # Build path-to-ID mapping from Kodi's library
    with StepProgress(console, enabled=not suppressed and not quiet) as sp:
        sp.update("Fetching Kodi library...")
        kodi_videos = client.get_music_videos()

        # Case-insensitive lookup
        kodi_lower: dict[str, str] = {p.lower(): p for p in kodi_videos}

        # Determine path mapping
        local_prefix = ""
        kodi_prefix = ""
        if path_mapping:
            local_prefix = path_mapping.get("local", "")
            kodi_prefix = path_mapping.get("kodi", "")
            if local_prefix and kodi_prefix:
                local_prefix = str(Path(local_prefix).resolve())
                logger.info("Path mapping (config): %s -> %s", local_prefix, kodi_prefix)

        if not (local_prefix and kodi_prefix):
            inferred = _infer_path_mapping(changed_paths, kodi_videos)
            if inferred:
                local_prefix, kodi_prefix = inferred

        # Filename fallback index
        filename_index: dict[str, int] = {}
        for kodi_path, mv_id in kodi_videos.items():
            name = kodi_path.rsplit("/", 1)[-1] if "/" in kodi_path else kodi_path
            filename_index[name.lower()] = mv_id

        unique_paths = list(dict.fromkeys(changed_paths))
        refreshed = 0
        not_found = 0

        for i, path in enumerate(unique_paths):
            sp.update(
                f"Refreshing {i + 1}/{len(unique_paths)}",
                filename=path.name,
            )

            mv_id = None

            if local_prefix and kodi_prefix:
                kodi_path = _translate_path(path, local_prefix, kodi_prefix, kodi_lower)
                if kodi_path:
                    mv_id = kodi_videos.get(kodi_path)

            if mv_id is None:
                mv_id = kodi_videos.get(str(path.resolve()))

            if mv_id is None:
                mv_id = filename_index.get(path.name.lower())
                if mv_id is not None:
                    logger.debug("Matched by filename: %s", path.name)

            if mv_id is not None:
                client.refresh_music_video(mv_id)
                logger.info("Refreshed in Kodi: %s", path.name)
                refreshed += 1
            else:
                logger.warning(
                    "Not in Kodi library (will be picked up by scan): %s",
                    path.name,
                )
                not_found += 1

        sp.update("Scanning for new files...")
        client.scan()

        sp.update("Cleaning stale entries...")
        client.clean()

    elapsed = time.perf_counter() - phase_start

    if not quiet:
        stats: dict[str, int] = {"refreshed": refreshed}
        if not_found:
            stats["not yet in library"] = not_found
        console.print(library_sync_summary_line("Kodi", stats, elapsed))
```

**Step 2: Update the CLI caller to pass `suppressed`**

In `festival_organizer/cli.py`, update `_run_kodi_sync` (around line 717). Change:

```python
sync_library(client, changed_paths, console, quiet,
             path_mapping=path_mapping)
```

to:

```python
from festival_organizer.console import suppression_enabled
suppressed = suppression_enabled(
    console, quiet=quiet,
    verbose=getattr(args, "verbose", False) if hasattr(args, "verbose") else False,
    debug=getattr(args, "debug", False) if hasattr(args, "debug") else False,
)
sync_library(client, changed_paths, console, quiet,
             path_mapping=path_mapping, suppressed=suppressed)
```

Wait, `_run_kodi_sync` doesn't have access to `args`. It receives `quiet` but not `verbose`/`debug`. Thread these through: update the signature:

```python
def _run_kodi_sync(
    all_results, pipeline_files, config, console, quiet,
    verbose=False, debug=False,
) -> None:
```

And update the caller at line 654:

```python
_run_kodi_sync(all_results, pipeline_files, config, console, quiet,
               verbose=verbose, debug=debug)
```

Then inside `_run_kodi_sync`, compute `suppressed`:

```python
from festival_organizer.console import suppression_enabled
suppressed = suppression_enabled(console, quiet=quiet, verbose=verbose, debug=debug)
```

And pass it:

```python
sync_library(client, changed_paths, console, quiet,
             path_mapping=path_mapping, suppressed=suppressed)
```

**Step 3: Update test_kodi.py**

Tests that call `sync_library` directly need the new `suppressed` kwarg. Grep for call sites in `tests/test_kodi.py` and add `suppressed=True` (tests run with a non-TTY console anyway).

**Step 4: Run tests**

Run: `pytest tests/test_kodi.py tests/test_console_library_sync.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add festival_organizer/kodi.py festival_organizer/cli.py tests/test_kodi.py
git commit -m "refactor(kodi): use StepProgress and library_sync_summary_line for Kodi sync output"
```

---

## Phase 5: Docs & Version

### Task 10: Update console.md contract

**Files:**
- Modify: `.claude/docs/console.md`

**Step 1: Update the contract**

1. Add `preview` (cyan) to the badge list in Rule 4 (line 22-23).
2. Replace the organize checklist stub (lines 36-43) with full contract language:
   - Verdict statuses: `done`, `up-to-date`, `preview`, `skipped`, `error`
   - Detail rules: context-aware (rename-only / import-only / both-changed / already-at-target)
   - `--verbose` metadata line format
   - Summary panel: counts + destinations + skipped-reasons + errors + elapsed
   - Kodi sync sub-phase: `library_sync_summary_line`
3. Add new primitives to the Primitives section: `organize_summary_panel`, `library_sync_summary_line`.

**Step 2: Commit**

```bash
git add .claude/docs/console.md
git commit -m "docs(console): update contract with preview badge and organize adoption"
```

---

### Task 11: Update organize.md docs

**Files:**
- Modify: `docs/commands/organize.md`

**Step 1: Add Output section**

Insert a new "## Console output" section after "## What files change" (after line 125). Describe:

- **Per-file verdict line** format with badge + [i/N] + filename + detail + elapsed
- **Badges**: `done` (file organized successfully), `up-to-date` (file already at target), `preview` (dry-run showing what would happen), `skipped`, `error`
- **Detail field**: shows only what changed (new filename for renames, destination folder for imports, both for combined, `would <action> to ...` for previews)
- **Summary panel**: counts + destinations breakdown + skipped reasons + errors + elapsed
- **`--verbose`**: adds a metadata line under each verdict showing classification, layout rule, and sidecar count
- **Kodi sync**: when `--kodi-sync` is active, a separate section appears showing transient progress during library sync, followed by a one-line summary

**Step 2: Commit**

```bash
git add docs/commands/organize.md
git commit -m "docs(organize): add console output section documenting verdict and summary shapes"
```

---

### Task 12: Version bump

**Files:**
- Modify: `pyproject.toml`

**Step 1: Bump version**

Run: `grep '^version' pyproject.toml` to confirm current version.
Change `version = "0.12.7"` to `version = "0.12.8"`.

**Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.12.8"
```

---

## Verification (end-to-end)

After all tasks are complete, run this checklist:

1. `pytest tests/ -v` -- full suite green
2. Copy 3 MKVs from `/home/martijn/_temp/cratedigger/data/test-sets/` to `/tmp/cd-test-src/`
3. `cratedigger organize /tmp/cd-test-src --output /tmp/cd-test-out --dry-run` -- expect `preview` badges with `would copy to ...` detail, summary with destinations
4. `cratedigger organize /tmp/cd-test-src --output /tmp/cd-test-out` -- expect `done` badges, summary with destinations, files exist
5. `cratedigger organize /tmp/cd-test-out` -- in-place re-organize; expect `done` or `up-to-date` verdicts
6. `cratedigger organize /tmp/cd-test-src --output /tmp/cd-test-out --verbose` -- expect dim metadata lines under each verdict
7. `cratedigger organize /tmp/cd-test-src --output /tmp/cd-test-out --enrich --dry-run` -- legacy output (classification panel), no new contract leakage
