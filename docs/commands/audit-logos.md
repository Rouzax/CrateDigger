# audit-logos

Check which festivals in your library have curated logo files for poster generation.

## What this is for

When `enrich` generates a `folder.jpg` poster for a festival folder, it uses a curated logo if one is available. Without a logo, the poster falls back to a color gradient. `audit-logos` shows you exactly which festivals in your library have logos and which do not, and tells you where to place a logo file for any that are missing.

Run this any time you want to improve poster quality for a specific festival, or after adding a new logo to verify it was picked up correctly.

## Before you start

`audit-logos` requires a CrateDigger library. Run [`organize`](organize.md) first. Without the `.cratedigger/` marker folder that `organize` creates, `audit-logos` exits with an error.

## Usage

```bash
cratedigger audit-logos <library> [options]
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--config <path>` | | Path to a config.json file |
| `--verbose` | `-v` | Show detailed progress |
| `--debug` | | Show internal mechanics |

## What it reports

`audit-logos` scans your library for all recognized festival names, then checks whether a logo file exists for each one.

**Festivals with logos:** the festival name and the path to the logo file being used.

**Festivals missing logos:** the festival name and two suggested paths where you can place a logo file (library-local or user-level).

**Unmatched logo folders:** folders that exist inside your logo directories but do not match any festival currently in your library. Usually these are leftovers from files you removed.

**Unsupported formats:** any logo files using a format CrateDigger cannot read (SVG, GIF, BMP, TIFF). Rename or convert them to a supported format.

## Where to place logo files

Logo files go in a folder named after the festival, inside one of two locations:

| Location | Path | Scope |
|----------|------|-------|
| User-level | `~/.cratedigger/festivals/{Festival Name}/logo.{ext}` | All libraries |
| Library-local | `{library}/.cratedigger/festivals/{Festival Name}/logo.{ext}` | This library only |

The library-local location takes precedence over the user-level location if both exist.

The festival folder name must match the canonical display name CrateDigger uses for that festival (the same name shown in the audit output).

**Supported formats:** JPG, PNG, WebP.

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

After adding a logo for a missing festival, regenerate its poster:

```bash
cratedigger enrich ~/Music/Library/ --only posters --regenerate
```

## Related

- [enrich: posters](enrich.md#posters-poster-images): how logos feed into poster generation
- [Library layout: curated festival logos](../library-layout.md#curated-festival-logos): logo file convention and location precedence
