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

### Interactive vs auto mode

In **interactive mode** (default), CrateDigger displays a ranked results table and prompts you to select the correct tracklist. You can type a number to select, or 0 to skip.

In **auto mode** (`--auto`), the top result is selected automatically if it meets minimum confidence thresholds (score and gap to the runner-up). Files that fall below the threshold are skipped.

The `auto_select` option in your config file sets the default behavior. The `--auto` flag overrides it.

### Chapter embedding

Once a tracklist is selected, CrateDigger:

1. Fetches the full tracklist from 1001Tracklists
2. Parses track entries into chapter markers with timestamps
3. Embeds chapters into the MKV file using mkvpropedit
4. Tags the file with metadata: tracklist URL, title, ID, date, genres, DJ artwork URL, stage name, and source information

### Stored URL handling

If a file already has a stored tracklist URL from a previous run, CrateDigger reuses it by default. In auto mode, it fetches and verifies the stored URL directly. In interactive mode, it prompts you to use the stored URL, skip, or research.

Use `--regenerate` to ignore stored URLs and search again. This flag also forces a full re-tag of the MKV even when the chapter structure is already current, which is useful for picking up new tag types (e.g. per-chapter PERFORMER / PERFORMER_NAMES / GENRE) or updated canonical names on files enriched by earlier CrateDigger versions.

### Per-chapter tags

`identify` writes these per-chapter tags at Matroska `TargetTypeValue=30`, one set per chapter:

| Tag | Example | Description |
|-----|---------|-------------|
| `PERFORMER` | `Afrojack` | Primary artist, alias-resolved |
| `PERFORMER_SLUGS` | `afrojack\|oliver-heldens` | Pipe-separated 1001TL slugs for every linked artist |
| `PERFORMER_NAMES` | `Afrojack\|Oliver Heldens` | Pipe-separated display names, aligned slot-for-slot with `PERFORMER_SLUGS` |
| `TITLE` | `Take Over Control` | Clean track title |
| `LABEL` | `WALL` | Record label |
| `GENRE` | `Electro House\|Big Room` | Pipe-separated per-track genres |

`PERFORMER_NAMES` is read by `enrich` to resolve per-artist MusicBrainz IDs. See [Enrich](enrich.md) for the `MUSICBRAINZ_ARTISTIDS` tag it writes alongside.

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
