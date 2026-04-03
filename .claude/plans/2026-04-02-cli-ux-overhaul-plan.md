# CLI UX Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the CLI surface so the command names, ordering, flag semantics, and output guide new users toward the correct workflow: identify -> organize -> enrich.

**Architecture:** All changes are in the CLI/presentation layer. No changes to core pipeline logic (analyzer, operations, runner). The `chapters` command becomes `identify`, `scan`/`dry-run` become `organize --dry-run`, flag names become context-specific, and output gets classification/metadata summaries.

**Tech Stack:** Python, Typer (CLI framework), Rich (console output), pytest

---

### Task 1: Rename `chapters` command to `identify`

**Files:**
- Modify: `festival_organizer/cli.py:150-164` (command definition)
- Modify: `festival_organizer/cli.py:234-239` (dispatch handler)
- Modify: `festival_organizer/tracklists/cli_handler.py:113` (header panel title)
- Modify: `tests/test_cli.py` (update any references)

**Step 1: Update CLI command definition in `cli.py`**

Replace the `chapters` command (lines 150-164) with `identify`:

```python
@app.command()
def identify(
    root: RootArg,
    tracklist: Annotated[Optional[str], typer.Option("--tracklist", "-t", help="Tracklist URL, ID, or query")] = None,
    auto: Annotated[bool, typer.Option("--auto", help="Batch mode, no prompts")] = False,
    preview: Annotated[bool, typer.Option("--preview", help="Show chapters without embedding")] = False,
    fresh: Annotated[bool, typer.Option("--fresh", help="Ignore stored URLs, search again")] = False,
    delay: Annotated[Optional[int], typer.Option("--delay", help="Delay between files, seconds (default: 5)")] = None,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
) -> int:
    """Match files on 1001Tracklists; embed metadata and chapters."""
    return _dispatch("identify", locals())
```

**Step 2: Update the dispatch handler in `_run_command`**

Replace lines 233-239:

```python
    # Handle identify (1001Tracklists matching) separately
    if args.command == "identify":
        from festival_organizer.tracklists.cli_handler import run_chapters
        args.auto_select = getattr(args, "auto", False)
        args.ignore_stored_url = getattr(args, "fresh", False)
        return run_chapters(args, config, console=console)
```

**Step 3: Update header panel title in cli_handler.py**

In `cli_handler.py:113`, change:
```python
    con.print(header_panel("Tracklist Chapters", rows))
```
to:
```python
    con.print(header_panel("CrateDigger: Identify", rows))
```

**Step 4: Run tests**

Run: `pytest tests/test_cli.py -v`

Some tests reference `"scan"` which will be updated in Task 2, but the identify rename should not break existing tests since chapters tests are in `test_cli_postprocess.py` or use the handler directly.

**Step 5: Commit**

```
feat(cli): rename chapters command to identify

The command does far more than add chapters: it searches 1001Tracklists,
matches files, and embeds authoritative metadata (artist, festival, date,
stage, venue, genres, artwork URLs) plus chapter markers. The name
"identify" better communicates this.

Also renames --force to --fresh (ignore stored URLs, search again) to
distinguish from enrich's --force which means "regenerate artifacts".
```

---

### Task 2: Replace `scan`/`dry-run` with `organize --dry-run`

**Files:**
- Modify: `festival_organizer/cli.py:86-111` (remove scan and dry-run commands)
- Modify: `festival_organizer/cli.py:114-130` (add --dry-run to organize)
- Modify: `festival_organizer/cli.py:229-232` (remove dry-run alias handling)
- Modify: `festival_organizer/cli.py:350-357,391-393` (change scan logic to use dry_run flag)
- Modify: `tests/test_cli.py` (update all scan/dry-run references)

**Step 1: Remove scan and dry-run commands, add --dry-run to organize**

Delete the `scan` function (lines 86-97) and `dry_run` function (lines 100-111).

Update the `organize` command to add `--dry-run` and guard mutual exclusivity:

