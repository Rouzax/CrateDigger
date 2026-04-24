# organize

Move or copy your recordings into a structured library with consistent folder names
and filenames.

## What this is for

After running [`identify`](identify.md) (or if you are skipping that step), `organize`
takes your recordings from wherever they are and puts them into a clean library structure.
It classifies each file as a festival set or a concert recording, renames it using a
consistent template, and places it in the right folder.

Running `organize` also creates a `.cratedigger/` marker folder inside your library.
This marker is what allows [`enrich`](enrich.md) to run later.

## Usage

```bash
cratedigger organize <source> [options]
```

`<source>` is a file or folder. When given a folder, CrateDigger scans it for all
recognized media files and processes each one.

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output <path>` | `-o` | (see below) | Destination library folder |
| `--layout <name>` | | config default | Folder layout: `artist_flat`, `festival_flat`, `artist_nested`, `festival_nested` |
| `--move` | | off | Move files instead of copying when importing from a separate folder. Ignored for in-place operations. |
| `--dry-run` | | off | Preview what would happen without changing any files |
| `--enrich` | | off | Run all enrichment operations immediately after organizing |
| `--yes` | `-y` | off | Skip confirmation when re-organizing an existing library |
| `--kodi-sync` | | off | Notify Kodi to refresh updated items after organizing |
| `--config <path>` | | (none) | Path to a config.toml file |
| `--quiet` | `-q` | off | Suppress per-file progress output |
| `--verbose` | `-v` | off | Show detailed decisions |
| `--debug` | | off | Show cache hits, retries, and internal mechanics |

`--dry-run` and `--move` cannot be combined.

## How organize decides what to do

`organize` picks the file operation automatically based on the relationship between
your source and output paths.

| Situation | Action |
|-----------|--------|
| Source and output are the same folder, or source is inside the output folder | **Rename in place.** Files are renamed atomically within the library. No copying. |
| Source and output are separate folders (no `--move`) | **Copy.** Files are copied into the library. Source is left intact. |
| Source and output are separate folders (with `--move`) | **Move.** Files are moved into the library. Source folder is cleaned up afterward. |
| `--dry-run` | **Preview only.** Nothing is changed. Shows what would happen. |

### When you omit `--output`

If you do not specify `--output`, CrateDigger uses the library root it finds by looking
for a `.cratedigger/` folder in or above your source. If no library is found, it uses
the source folder itself as the output. Either way, source and output end up being the same
location, so the action is always **rename in place**.

### Examples

**Copy (first import, keep originals):**

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/
```

Source (`~/Downloads/sets/`) and output (`~/Music/Library/`) are separate folders.
CrateDigger copies each file into the library under the correct folder and filename.
Your originals in `~/Downloads/sets/` are untouched. Safe default for a first import.

**Move (import and clear the inbox):**

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --move
```

Same as above, but files are moved instead of copied. Once a file is in the library,
it is removed from `~/Downloads/sets/`. Empty source folders are cleaned up.

**Rename in place (re-organizing an existing library):**

```bash
cratedigger organize ~/Music/Library/
```

Source and output are the same library. No files are copied or moved elsewhere; they are
just renamed and repositioned within the library tree to match your current layout and
filename templates. Useful after changing your layout or template in the config.

**Preview before committing:**

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --dry-run
```

Shows exactly what would be copied and where, without touching any files. Run this first
if you are unsure what the result will look like.

## What files change

For each media file that is moved, copied, or renamed, CrateDigger also moves or copies
the matching sidecar files alongside it. Sidecar files are the extra files that sit next
to a video with the same base name:

- `{name}.nfo`
- `{name}-thumb.jpg`
- `{name}-poster.jpg`
- `{name}-fanart.jpg`

If any of these exist alongside the source file, they go with it. Their names are updated
to match the new filename.

`folder.jpg` and `fanart.jpg` belong to the folder, not to individual videos, so they
are handled differently:

