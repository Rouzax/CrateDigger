# Organize

Move or copy files into a structured library with smart folder layouts and consistent filenames.

## Usage

```bash
cratedigger organize <source> [options]
```

The `<source>` argument is a file or folder to organize. When given a folder, all recognized media files are processed.

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output <path>` | `-o` | Output folder for the library |
| `--layout <name>` | | Folder layout (see below) |
| `--move` | | When importing: move files instead of copying (ignored for in-place re-organize, which always uses atomic rename) |
| `--dry-run` | | Preview what would happen without making changes |
| `--enrich` | | Run all enrichment operations after organizing |
| `--yes` | `-y` | Skip confirmation prompts |
| `--kodi-sync` | | Notify Kodi to refresh updated items |
| `--config <path>` | | Path to config.json |
| `--quiet` | `-q` | Suppress per-file progress |
| `--verbose` | `-v` | Show detailed progress and decisions |
| `--debug` | | Show cache hits, retries, and internal mechanics |

## Action selection

`organize` picks the file operation automatically from the source/output
relationship:

| You ran | Relationship | Action |
|---------|--------------|--------|
| `organize <inbox>` (no library marker, no `--output`) | source == output | **rename** (in place) |
| `organize <library>` or `organize <library>/sub` | source ⊆ output | **rename** (in place) |
| `organize <inbox> --output <library>` | disjoint | **copy** |
| `organize <inbox> --output <library> --move` | disjoint | **move** |
| any of the above with `--dry-run` | — | preview only |

The in-place rename is atomic and only changes the filename / folder within
the library; `--move` has no effect in this case (same-filesystem rename is
already what you'd get). `--dry-run` and `--move` cannot be combined.

## Layouts

CrateDigger supports four folder layouts. Each layout defines separate templates for festival sets and concert recordings.

### artist_flat

Files grouped by artist in a flat structure.

```
Library/
  Martin Garrix/
    2024 - Martin Garrix - AMF.mkv
  Armin van Buuren/
    2023 - Armin van Buuren - ASOT.mkv
```

### festival_flat

Festival sets grouped by festival; concerts grouped by artist.

```
Library/
  Tomorrowland/
    2024 - Martin Garrix - Tomorrowland.mkv
  Armin van Buuren/
    2023 - Armin van Buuren - Untold.mkv
```

### artist_nested

Deep hierarchy organized by artist, then festival/title, then year.

```
Library/
  Martin Garrix/
    Tomorrowland/
      2024/
        2024 - Martin Garrix - Tomorrowland.mkv
  Coldplay/
    2023 - Live at Wembley/
      Coldplay - Live at Wembley (2023).mkv
```

### festival_nested

Deep hierarchy organized by festival, then year, then artist.

```
Library/
  Tomorrowland/
    2024/
      Martin Garrix/
        2024 - Martin Garrix - Tomorrowland.mkv
  Martin Garrix/
    2023 - Armin van Buuren - Untold/
      2023 - Armin van Buuren - Untold.mkv
```

## Template syntax

Folder and filename templates use a Sonarr-style collapsing token syntax.

### Required fields

`{field}` is a required field. If the value is empty, a fallback value is used (e.g., "Unknown Artist").

```
{artist}/{year}
```

### Optional decorated fields

`{ edition}` or `{ - set_title}` are optional fields. The literal characters inside the braces (the space, dash, brackets) are included only when the field has a value. If the field is empty, the entire token vanishes.

```
{festival}{ edition}        -> "Tomorrowland Winter" or "Tomorrowland"
{artist}{ - set_title}      -> "Tiesto - Closing Set" or "Tiesto"
{year} - {artist}{ [stage]} -> "2024 - Tiesto [Mainstage]" or "2024 - Tiesto"
```

### Available fields

| Field | Description |
|-------|-------------|
| `artist` | Artist name (resolved via aliases, B2B split to first artist) |
| `festival` | Canonical festival name |
| `edition` | Festival edition (e.g., "Winter", "SoCal") |
| `year` | Release or event year |
| `date` | Event date |
| `stage` | Stage name (from 1001Tracklists metadata) |
| `set_title` | Set title or description |
| `title` | Full title (used mainly for concerts) |

### Default templates

**Folder layouts** (configurable per layout and content type):

| Layout | Festival set | Concert |
|--------|-------------|---------|
| artist_flat | `{artist}` | `{artist}` |
| festival_flat | `{festival}{ edition}` | `{artist}` |
| artist_nested | `{artist}/{festival}{ edition}/{year}` | `{artist}/{year} - {title}` |
| festival_nested | `{festival}{ edition}/{year}/{artist}` | `{artist}/{year} - {title}` |

**Filename templates**:

| Content type | Template |
|-------------|----------|
| festival_set | `{year} - {artist} - {festival}{ edition}{ [stage]}{ - set_title}` |
| concert_film | `{artist} - {title}{ (year)}` |

## Classification

CrateDigger automatically classifies files as either `festival_set` or `concert_film` based on metadata analysis. You can override classification with glob patterns in the [content_type_rules](../configuration.md#content-type-rules) config section.

## Re-organizing

When you run organize on an existing library (a folder that already contains a `.cratedigger` marker), CrateDigger asks for confirmation before proceeding. Use `--yes` to skip the prompt.

## Examples

Copy files into a library with the default layout:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/
```

Preview the result without making changes:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --dry-run
```

Move files using a specific layout:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --layout festival_nested --move
```

Organize and enrich in one pass:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --enrich
```

Re-organize an existing library in place (atomic rename, no duplication):

```bash
cratedigger organize ~/Music/Library/
```