```python
@app.command()
def organize(
    root: RootArg,
    output: OutputOpt = None,
    layout: LayoutOpt = None,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview what would happen without making changes")] = False,
    move: Annotated[bool, typer.Option("--move", help="Move instead of copy (default: copy)")] = False,
    rename_only: Annotated[bool, typer.Option("--rename-only", help="Rename in place only")] = False,
    enrich: Annotated[bool, typer.Option("--enrich", help="Also run enrichment after organizing")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompts")] = False,
    kodi_sync: Annotated[bool, typer.Option("--kodi-sync", help="Notify Kodi to refresh updated items")] = False,
) -> int:
    """Move/copy files into library structure."""
    if dry_run and move:
        print("Error: --dry-run and --move cannot be used together.", file=sys.stderr)
        raise SystemExit(1)
    if dry_run and rename_only:
        print("Error: --dry-run and --rename-only cannot be used together.", file=sys.stderr)
        raise SystemExit(1)
    if move and rename_only:
        print("Error: --move and --rename-only cannot be used together.", file=sys.stderr)
        raise SystemExit(1)
    return _dispatch("organize", locals())
```

**Step 2: Update `_run_command` to remove dry-run alias handling**

Remove lines 229-232 (`if args.command == "dry-run": args.command = "scan"`).

**Step 3: Update scan logic to use dry_run flag**

In `_run_command`, replace `if args.command == "scan":` checks with `if getattr(args, "dry_run", False):`.

At line 350-357 (the per-file dry-run block):
```python
        if getattr(args, "dry_run", False):
            # Dry run: no operations, just show plan
            target_folder = render_folder(mf, config)
            target_name = render_filename(mf, config)
            target = output / target_folder / target_name
            progress.file_start(fp, target_folder + "/" + target_name)
            progress.file_done([])
            continue
```

At line 391-393 (post-loop dry-run message):
```python
    if getattr(args, "dry_run", False):
        console.print(f"\n[dim]Dry run complete. {len(media_files)} files scanned.[/dim]")
        return 0
```

Also: skip library init when dry_run is set. At line 278-280:
```python
    if args.command == "organize" and not getattr(args, "dry_run", False) and not library_root:
        init_library(output, layout=config.default_layout)
```

Also: skip the re-organize confirmation when dry_run is set. At line 254:
```python
    if args.command == "organize" and not getattr(args, "dry_run", False) and library_root and not explicit_output:
```

**Step 4: Update tests**

In `tests/test_cli.py`:

- `test_run_nonexistent_path`: change `run(["scan", ...])` to `run(["organize", "--dry-run", ...])`
- `test_verbose_flag_enables_info_logging`: change `"scan"` to `"organize", "--dry-run"`
- `test_debug_flag_enables_debug_logging`: change `"scan"` to `"organize", "--dry-run"`
- `test_dry_run_is_alias_for_scan`: remove this test entirely
- Add new test `test_organize_dry_run_no_ops` that verifies `--dry-run` shows files without modifying anything
- Add new test `test_organize_dry_run_move_conflict` that verifies `--dry-run` + `--move` errors
- Add new test `test_organize_move_rename_only_conflict` that verifies `--move` + `--rename-only` errors

```python
def test_organize_dry_run_no_ops():
    """--dry-run shows files without making changes."""
    with patch("festival_organizer.cli.scan_folder", return_value=[]):
        with patch("festival_organizer.cli.resolve_library_root", return_value=None):
            result = run(["organize", "/tmp", "--dry-run"])
    assert result == 0


def test_organize_dry_run_move_conflict(capsys):
    """--dry-run and --move cannot be used together."""
    result = run(["organize", "/tmp", "--dry-run", "--move"])
    assert result != 0


def test_organize_move_rename_only_conflict(capsys):
    """--move and --rename-only cannot be used together."""
    result = run(["organize", "/tmp", "--move", "--rename-only"])
    assert result != 0
```

**Step 5: Run all tests**

Run: `pytest tests/test_cli.py -v`

**Step 6: Commit**

```
refactor(cli): replace scan/dry-run with organize --dry-run

Removes scan and dry-run as standalone commands. Preview is now
organize --dry-run, which better communicates that it previews the
organize operation.

Also adds mutual exclusivity guards for --move/--rename-only/--dry-run.
```

---

### Task 3: Rename `enrich --force` to `--regenerate` and clean up enrich flags

**Files:**
- Modify: `festival_organizer/cli.py:133-147` (enrich command)
- Modify: `festival_organizer/cli.py:330,377-387,399` (force references in _run_command)
- Modify: `tests/test_cli.py` (if any test references enrich --force)