- **When copying or moving from an external inbox:** they are not copied into the library.
  The [`enrich`](enrich.md) command generates fresh ones inside the library.
- **When re-organizing in place:** if all the videos in a folder move to a new destination
  folder, `folder.jpg` and `fanart.jpg` follow them automatically. If only some videos
  move, they stay in the original folder.

The `.cratedigger/` marker folder is created inside the output library on the first run.

## Console output

When you run `organize`, CrateDigger shows one line per file describing what happened.

### Per-file verdict

Each file gets a single result line in this format:

```
  <badge>  [i/N] <filename>  ->  <detail>  .  <elapsed>
```

The badge tells you the outcome:

| Badge | Meaning |
|-------|---------|
| `done` | File was successfully copied, moved, or renamed |
| `up-to-date` | File is already at the correct location; nothing changed |
| `preview` | Dry-run preview showing what would happen |
| `skipped` | File was skipped (not a recognized media file, or user declined) |
| `error` | Something went wrong (permission denied, disk full, etc.) |

The detail field shows only what changed:

- **Rename in place (same folder):** the new filename.
- **Import (same filename, new folder):** the destination folder.
- **Both changed:** the full relative path.
- **Dry-run:** prefixed with `would copy to`, `would move to`, or `would rename to`.

Elapsed time appears only when an operation takes more than half a second.

### Verbose output

With `--verbose`, each verdict is followed by a dim metadata line showing:

- The file's classification (festival set or concert)
- The layout rule applied
- How many sidecar files were moved alongside the video

### Summary panel

After all files are processed, a summary panel shows:

- **Counts:** how many files were done, up-to-date, previewed, skipped, or errored.
- **Destinations:** which folders files ended up in, sorted by count.
- **Skipped reasons:** why files were skipped, if any.
- **Errors:** which files failed and why, if any.
- **Elapsed:** total wall time.

### Kodi sync

When `--kodi-sync` is active, a separate Kodi sync section appears after the summary. It
shows transient progress while fetching the Kodi library and refreshing items, followed by
a one-line summary of how many items were refreshed and how many are not yet in the library.

## Layouts

CrateDigger supports four folder layouts, each with separate templates for festival sets
and concert recordings.

### artist_flat

All files for an artist go into a single folder, regardless of festival or year.
Good for smaller libraries or when you want a simple one-level structure.

```
Library/
  Martin Garrix/
    2024 - Martin Garrix - Tomorrowland.mkv
    2023 - Martin Garrix - AMF.mkv
  Armin van Buuren/
    2023 - Armin van Buuren - ASOT.mkv
```

### festival_flat

Festival sets are grouped by festival name. Concert recordings go into an artist folder.
Good when you primarily browse by festival.

```
Library/
  Tomorrowland/
    2024 - Martin Garrix - Tomorrowland.mkv
  AMF/
    2023 - Martin Garrix - AMF.mkv
  Armin van Buuren/
    2023 - Armin van Buuren - Untold.mkv
```

### artist_nested

Deep hierarchy: artist, then festival, then year. Good for large libraries where you
browse by artist and want sets organized by event and year within each artist folder.

```
Library/
  Martin Garrix/
    Tomorrowland/
      2024/
        2024 - Martin Garrix - Tomorrowland.mkv
  Coldplay/
    Live at Wembley/
      2023/
        Coldplay - Live at Wembley (2023).mkv
```

### festival_nested

Deep hierarchy: festival, then year, then artist. Good for large libraries where you
browse by event and want all artists at a given festival in one place.

```
Library/
  Tomorrowland/
    2024/
      Martin Garrix/
        2024 - Martin Garrix - Tomorrowland.mkv
  Untold/
    2023/
      Armin van Buuren/
        2023 - Armin van Buuren - Untold.mkv
```

## Classification

CrateDigger automatically classifies each file as either a **festival set** or a
**concert recording**. The classification determines which folder template and filename
template are applied.

