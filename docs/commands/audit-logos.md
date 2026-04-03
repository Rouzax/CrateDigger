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

- **Festivals with logos** and the path to each logo file
- **Festivals missing logos** with suggested paths for placing them
- **Unmatched logo folders** that exist but do not correspond to any festival in your library
- **Unsupported formats** (SVG, GIF, BMP, TIFF are not supported)

## Logo locations

CrateDigger searches for logos in two directories:

1. `<library>/.cratedigger/festivals/<FestivalName>/logo.<ext>`
2. `~/.cratedigger/festivals/<FestivalName>/logo.<ext>`

Supported image formats: JPG, JPEG, PNG, WEBP.

The festival name in the directory path must match the canonical display name exactly (e.g., `Tomorrowland`, `Tomorrowland Winter`, `EDC Las Vegas`).

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
