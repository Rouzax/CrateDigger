# Audit Logos

Check curated festival logo coverage for your library.

## Usage

```bash
cratedigger audit-logos <library> [options]
```

The `<library>` argument must point to an existing CrateDigger library.

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--config <path>` | | Path to config.json |
| `--verbose` | `-v` | Show detailed progress and decisions |
| `--debug` | | Show cache hits, retries, and internal mechanics |

## What it does

The audit-logos command scans your library for all festival names, then checks whether a curated logo file exists for each one. It reports:

- **Festivals with logos** and the path to each logo file.
- **Festivals missing logos** with suggested paths for placing them.
- **Unmatched logo folders** that exist but do not correspond to any festival in your library.
- **Unsupported formats** (SVG, GIF, BMP, TIFF are not supported).

Curated logos drive the festival-gradient album poster layout. When a logo is missing, album posters for that festival fall back to fanart-derived or pure-gradient layouts. The [library layout page](../library-layout.md#curated-festival-logos) documents the logo file convention, the library-local vs user-level precedence, and which supported image formats land where.

## Example

```bash
cratedigger audit-logos ~/Music/Library/
```

Sample output:

```
Library: /home/user/Music/Library
Festivals found: 12

With curated logo (8):
  Tomorrowland: /home/user/.cratedigger/festivals/Tomorrowland/logo.png
  AMF: /home/user/.cratedigger/festivals/AMF/logo.png
  ...

Missing curated logo (4):
  Awakenings
    -> place logo at: /home/user/Music/Library/.cratedigger/festivals/Awakenings/logo.png
       or user-level: /home/user/.cratedigger/festivals/Awakenings/logo.png
  ...
```

## See also

- [Library layout: curated festival logos](../library-layout.md#curated-festival-logos) — file convention, location precedence, supported formats.
- [Library layout: album poster layouts](../library-layout.md#album-poster-folderjpg) — how logos feed the poster pipeline and which layout fires when a logo is or isn't available.