If the automatic classification is wrong, you can override it for specific files using
glob patterns in the `content_type_rules` section of your
[config](../configuration.md#content-type-rules).

## Re-organizing an existing library

If your source is already a CrateDigger library (or inside one), `organize` performs
an in-place rename. Before doing this, CrateDigger asks for confirmation, since it
will rename folders and files that are already in place.

Use `--yes` to skip the confirmation prompt:

```bash
cratedigger organize ~/Music/Library/ --yes
```

Re-organizing is useful when you change your layout or filename template in the config
and want to apply the new naming to files already in the library.

## Common examples

**Import recordings into a library (safe default, copies files):**

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/
```

Source files are preserved. Good for a first import where you want to verify the result.

**Import and delete the originals after:**

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --move
```

**Preview what would happen before committing:**

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --dry-run
```

**Import with a specific layout:**

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --layout festival_nested
```

**Organize and enrich in one pass:**

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --enrich
```

**Re-organize an existing library after changing your layout config:**

```bash
cratedigger organize ~/Music/Library/
```

CrateDigger detects that source and output are the same library and renames in place.

## Common problems

**"Error: --dry-run and --move cannot be used together"**

These two flags are incompatible. Use `--dry-run` to preview, then run again with
`--move` (without `--dry-run`) to actually move.

**Files classified incorrectly**

CrateDigger classified a concert as a festival set, or vice versa. You can override this
by adding a path rule to `content_type_rules` in your
[config](../configuration.md#content-type-rules). A path rule is a simple wildcard pattern
that matches a folder or filename, for example `Coldplay/*` to force everything under a
`Coldplay` folder to be treated as a concert. See
[Configuration: content type rules](../configuration.md#content-type-rules) for examples.

**enrich fails after organize**

If you run `enrich` separately after `organize` and get an error saying "not a CrateDigger
library", check that `organize` completed successfully. It creates the `.cratedigger/`
marker folder that `enrich` requires.

## Advanced details

### Filename template syntax

Folder and filename templates support two types of fields:

**Required fields** (`{field}`): always included. If the value is empty, a fallback is
used (e.g., "Unknown Artist").

**Optional decorated fields** (`{ field}`, `{ - field}`, `{ [field]}`): the punctuation
inside the braces is included only when the field has a value. If the field is empty, the
entire token is removed.

```
{festival}{ edition}         -> "Tomorrowland Winter"  or  "Tomorrowland"
{artist}{ - set_title}       -> "Tiesto - Closing Set" or  "Tiesto"
{year} - {artist}{ [stage]}  -> "2024 - Tiesto [Mainstage]" or "2024 - Tiesto"
```

### Available fields

| Field | Description |
|-------|-------------|
| `artist` | Artist name (alias-resolved; for B2B sets, the first artist) |
| `festival` | Canonical festival name |
| `edition` | Festival edition (e.g., "Winter", "SoCal") |
| `year` | Event year |
| `date` | Full event date |
| `stage` | Stage name (from 1001Tracklists metadata if identified) |
| `set_title` | Set title or description |
| `title` | Full title (used mainly for concert recordings) |

### Default templates

**Folder templates** (by layout and content type):

| Layout | Festival set | Concert |
|--------|-------------|---------|
| artist_flat | `{artist}` | `{artist}` |
| festival_flat | `{festival}{ edition}` | `{artist}` |
| artist_nested | `{artist}/{festival}{ edition}/{year}` | `{artist}/{year} - {title}` |
| festival_nested | `{festival}{ edition}/{year}/{artist}` | `{artist}/{year} - {title}` |

**Filename templates:**

| Content type | Template |
|-------------|----------|
| festival_set | `{year} - {artist} - {festival}{ edition}{ [stage]}{ - set_title}` |
| concert_film | `{artist} - {title}{ (year)}` |

Templates are configurable in your [config](../configuration.md#filename-templates).

## What to do next

After organizing, run [`enrich`](enrich.md) to add artwork, posters, NFO files, and
metadata tags to your library.