**Step 1: Update enrich command definition**

Replace the enrich command (lines 133-147):

```python
@app.command()
def enrich(
    root: RootArg,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    debug: DebugOpt = False,
    only: Annotated[Optional[str], typer.Option("--only", help="Operations: nfo, art, fanart, posters, tags")] = None,
    regenerate: Annotated[bool, typer.Option("--regenerate", help="Regenerate even if artifacts exist")] = False,
    kodi_sync: Annotated[bool, typer.Option("--kodi-sync", help="Notify Kodi to refresh updated items")] = False,
) -> int:
    """Add artwork, posters, NFO, and tags."""
    return _dispatch("enrich", locals())
```

Note: `--output` and `--layout` removed. Description updated.

**Step 2: Update `_run_command` to use `regenerate` instead of `force`**

At line 330, change:
```python
    force = getattr(args, "force", False)
```
to:
```python
    force = getattr(args, "regenerate", False) or getattr(args, "fresh", False)
```

This variable name `force` is internal; both `--regenerate` (enrich) and `--fresh` (identify) feed into it. This keeps the operations layer unchanged.

**Step 3: Remove the `enrich --only chapters` code path**

Delete lines 399-412 (the block that delegates to `run_chapters` when `"chapters" in only`).

**Step 4: Handle missing --output/--layout on enrich**

In `_run_command`, when command is `"enrich"` and there's no library root, error:

After line 244 (`if not root.exists():`), add:
```python
    if args.command == "enrich" and not library_root:
        print("Error: not a CrateDigger library. Run organize first.", file=sys.stderr)
        return 1
```

**Step 5: Run tests**

Run: `pytest tests/ -v`

**Step 6: Commit**

```
refactor(cli): rename enrich --force to --regenerate, remove --output/--layout

Enrich now auto-detects the library root. Removes --output and --layout
flags that leaked implementation details.

Also removes chapters from --only (use the identify command instead) and
renames --force to --regenerate for clarity.
```

---

### Task 4: Reorder commands and add workflow line to --help

**Files:**
- Modify: `festival_organizer/cli.py:54-67` (app definition and callback)

**Step 1: Reorder command definitions**

In `cli.py`, reorder the `@app.command()` functions so they appear in this order:
1. `identify`
2. `organize`
3. `enrich`
4. `audit_logos`

Typer shows commands in definition order, so this controls the help output.

**Step 2: Update the app help text**

Change lines 54-58:

```python
app = typer.Typer(
    name="cratedigger",
    help="CrateDigger: Festival set & concert library manager\n\nWorkflow: identify -> organize -> enrich",
    rich_markup_mode="rich",
    no_args_is_help=False,
)
```

**Step 3: Verify the help output**

Run: `cratedigger --help`

Expected output should show:
```
CrateDigger: Festival set & concert library manager

Workflow: identify -> organize -> enrich

Commands:
  identify      Match files on 1001Tracklists; embed metadata and chapters.
  organize      Move/copy files into library structure.
  enrich        Add artwork, posters, NFO, and tags.
  audit-logos   Check curated festival logo coverage.
```

**Step 4: Run tests**

Run: `pytest tests/test_cli.py -v`

**Step 5: Commit**

```
feat(cli): reorder commands and add workflow guidance to --help

Commands now appear in recommended workflow order: identify, organize,
enrich, audit-logos. Help text shows the recommended workflow.
```

---

### Task 5: Add classification summary to `organize --dry-run`

**Files:**
- Modify: `festival_organizer/progress.py` (add dry-run summary method)
- Modify: `festival_organizer/cli.py:391-393` (call new summary)
- Modify: `festival_organizer/console.py` (add classification_panel helper if needed)
- Create: `tests/test_progress_dry_run.py` (or add to existing test_console.py)

**Step 1: Write the failing test**

Add to `tests/test_console.py`:

