# Identify

Match recordings against 1001Tracklists, then embed metadata and chapter markers into MKV files.

## Usage

```bash
cratedigger identify <folder_or_file> [options]
```

The `<folder_or_file>` argument accepts a single MKV/WEBM file or a folder containing media files. When given a folder, CrateDigger scans for all MKV and WEBM files and processes each one.

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--tracklist <value>` | `-t` | Tracklist URL, numeric ID, or search query |
| `--auto` | | Batch mode; auto-select best match without prompts |
| `--preview` | | Show matched chapters without embedding them |
| `--regenerate` / `--fresh` | | Redo identification and re-tag even when chapters already exist |
| `--delay <seconds>` | | Delay between files in seconds (default: 5) |
| `--config <path>` | | Path to config.json |
| `--quiet` | `-q` | Suppress per-file progress |
| `--verbose` | `-v` | Show detailed progress and decisions |
| `--debug` | | Show cache hits, retries, and internal mechanics |

## How it works

### Search query generation

When no `--tracklist` is provided, CrateDigger builds a search query from the filename. It extracts the artist name, festival, year, and other details, then searches 1001Tracklists for matching entries.

Festival abbreviations (like "AMF", "EDC", "UMF") are automatically expanded to their full names for better search results, using the aliases defined in your [festival configuration](../festivals.md).

### Result scoring

Search results are scored based on multiple factors:

- Artist name match
- Festival/event name match
- Year match
- Duration similarity (compared to the media file duration)
- DJ and source name recognition from cached data

Results are ranked by score, with the best match shown first.

### Interactive selection

In **interactive mode** (default), CrateDigger displays a ranked results table and prompts you to pick the correct tracklist. Type a number to select, or `0` to skip.

The scoring rule of thumb: higher scores mean stronger matches. The top result is typically correct; the ranking surfaces alternatives when the filename is ambiguous or the file is mistitled. A large score gap between the top result and runner-up is a stronger signal than a high absolute score.

Sample session:

```
Analyzing 1 file...
  Tiësto - Live at We Belong Here Miami 2026 [2EQGqEvLAuE].mkv (2h 18m)

Search: "Tiesto We Belong Here Miami 2026"

Top matches:
  #   Score  Date        Duration  Title
  1   314    2026-03-01  2h 19m    Tiësto @ We Belong Here, Miami 2026
  2   186    2026-03-01  0h 58m    Tiësto @ Main Stage, We Belong Here Miami 2026 (Radio Edit)
  3   142    2025-02-28  1h 45m    Tiësto @ We Belong Here 2025
  4   121    2024-11-15  2h 02m    Tiësto @ EDC Orlando 2024
  5   98     2023-08-12  1h 30m    Tiësto @ Tomorrowland 2023

Select [1-5, 0=skip]: 1
Selected: Tiësto @ We Belong Here, Miami 2026 (2026-03-01)
Fetching tracklist... 38 tracks
Embedding chapters and tags...
  Chapters: 38 written
  TTV=70 tags: 14 written
  Per-chapter tags: 38 × (PERFORMER, PERFORMER_SLUGS, PERFORMER_NAMES, TITLE, LABEL, GENRE) written
Done.
```

If a file has a stored tracklist URL from a previous run, CrateDigger reuses it by default. In interactive mode you're prompted to use the stored URL, skip the file, or research (search again and pick a different result).

### Auto mode

With `--auto`, CrateDigger picks the top-scoring result automatically if it meets two thresholds: minimum absolute score and minimum gap to the runner-up. Files that fail either threshold are skipped without prompting. This makes `--auto` safe for batch processing: ambiguous matches get deferred to a later interactive pass rather than silently misidentified.

Set `auto_select: true` in your config to make auto mode the default; `--auto` on the CLI overrides the config either way.

### Chapter embedding

Once a tracklist is selected, CrateDigger:

1. Fetches the full tracklist from 1001Tracklists
2. Parses track entries into chapter markers with timestamps
3. Embeds chapters into the MKV file using mkvpropedit
4. Tags the file with metadata: tracklist URL, title, ID, date, genres, DJ artwork URL, stage name, and source information

### Stored URL handling

If a file already has a stored tracklist URL from a previous run, CrateDigger reuses it by default. In auto mode, it fetches and verifies the stored URL directly. In interactive mode, it prompts you to use the stored URL, skip, or research.

Use `--regenerate` to ignore stored URLs and search again. This flag also forces a full re-tag of the MKV even when the chapter structure is already current, which is useful for picking up new tag types (e.g. per-chapter PERFORMER / PERFORMER_NAMES / GENRE) or updated canonical names on files enriched by earlier CrateDigger versions.

### Tags written

`identify` writes per-chapter Matroska tags (`TargetTypeValue=30`) and album-level collection tags (`TargetTypeValue=70`) from the parsed tracklist. See the [tag reference](../tag-reference.md) for the full list with examples. `PERFORMER_NAMES` (per-chapter) and `CRATEDIGGER_1001TL_ARTISTS` (album-level) are later read by `enrich` to resolve MusicBrainz artist IDs.

### Self-healing legacy files

When `identify` runs against a file whose chapter structure is already current, it normally reports `Up to date` and skips the write step. CrateDigger also checks whether the file has the per-chapter tags (`PERFORMER`, `PERFORMER_SLUGS`, `PERFORMER_NAMES`, `GENRE` at `TargetTypeValue=30`). If any are missing, the full tagging flow runs automatically on the next `identify` pass, no flag required. Subsequent runs are byte-idempotent because chapter UIDs are deterministic.

## Examples

Identify all files in a folder interactively:

```bash
cratedigger identify ~/Downloads/sets/
```

Identify a single file with a known tracklist URL:

```bash
cratedigger identify recording.mkv --tracklist "https://www.1001tracklists.com/tracklist/xyz"
```

Batch process with auto-selection:

```bash
cratedigger identify ~/Downloads/sets/ --auto
```

Preview chapters without embedding:

```bash
cratedigger identify recording.mkv --preview
```

Re-identify files that were already processed:

```bash
cratedigger identify ~/Downloads/sets/ --regenerate --auto
```
