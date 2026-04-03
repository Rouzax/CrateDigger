# CLI UX Overhaul Design

## Problem

A usability walkthrough revealed that the CLI's command structure, naming, and help text actively mislead new users about the correct workflow.

The most important command (`chapters`) was named and described as a minor enrichment step, causing users to run it last instead of first. The actual optimal workflow is `chapters -> organize -> enrich`, but the help text, command ordering, and naming all steer users to `scan -> organize -> enrich -> chapters`.

Additional issues: redundant commands (scan/dry-run), inconsistent flag semantics (`--force` means different things on different commands), flags on commands where they don't belong (`--output`/`--layout` on enrich), and missing output summaries that would help users verify their work before committing.

## Decisions

### 1. Rename `chapters` to `identify`

The command searches 1001Tracklists, matches files, and embeds authoritative metadata (artist, festival, date, stage, venue, genres, artwork URLs) plus chapter markers. The name "chapters" undersells this. "identify" better communicates that this is where files get recognized and tagged.

New description: "Match files on 1001Tracklists; embed metadata and chapters."

### 2. Replace `scan`/`dry-run` with `organize --dry-run`

`scan` and `organize` share 90% of their logic. The only difference is scan skips file operations. Making this a flag is the honest representation. No install base, so no backwards compatibility needed.

Remove both `scan` and `dry-run` commands entirely. Add `--dry-run` flag to `organize`.

### 3. Rename `--force` to context-specific names

- `enrich --force` becomes `enrich --regenerate` (regenerate even if artifacts exist)
- `identify --force` becomes `identify --fresh` (ignore stored URLs, search fresh)

Different semantics deserve different names.

### 4. Remove `--output` and `--layout` from `enrich`

Enrich works on already-organized files inside a library. It auto-detects the library root from `.cratedigger/` marker. These flags leak implementation details into UX. If not in a library, show a clear error.

### 5. Remove `chapters` from `enrich --only`

With `identify` as its own command, there's no reason to have a chapters shortcut inside enrich. Valid `--only` values become: `nfo, art, fanart, posters, tags`.

### 6. Add workflow line to `--help`

Add "Recommended workflow: identify -> organize -> enrich" to the main help. Reorder command definitions to match:
1. `identify`
2. `organize`
3. `enrich`
4. `audit-logos`

### 7. Add classification summary to `organize --dry-run`

Show a breakdown panel after dry run:
```
Festival sets: 75
Concerts: 3
Unrecognized: 2
  Musical 8B
  Gala ontvangst
```

Unrecognized files highlighted in yellow.

### 8. Improve `identify` output

Default: per-file shows chapter count. Summary at end shows metadata breakdown (festivals found, unmatched files).

With `--verbose`: also show per-file "Tagged: artist, festival, date, stage" line.

### 9. Tools display: show only missing

Remove "Tools: mediainfo, ffprobe, ..." from header panel. Only show warnings when tools are missing. Silence means success.

### 10. Guard `--rename-only` + `--move` mutual exclusivity

Error if both passed together.

### 11. Show `--delay` default in help

"Delay between files, seconds (default: 5)"

### 12. Fix `--only` help text truncation

Use shorter help text: "Operations: nfo, art, fanart, posters, tags"
