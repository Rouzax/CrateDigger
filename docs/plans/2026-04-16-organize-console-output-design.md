# Organize Console Output Contract

## Context

The CrateDigger console output contract was recently landed for the `identify` command (commits d0ba546..17375c4 on `main`, released as 0.12.7). It defines:

- A shared Rich console, with a `suppression_enabled` gate for non-TTY / `--quiet` / `--verbose` / `--debug`.
- A `StepProgress` primitive for transient spinners on slow operations.
- A `verdict(status, index, total, filename, detail, elapsed_s)` primitive that emits one styled line per file using five badges: `done` / `updated` / `up-to-date` / `skipped` / `error`.
- A summary panel primitive (`identify_summary_panel`) with counts + festivals + unmatched + elapsed.

The user's concern with organize today: **"it is very hard to see in dry-run or normal run what actually happens — also with in-place rename."** Per-file output is split across two lines (filename + target) and mixes op icons; dry-run has no per-file visibility at all (just a classification count panel).

This change applies the contract to `organize` as the smallest-blast-radius adopter, validating the primitives before the larger enrich-command rewrite. The `--enrich` path is explicitly out of scope — it keeps its current per-op-icon output and will be redesigned together with the enrich command.

**Save this design first.** Before executing implementation, copy this plan to `docs/plans/2026-04-16-organize-console-output-design.md` and commit it so the design is tracked in repo history alongside the identify design doc.

## Scope

**In:** `cratedigger organize` with `--dry-run`, `--move`, default copy, in-place rename (no `--output`), `--kodi-sync`, `--verbose`, `--debug`, `--quiet`.

**Out:** `cratedigger organize --enrich` (keeps current output untouched). `cratedigger enrich` (separate future command rewrite).

## Design decisions (locked via brainstorm)

1. **Spinner policy — wrap slow paths only.** `StepProgress` wraps the copy/move file loop (so large cross-filesystem copies have feedback) and Kodi sync phases. Sub-second in-place rename ops get no spinner; the verdict line is the only feedback.

2. **New `preview` badge (cyan).** Added to `verdict()`'s status set. Used by organize dry-run, and **identify is retrofitted in the same change** so both commands speak the same dialect (identify currently emits `status="done"` with a `"(preview)"` suffix — this drops the suffix and switches to `status="preview"`).

3. **Context-aware detail field.** The detail shows only what changed:
   - In-place rename, same folder → new filename.
   - Import, same filename → target folder (relative to output root, trailing `/`).
   - Both changed → `<rel-folder>/<new-filename>`.
   - No-op (file already at target) → badge flips to `up-to-date`, detail = `already at target`.
   - Skipped → reason (`not a video`, `user declined`, `unrecognized`).
   - Error → short exception message.
   - Dry-run → same rules, `preview` badge, detail prefixed with `would <verb> to `.

4. **`organize_summary_panel` primitive.** Counts row (`done` / `up-to-date` / `preview` / `skipped` / `error`) + destinations breakdown (top-N grouped by top-level target folder, sorted desc by count) + skipped reasons (if any) + errors list (capped with `+N more`) + elapsed. Used for both live and dry-run; replaces `classification_summary_panel` entirely.

5. **`library_sync_summary_line(name, stats, elapsed_s)` generic primitive.** Contract-styled one-liner for a post-pipeline sub-phase. Kodi is the first caller. Lyrion/Jellyfin sync are expected future callers — no `"Kodi"` hardcoded in the primitive layer.

6. **Kodi sync stays a distinct sub-phase.** Section header preserved (thinner/dim), transient phases (fetch / refresh-loop / scan / clean) wrapped in `StepProgress`, single `library_sync_summary_line` at the end replaces today's per-item dim line.

7. **`--verbose` per-file metadata line.** Dim line under each verdict: `festival set . layout: festival_nested . 2 sidecars moved`. Mirrors identify's per-verdict metadata pattern.

## Phased implementation

### Phase 1 — Primitives (`festival_organizer/console.py`)

