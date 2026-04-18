# Console Output Contract

Every CrateDigger command emits output under this contract. All Rich
usage flows through `festival_organizer/console.py`.

## Rules (normative)

1. A single `rich.console.Console` on stdout, created via
   `festival_organizer.console.make_console()`. All output, including
   log records via `RichHandler`, flows through it.
2. Any blocking operation expected to take >= 300 ms must emit a
   transient spinner with a step label via `StepProgress`.
3. Live display is disabled when any of the following hold
   (`suppression_enabled(...)`): stdout is not a TTY, `--quiet`,
   `--verbose`, or `--debug`. Under suppression, header, per-file
   verdict line, and summary still print. Nothing transient is
   emitted.
4. Exactly one verdict block per processed file. Standard shape is
   two lines:

       <badge>  [i/N] <filename>  .  <elapsed>
                      <detail_line>

   Line 2 is aligned under the filename. Content is command-specific:
   - identify: match info + chapter count
   - organize: target path
   - enrich: done ops summary, error callouts

   When `detail_line` is None, falls back to single-line format with
   `->` (backward compat):

       <badge>  [i/N] <filename>  ->  <detail>  .  <elapsed>

   Badges: `done` (green), `updated` (cyan), `up-to-date` (dim
   green), `preview` (cyan), `skipped` (yellow), `error` (red).
   Elapsed omitted when wall time < 0.5s.
5. Interactive prompts (`input(...)`) must emit a trailing newline
   before the next print.
6. Header panel and summary panel built via `header_panel(...)` and
   `summary_panel(...)` / `identify_summary_panel(...)`.

## Adoption checklist per command

### identify
Reference implementation. See
`festival_organizer/tracklists/cli_handler.py`.

### organize
Reference implementation:
`festival_organizer/progress.py` (`OrganizeContractProgress`).

Verdict statuses: `done`, `up-to-date`, `preview`, `skipped`,
`error`. Does not use `updated`.

Organize uses the two-line verdict block. Detail line (line 2) is
context-aware (shows only what changed):
- Rename (same folder): new filename.
- Import (same name): target folder relative to output root, trailing `/`.
- Both changed: relative path including new filename.
- No-op: badge flips to `up-to-date`, detail = `already at target`.
- Dry-run: `preview` badge, detail prefixed with `would <action> to `.

`--verbose` emits a dim metadata line under each verdict:
`festival_set . layout: festival_nested . 2 sidecars moved`.

Summary panel: `organize_summary_panel(...)` with counts,
destinations breakdown, skipped reasons, errors list, elapsed.

Spinner policy: `StepProgress` wraps only slow paths (large-file
copy/move, Kodi sync phases). Sub-second rename ops get no spinner.

Kodi sync: distinct sub-phase after the pipeline. Dim rule header,
`StepProgress` for transient phases, one `library_sync_summary_line`
at end.

`organize --enrich` uses `OrganizeEnrichProgress` (composite) which
emits dual verdict blocks: the organize verdict followed immediately
by the enrich verdict for the same file.

### enrich
Reference implementation:
`festival_organizer/progress.py` (`EnrichContractProgress`).

Verdict badge uses worst-wins: error > done > up-to-date.

Detail line (line 2): comma-separated done op names. Errors called out
with `; op error: detail`. All skipped: `all up to date`.
Trivial skip reasons ("exists") are silently omitted; non-trivial
reasons (e.g. "run identify") are called out.

`--verbose` emits dim per-op breakdown lines after the verdict block
(checkmark/circle/cross + op name + detail).

Summary panel: `enrich_summary_panel(...)` with file-level stats,
per-op breakdown, errors list, unresolved artists count, elapsed.

Spinner policy: `StepProgress` updates label per op being executed.
Paused before verdict emission, restarted after.

### festival, chapters
- One verdict line per input. No network calls; step labels optional.

## Primitives

- `make_console(file=None) -> Console`
- `suppression_enabled(console, *, quiet, verbose, debug) -> bool`
- `StepProgress(console, enabled) -> context manager`
  - `.update(step, *, filename=None, current=0, total=0)`
  - `.start() / .stop()`
- `verdict(*, status, index, total, filename, detail, elapsed_s, width=None) -> Text`
- `header_panel(title, rows) -> Panel`
- `summary_panel(counts, log_path=None) -> Panel`
- `identify_summary_panel(...)` identify-specific extension
- `organize_summary_panel(...)` organize-specific summary
- `enrich_summary_panel(...)` enrich-specific summary (file stats, per-op breakdown, errors, unresolved artists)
- `OrganizeEnrichProgress` composite progress for `organize --enrich` (dual verdict blocks per file)
- `library_sync_summary_line(name, stats, elapsed_s)` post-pipeline sync summary
- `results_table(results, video_duration_mins, query_parts=None) -> Table`
- `print_error(message, console=None) -> None`
