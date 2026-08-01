# audit-logos

Check which places in your library have curated logo files for poster generation.

## What this is for

When `enrich` generates a `folder.jpg` poster for a place folder, it uses a curated logo if one is available. Without a logo, the poster falls back to a color gradient. `audit-logos` shows you exactly which places in your library have logos and which do not, and tells you where to place a logo file for any that are missing.

A "place" here is any event location CrateDigger routes a set by: a festival (Tomorrowland), a standalone venue (Red Rocks), or a free-text location from the tracklist page. Artist-routed sets are not listed; their posters use artist artwork, not place logos.

Run this any time you want to improve poster quality for a specific place, or after adding a new logo to verify it was picked up correctly.

## Before you start

`audit-logos` requires a CrateDigger library. Run [`organize`](organize.md) first. Without the `.cratedigger/` marker folder that `organize` creates, `audit-logos` exits with an error.

## Usage

```bash
cratedigger audit-logos <library> [options]
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--config <path>` | | Path to a config.toml file |
| `--verbose` | `-v` | Show detailed progress |
| `--debug` | | Show internal mechanics |

## What it reports

`audit-logos` scans your library for all recognized place names (festivals, venues, and locations), then checks whether a logo file exists for each one.

**Places with logos:** the place name and the path to the logo file being used.

**Places missing logos:** the place name and two suggested paths where you can place a logo file (library-local or user-level).

**Unmatched logo folders:** folders that exist inside your logo directories but do not match any place currently in your library. Usually these are leftovers from files you removed.

**Unsupported formats:** any logo files using a format CrateDigger cannot read (SVG, GIF, BMP, TIFF). Rename or convert them to a supported format.

## Where to place logo files

Logo files go in a folder named after the place, inside one of two locations:

| Location | Path | Scope |
|----------|------|-------|
| User-level (Linux / macOS) | `~/CrateDigger/places/{Place Name}/logo.{ext}` | All libraries |
| User-level (Windows) | `Documents\CrateDigger\places\{Place Name}\logo.{ext}` | All libraries |
| Library-local | `{library}/.cratedigger/places/{Place Name}/logo.{ext}` | This library only |

The library-local location takes precedence over the user-level location if both exist.

The place folder name must match the canonical display name CrateDigger uses for that place (the same name shown in the audit output).

**Supported formats:** JPG, PNG, WebP.

## Example

```bash
cratedigger audit-logos ~/Music/Library/
```

Sample output:

```
Library: /home/user/Music/Library
Places found: 12

With curated logo (8):
  Tomorrowland: /home/user/CrateDigger/places/Tomorrowland/logo.png
  AMF: /home/user/CrateDigger/places/AMF/logo.png
  ...

Missing curated logo (4):
  Red Rocks
    -> place logo at: /home/user/Music/Library/.cratedigger/places/Red Rocks/logo.png
       or user-level: /home/user/CrateDigger/places/Red Rocks/logo.png
  ...
```

After adding a logo for a missing place, regenerate its poster:

```bash
cratedigger enrich ~/Music/Library/ --only posters --regenerate
```

## Related

- [enrich: posters](enrich.md#posters-poster-images): how logos feed into poster generation
- [Library layout: festival logos](../library-layout.md#festival-logos): logo file convention and location precedence