- Add `"preview": ("preview", "cyan")` to `_VERDICT_STYLES` (after L318 `updated`, which is also cyan — that's fine, different label).
- Update module docstring and `.claude/docs/console.md` badge enumeration.
- Implement `organize_summary_panel(stats, destinations=None, skipped_reasons=None, errors=None, elapsed_s=None) -> Panel`. Follow the shape pattern of `identify_summary_panel`: dim separators between counts, bullet list for destinations (top-10 then `... +N more`), skipped-reasons section only when non-empty, errors capped at 10 with tail. Reuse `_format_elapsed` for the elapsed suffix.
- Implement `library_sync_summary_line(name, stats, elapsed_s) -> Text`. Reuses `_VERDICT_BADGE_WIDTH` and the `done` style. Stats dict iteration preserves insertion order; joins non-zero entries as `"<key> <value>"` with `", "` separator. Elapsed suffix gated by `_ELAPSED_THRESHOLD_S` as in `verdict()`.
- `classification_summary_panel` is removed (only one caller; replaced by `organize_summary_panel`).

### Phase 2 — Identify retrofit

- `festival_organizer/tracklists/cli_handler.py:633` — change `("previewed", "done", f"{title} . {N} chapters (preview)")` to `("previewed", "preview", f"{title} . {N} chapters")`. The `"previewed"` stat bucket is preserved.
- `festival_organizer/console.py:439` — `identify_summary_panel` colour map: `"previewed"` moves from green to cyan so the summary matches the `preview` badge.
- Any test asserting the `(preview)` literal string is updated.

### Phase 3 — Organize adoption

**New class.** Add `OrganizeContractProgress` in `festival_organizer/progress.py` alongside the existing `ProgressPrinter` (don't retrofit the old class — the behaviour divergence is too wide). Both classes share the `print_header` responsibility (either via module helper or duplicated small body).

`OrganizeContractProgress` responsibilities:

- `__init__(total, console, quiet, verbose, *, output_root, dry_run, action, layout)`.
- `file_start(...)` — no-op (the contract has no per-file preamble).
- `file_done(source: Path, media_file: MediaFile, op: OrganizeOperation, result: OperationResult, elapsed_s: float)` — note the extended signature; builds the detail string, emits one verdict, updates aggregators, emits the `--verbose` metadata line if applicable.
- `file_preview(source, media_file, target)` — dedicated dry-run path; constructs a synthetic `preview` verdict using the context-aware detail with `would <verb> to ` prefix.
- `print_summary(elapsed_s)` — builds destinations / skipped-reasons / errors dicts, calls `organize_summary_panel`.
- `pipeline_context()` — returns a `StepProgress` under the suppression gate, for the runner to update per file with `"Copying [i/N] filename"` / `"Moving [i/N] filename"`; `rename` and `dry_run` actions set the step label to a no-op state (spinner stops).

**Detail string helper.** Implement as module-level `_organize_detail(...)` in `progress.py` (unit-testable in isolation) with the locked context-aware rules. 4 success cases × 2 (live/dry-run) + 3 exception paths (skipped / error / up-to-date).

**Data plumbing (without mutating `OperationResult`).**

- `source` is already known to `runner.py` as the file being processed; pass it to `file_done`.
- `target` is on `OrganizeOperation.target` (mutated to resolved path at `operations.py:89`). Runner already holds the op reference; pass the op to `file_done`.
- `sidecars_moved`: add an instance attribute on `OrganizeOperation` (not `OperationResult`). Change `_move_sidecars` to count successful moves and assign to `self.sidecars_moved` before returning. Runner reads `op.sidecars_moved` when building the verbose metadata line.
- `media_file.content_type` gives the classification label for the verbose line.
- `config.default_layout` gives the layout rule; passed once at `OrganizeContractProgress.__init__`.

**CLI wiring (`festival_organizer/cli.py`).**

- Progress instantiation (currently ~L430): branch on `command == "organize" and not args.enrich` → instantiate `OrganizeContractProgress`, else existing `ProgressPrinter`.
- Dry-run shortcut (currently ~L549–556): call `progress.file_preview(...)` per file; let the run fall through to `progress.print_summary(elapsed)` instead of the early `return 0`.
- Classification panel block (currently ~L596–608): removed. Summary panel absorbs.
- Completion signal `[dim]Completed in Xs[/dim]` (currently ~L659): remove for the pure-organize path (the summary panel already carries elapsed); keep for the enrich-path fallback.
- Action detection: pass the resolved action (not `"dry_run"`) into `OrganizeContractProgress(action=...)`; dry-run is signalled by the separate `dry_run=True` init arg. This mirrors `cli.py:459–462` which already recomputes `header_action` for the header.

**Runner (`festival_organizer/organize/runner.py`).**

- Time each op execution; pass `elapsed_s`, `source`, `op`, and the single organize `result` to `file_done` on the contract class. The legacy `ProgressPrinter.file_done` keeps its current `(results: list)` signature via duck typing at the CLI layer (distinct branches for the two classes) OR accept the extra args via `*args, **kwargs` ignored.

### Phase 4 — Kodi sync alignment (`festival_organizer/kodi.py`)

- Replace the bold `Kodi sync` banner with a thinner dim header (`console.rule("Kodi sync", style="dim")` or equivalent).
- Wrap transient phases (fetch, per-item refresh loop, scan, clean) in a single `StepProgress`, updating step labels per phase. Per-item: `sp.update(f"Refreshing {i}/{N}", filename=path.name)`.
- Remove the per-item `✓ refreshed N  ○ M not yet in library` dim line.
- At end of `sync_library`, emit `console.print(library_sync_summary_line("Kodi", stats, elapsed))` where `stats = {"refreshed": N, "not yet in library": M}` (second key omitted when zero).
- Thread `suppressed: bool` into `sync_library` (computed via `suppression_enabled` at the CLI layer). `StepProgress(enabled=not suppressed)` makes non-TTY / `--verbose` / `--debug` degrade to summary-only output.

### Phase 5 — Docs & version

- `.claude/docs/console.md` — add `preview` to the badge list; expand the organize adoption checklist from stub to full contract language.
- `docs/commands/organize.md` — add an "Output" section (after "What files change") describing verdict shape, summary panel, `--verbose` metadata, dry-run preview shape.
- `docs/plans/2026-04-16-organize-console-output-design.md` — save this plan as the design artefact (commit in Phase 0, before implementation).
- `pyproject.toml` — bump version to `0.12.8`.

## Critical files

- `/home/martijn/CrateDigger/festival_organizer/console.py` — primitives (verdict, organize_summary_panel, library_sync_summary_line).
- `/home/martijn/CrateDigger/festival_organizer/progress.py` — new `OrganizeContractProgress` class + `_organize_detail` helper.
- `/home/martijn/CrateDigger/festival_organizer/cli.py` — progress-class branching, dry-run flow, summary call sites.
- `/home/martijn/CrateDigger/festival_organizer/organize/runner.py` — pass source/op/elapsed to progress.
- `/home/martijn/CrateDigger/festival_organizer/operations.py` — `OrganizeOperation` gains a `sidecars_moved` instance attribute populated by `_move_sidecars`.
- `/home/martijn/CrateDigger/festival_organizer/kodi.py` — Kodi sync rewrite to contract primitives.
- `/home/martijn/CrateDigger/festival_organizer/tracklists/cli_handler.py` — identify retrofit for `preview` badge.
- `/home/martijn/CrateDigger/.claude/docs/console.md` and `/home/martijn/CrateDigger/docs/commands/organize.md` — documentation.
- `/home/martijn/CrateDigger/pyproject.toml` — version bump.

## Testing plan

**Unit tests (new or extended).**

- `tests/test_console_verdict.py` — extend parametrize to include `preview` / cyan; assert badge-padding regression still holds.
- `tests/test_organize_summary_panel.py` (new) — empty stats, destinations grouping/truncation, skipped-reasons omitted when empty, errors cap with `+N more`, elapsed formatting.
- `tests/test_library_sync_summary_line.py` (new) — name substitution, short-elapsed suppression, generic name ("Lyrion") works.
- `tests/test_organize_detail.py` (new, or appended to `test_progress.py`) — the 4×2 context-aware detail cases + 3 exception paths.
- `tests/test_operations.py` — `OrganizeOperation._move_sidecars` populates `sidecars_moved` across copy/move/rename.

**Integration / regression.**

- Update any identify snapshot or text-assertion test referencing `(preview)` literal.
- Existing `organize --enrich` tests must still pass untouched (they use `ProgressPrinter`).
- Add one dry-run integration test asserting a `preview` verdict line renders (no classification panel).

## Verification (end-to-end, post-implementation)

Prereq: test fixtures exist at `/home/martijn/_temp/cratedigger/data/test-sets/` (5 MKVs with YouTube-style `[id]` suffixes).

1. `cratedigger organize --help` renders without error.
2. **Dry-run, import layout.** Copy 3 MKVs to `/tmp/cd-test-src/`, run:
   `cratedigger organize /tmp/cd-test-src --output /tmp/cd-test-out --dry-run`
   Expect: 3 `preview` badges with `would copy to Festivals/…/` detail; summary panel with `preview: 3` and a destinations breakdown; no mutations on disk.
3. **Live copy, import layout.** Same source, drop `--dry-run`. Expect: 3 `done` badges with folder-or-both detail; summary with `done: 3` and destinations breakdown; files exist under `/tmp/cd-test-out/`.
4. **In-place rename re-organize.** Point organize at `/tmp/cd-test-out/` without `--output`. Expect: `done` verdicts showing only the new filename in detail (folder unchanged for files already in the right folder), or `up-to-date` with `already at target` where the filename matches.
5. **Verbose.** Add `--verbose` to (3). Expect: spinner suppressed; under each verdict a dim line `festival set . layout: <layout> . N sidecars moved` (or no sidecar clause when count is 0).
6. **Enrich path regression.** Run `cratedigger organize /tmp/cd-test-src --output /tmp/cd-test-out --enrich --dry-run`. Expect: classification panel (legacy output) unchanged. Confirms the new contract did not leak into the enrich path.
7. **Identify preview regression.** Run an `identify --preview` on a file with a known 1001TL result. Expect: `preview` badge (not `done`), detail without `(preview)` suffix.
8. **Kodi sync (if Kodi available).** Add `--kodi-sync` to (3). Expect: dim `Kodi sync` header, transient phase spinners, one contract-styled summary line at the end (`done  Kodi sync  ->  refreshed N, M not yet in library  .  Xs`).
9. `pytest` — full suite green on 3.11 / 3.12 / 3.13 (CI).

## Risks & edge cases

- **`--dry-run --move` combination** already blocked at `cli.py:142–144`; no new handling needed.
- **Cross-filesystem `shutil.move` fallback to copy+delete** — `StepProgress` label "Moving" remains accurate; the slowness is what the spinner is for.
- **Sidecar collision or OSError during rename** — `_move_sidecars` already swallows warnings; `sidecars_moved` counts successes only. An incomplete sidecar move does not flip the main verdict to error (existing behaviour, preserved).
- **Huge folder paths under narrow terminals** — `verdict()` truncates `filename` but not `detail`; Rich soft-wraps long target paths. Acceptable for now; documented as an edge case. Extending `verdict()` to also soft-truncate `detail` is out of scope.
- **Run with 200+ destination folders** — handled by the top-N-then-`+more` truncation in `organize_summary_panel`.
- **Empty file list** — today's "Nothing to do." line at `cli.py:483` stays as-is (pre-contract wording; not a verdict line).
- **Resolved-action vs dry-run** — pass the resolved action (`copy`/`move`/`rename`) to `OrganizeContractProgress`, not `"dry_run"`. The `dry_run=True` init arg gates the `would <verb> to ` prefix.