```python
def test_summary_panel_with_classification():
    """Summary panel can include classification breakdown."""
    from festival_organizer.console import classification_summary_panel
    panel = classification_summary_panel(
        total=80,
        festival_sets=75,
        concerts=3,
        unrecognized=["Musical 8B", "Gala ontvangst"],
    )
    output = _render(panel)
    assert "Festival sets" in output
    assert "75" in output
    assert "Concerts" in output
    assert "3" in output
    assert "Unrecognized" in output
    assert "Musical 8B" in output
    assert "Gala ontvangst" in output
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_console.py::test_summary_panel_with_classification -v`
Expected: FAIL (function doesn't exist yet)

**Step 3: Implement `classification_summary_panel` in console.py**

Add to `festival_organizer/console.py`:

```python
def classification_summary_panel(
    total: int,
    festival_sets: int,
    concerts: int,
    unrecognized: list[str],
) -> Panel:
    """Dry-run classification breakdown panel."""
    body = Text()
    body.append("Festival sets: ", style="bold")
    body.append(str(festival_sets), style="green")
    body.append("\n")
    body.append("Concerts: ", style="bold")
    body.append(str(concerts), style="green")
    if unrecognized:
        body.append("\n")
        body.append(f"Unrecognized: ", style="bold")
        body.append(str(len(unrecognized)), style="yellow")
        for name in unrecognized:
            body.append(f"\n  {name}", style="yellow")
    return Panel(body, title="Dry Run Summary", expand=True)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_console.py::test_summary_panel_with_classification -v`
Expected: PASS

**Step 5: Wire it into the dry-run output in cli.py**

Replace the dry-run completion block (around line 391-393) with:

```python
    if getattr(args, "dry_run", False):
        # Build classification summary
        festival_count = sum(1 for _, mf in media_files if mf.content_type == "festival_set")
        concert_count = sum(1 for _, mf in media_files if mf.content_type == "concert_film")
        unrecognized = [fp.name for fp, mf in media_files if mf.content_type in ("unknown", "")]
        from festival_organizer.console import classification_summary_panel
        console.print()
        console.print(classification_summary_panel(
            total=len(media_files),
            festival_sets=festival_count,
            concerts=concert_count,
            unrecognized=unrecognized,
        ))
        return 0
```

**Step 6: Run all tests**

Run: `pytest tests/ -v`

**Step 7: Commit**

```
feat(cli): add classification summary to organize --dry-run

Shows a breakdown of festival sets, concerts, and unrecognized files
after a dry run. Unrecognized files are highlighted so users can catch
problems before committing.
```

---

### Task 6: Add metadata summary to `identify` output

**Files:**
- Modify: `festival_organizer/tracklists/cli_handler.py:116,128-149,152-153` (stats tracking and summary)
- Modify: `festival_organizer/console.py` (add identify summary panel)
- Add tests to: `tests/test_console.py`

**Step 1: Write the failing test for the new summary panel**

Add to `tests/test_console.py`:

```python
def test_identify_summary_panel():
    """Identify summary shows metadata breakdown."""
    from festival_organizer.console import identify_summary_panel
    panel = identify_summary_panel(
        stats={"added": 72, "updated": 5, "skipped": 1, "error": 2, "up_to_date": 0},
        tagged_count=77,
        festivals={"Tomorrowland": 45, "EDC Las Vegas": 10, "Ultra": 8},
        unmatched=["Musical 8B", "Gala ontvangst"],
    )
    output = _render(panel)
    assert "added" in output
    assert "72" in output
    assert "Metadata tagged" in output
    assert "77" in output
    assert "Tomorrowland" in output
    assert "45" in output
    assert "Unmatched" in output
    assert "Musical 8B" in output
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_console.py::test_identify_summary_panel -v`

**Step 3: Implement `identify_summary_panel` in console.py**

Add to `festival_organizer/console.py`:

```python
def identify_summary_panel(
    stats: dict[str, int],
    tagged_count: int = 0,
    festivals: dict[str, int] | None = None,
    unmatched: list[str] | None = None,
) -> Panel:
    """Summary panel for the identify command with metadata breakdown."""
    body = Text()

    # Standard stats line
    first = True
    for key, value in stats.items():
        if not first:
            body.append("  ")
        first = False
        style = "green" if key in ("added", "done", "up_to_date") else (
            "cyan" if key == "updated" else (
                "red" if key == "error" else "dim"
            )
        )
        body.append(f"{key}: ", style="bold")
        body.append(str(value), style=style)

    # Metadata tagged count
    if tagged_count:
        body.append(f"\n\nMetadata tagged: ", style="bold")
        body.append(str(tagged_count), style="green")
        body.append(" files")

    # Festival breakdown
    if festivals:
        body.append("\n")
        body.append("Festivals: ", style="bold")
        sorted_fests = sorted(festivals.items(), key=lambda x: -x[1])
        fest_parts = [f"{name} ({count})" for name, count in sorted_fests[:6]]
        body.append(", ".join(fest_parts))
        remaining = len(sorted_fests) - 6
        if remaining > 0:
            body.append(f", ... +{remaining} more", style="dim")

    # Unmatched files
    if unmatched:
        body.append("\n")
        body.append("Unmatched: ", style="bold")
        body.append(str(len(unmatched)), style="yellow")
        body.append(f" ({', '.join(unmatched[:5])})", style="yellow")
        if len(unmatched) > 5:
            body.append(f", ... +{len(unmatched) - 5} more", style="dim")

    return Panel(body, title="Summary", expand=True)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_console.py::test_identify_summary_panel -v`

**Step 5: Track metadata in cli_handler.py**

In `cli_handler.py`, add tracking state after stats initialization (line 116):

```python
    stats = {"added": 0, "updated": 0, "up_to_date": 0, "skipped": 0, "error": 0}
    tagged_festivals: dict[str, int] = {}
    unmatched_files: list[str] = []
    tagged_count = 0
```

After each successful `_process_file` call (line 143), add metadata tracking. The approach: read the file's tags after processing to check what festival was tagged. However, to keep it simple and avoid re-reading, we track based on the `_process_file` return status. Files that got `"added"` or `"updated"` were successfully tagged.

A cleaner approach: have `_process_file` return a richer result. But to minimize changes, we can inspect the file's analyse result to get the festival post-identify. Since the tags are already embedded at this point, we can re-analyse briefly. However, that's expensive.

Better approach: extend `_process_file` to return a tuple `(status, festival_name)`. This requires modifying its signature and all callers.

Simplest approach for now: after the loop, re-scan the files that were added/updated and read their new CRATEDIGGER_1001TL_FESTIVAL tag. But this is wasteful.

Most practical approach: track festivals during `_fetch_and_embed`. The export object already has `sources_by_type` which contains the festival name. We can collect this in the outer loop by making `_process_file` return additional metadata.

**Revised approach:** Change `_process_file` to return a dataclass or namedtuple instead of a plain string:

In `cli_handler.py`, add near the top:

```python
from dataclasses import dataclass

@dataclass
class IdentifyResult:
    status: str
    festival: str = ""
```

Update `_process_file` return type to `IdentifyResult`. Update `_fetch_and_embed` to return `IdentifyResult` with the festival from `export.sources_by_type`.

This is a moderate refactor. The key changes:
- `_process_file` returns `IdentifyResult` instead of `str`
- `_fetch_and_embed` returns `IdentifyResult` with festival extracted from export
- The main loop in `run_chapters` uses `.status` for stats and `.festival` for tracking

Then in the main loop:
```python
        try:
            result = _process_file(...)
            stats[result.status] = stats.get(result.status, 0) + 1
            if result.status in ("added", "updated") and result.festival:
                tagged_festivals[result.festival] = tagged_festivals.get(result.festival, 0) + 1
                tagged_count += 1
            elif result.status == "skipped" and not result.festival:
                # File had no match at all
                unmatched_files.append(filepath.name)
```

And replace the summary output (lines 152-153):
```python
    con.print()
    from festival_organizer.console import identify_summary_panel
    con.print(identify_summary_panel(
        stats=stats,
        tagged_count=tagged_count,
        festivals=tagged_festivals,
        unmatched=unmatched_files,
    ))
```

**Step 6: Add verbose per-file metadata line**

In `_fetch_and_embed`, after the "Embedded N chapters" line (line 383), add:

```python
        if not quiet:
            con.print(f"  [green]Embedded {len(chapters)} chapters.[/green]")
            if verbose and export:
                _print_tagged_metadata(export, con)
```

Add helper function:
```python
def _print_tagged_metadata(export, console: Console) -> None:
    """Print per-file tagged metadata (verbose mode only)."""
    parts = []
    if export.dj_artists:
        parts.append(", ".join(name for _, name in export.dj_artists))
    for source_type, names in export.sources_by_type.items():
        if source_type == "Open Air / Festival" and names:
            parts.append(names[0])
    if export.stage_text:
        parts.append(export.stage_text)
    if parts:
        console.print(f"  [dim]Tagged: {', '.join(parts)}[/dim]")
```

Note: `verbose` needs to be passed through to `_fetch_and_embed`. Add it as a parameter.

**Step 7: Run all tests**

Run: `pytest tests/ -v`

**Step 8: Commit**

```
feat(cli): add metadata summary to identify command output

Default output now shows a summary with festival breakdown and unmatched
files. With --verbose, each file also shows what metadata was tagged
(artist, festival, stage).
```

---

### Task 7: Show only missing tools in header panel

**Files:**
- Modify: `festival_organizer/progress.py:38-47` (print_header method)
- Modify: `festival_organizer/cli.py:286-298` (tools list building)
- Modify: `tests/test_console.py` (update header_panel tests if needed)

**Step 1: Update cli.py to pass missing tools instead of found tools**

Replace lines 286-298:

```python
    # Check for missing tools
    all_tools = {
        "mediainfo": metadata.MEDIAINFO_PATH,
        "ffprobe": metadata.FFPROBE_PATH,
        "mkvextract": metadata.MKVEXTRACT_PATH,
        "mkvpropedit": metadata.MKVPROPEDIT_PATH,
    }
    missing_tools = [name for name, path in all_tools.items() if not path]
    progress.print_header(
        command=("Organize (dry run)" if getattr(args, "dry_run", False) else args.command.capitalize()),
        source=root, output=output,
        layout=config.default_layout, missing_tools=missing_tools,
    )
```

**Step 2: Update `ProgressPrinter.print_header` to show warnings**

In `progress.py`, change the `print_header` method signature and body:

```python
    def print_header(
        self,
        command: str,
        source: Path,
        output: Path,
        layout: str,
        missing_tools: list[str] | None = None,
    ) -> None:
        """Print the run header."""
        rows = {
            "Source": str(source),
            "Output": str(output),
            "Layout": layout,
        }
        self.console.print(header_panel(f"CrateDigger: {command}", rows))
        if missing_tools:
            for tool in missing_tools:
                self.console.print(f"  [yellow]Warning: {tool} not found (some features may be limited)[/yellow]")
```

**Step 3: Run tests**

Run: `pytest tests/ -v`

**Step 4: Commit**

```
refactor(cli): show only missing tools as warnings in header

Removes the tools list from the header panel. Missing tools now appear
as yellow warnings below the header. Silence means all tools were found.
```

---

### Task 8: Update docs and config example

**Files:**
- Modify: `docs/console-style.md` (update command names)
- Modify: `docs/logging.md` (update command references if any)
- Modify: `config.example.json` (no changes needed here, but verify)
- Modify: `docs/plans/2026-04-02-cli-ux-overhaul-design.md` (mark as implemented)

**Step 1: Update docs/console-style.md**

Replace any references to "chapters command" with "identify command". Update the component catalog if needed.

**Step 2: Update docs/logging.md if it references command names**

Search for "scan", "chapters", "dry-run" and update to "organize --dry-run", "identify".

**Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: all pass

**Step 4: Commit**

```
docs: update console-style and logging docs for CLI rename
```

---

### Task 9: Final verification

**Step 1: Verify all help outputs**

```bash
cratedigger --help
cratedigger identify --help
cratedigger organize --help
cratedigger enrich --help
cratedigger audit-logos --help
```

Verify:
- Commands in workflow order: identify, organize, enrich, audit-logos
- Workflow line visible in main help
- identify description mentions metadata AND chapters
- organize has --dry-run, no scan/dry-run commands
- enrich has --regenerate (not --force), no --output/--layout, --only shows correct operations
- identify has --fresh (not --force)

**Step 2: Verify mutual exclusivity**

```bash
cratedigger organize /tmp --dry-run --move   # Should error
cratedigger organize /tmp --move --rename-only  # Should error
```

**Step 3: Run full test suite**

```bash
pytest tests/ -v
```

**Step 4: Commit any final fixes**
