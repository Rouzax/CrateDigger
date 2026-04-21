# enrich

Add artwork, posters, metadata files, and tags to your CrateDigger library.

## What this is for

After your files are organized into a library, `enrich` fills in everything that makes
the library usable in a media player. It generates the cover art thumbnails, poster
images, and NFO files that Kodi, Plex, and Jellyfin read to display your recordings
correctly. It also embeds structured metadata tags into the MKV files themselves.

You can run `enrich` as many times as you like. It skips files that already have
up-to-date artifacts, so re-running it is fast and safe.

## Before you start

`enrich` requires a CrateDigger library. Run [`organize`](organize.md) first. The
`.cratedigger/` folder that `organize` creates is what `enrich` uses to confirm it is
working on the right folder. Without it, `enrich` exits with an error.

## Usage

```bash
cratedigger enrich <library> [options]
```

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--only <ops>` | | (all) | Run only specific operations. Comma-separated. See below. |
| `--regenerate` | | off | Re-create artifacts even if they already exist |
| `--kodi-sync` | | off | Notify Kodi to refresh updated items after enriching |
| `--config <path>` | | (none) | Path to a config.toml file |
| `--quiet` | `-q` | off | Suppress per-file progress output |
| `--verbose` | `-v` | off | Show detailed progress and decisions |
| `--debug` | | off | Show cache hits, retries, and internal mechanics |

## What enrich does

By default, `enrich` runs all operations in sequence. Use `--only` to run a subset:

```bash
cratedigger enrich ~/Music/Library/ --only nfo,posters
```

### art: cover art

Extracts the thumbnail image used by everything else.

CrateDigger looks for artwork embedded inside the MKV file. If found, it saves it as
`{name}-thumb.jpg` alongside the video. It also copies the same image as `{name}-fanart.jpg`,
which is the filename Kodi expects for its fanart slot.

If no embedded artwork exists and the `vision` extra is installed, CrateDigger samples a
frame from the video instead. Without embedded art and without the `vision` extra, a color
gradient image is generated as a fallback so the rest of the pipeline always has a thumbnail
to work with. See [getting started](../getting-started.md#optional-video-frame-sampling) for
how to install the `vision` extra.

**Skipped if:** `{name}-thumb.jpg` already exists (unless `--regenerate`).

### fanart: artist artwork

Downloads high-quality artist images from [fanart.tv](https://fanart.tv) (a community
site with artist logos, backgrounds, and thumbnails). These are saved to a shared cache
folder (`~/.cache/CrateDigger/artists/{artist}/` on Linux, `%LOCALAPPDATA%\CrateDigger\Cache\artists\{artist}\` on Windows) and used as backgrounds in poster generation.

To find an artist's images on fanart.tv, CrateDigger first resolves their MusicBrainz ID.
It uses the same lookup chain as the MBID operations: your override file first, then the
auto-cache, then a live MusicBrainz search. This lookup is used only for image retrieval
and is not written to your MKV files. For that, see `chapter_artist_mbids` and
`album_artist_mbids` below. Artists whose name cannot be resolved to a MusicBrainz ID
are skipped.

Requires `fanart.enabled: true` in your config (the default). A built-in API key is
included; you can optionally add your own personal key for faster lookups.

**Skipped if:** artwork is already cached and not expired. Cache lifetimes use the TTL
you configure (default 90 days) with a ±20% random spread per entry, so individual
artists may refresh slightly earlier or later than the exact configured value. This
prevents all cached items from expiring at the same time on large libraries.

### posters: poster images

Generates two types of poster image for each recording:

- **`{name}-poster.jpg`**: a per-video poster showing artist name, festival, date, and
  stage, overlaid on a background image
- **`folder.jpg`**: an album-level poster for the folder, used by media players to
  represent the whole event

The background image used for each poster depends on the folder type:

| Folder type | Background sources tried in order |
|-------------|----------------------------------|
| Artist folder | DJ artwork from 1001Tracklists, then fanart.tv, then gradient |
| Festival folder | Curated festival logo, then gradient |
| Year folder | Gradient only |

If no background image is available, a color gradient is generated from the available
metadata. Curated festival logos can be added to improve festival folder posters. See
[audit-logos](audit-logos.md) to check which festivals have logos.

Both the per-video poster and the folder poster fall back to a color gradient if no
background image is available, so every recording and every folder gets a poster regardless
of whether a thumbnail exists. Use `--regenerate` to rebuild existing posters.

### nfo: metadata files

Writes an NFO file alongside each video. An NFO file is a small XML file that media
players like Kodi, Plex, and Jellyfin read to display the recording's title, artist,
genre, year, and artwork references. CrateDigger follows the Kodi musicvideo NFO format.

The NFO includes:

- Title, artist(s), album, year, runtime
- Genre (from 1001Tracklists if identified; otherwise from `nfo_settings` in your config)
- Stage or venue
- References to the thumbnail, poster, and fanart images

**Skipped if:** `{name}.nfo` already exists (unless `--regenerate`).

### tags: MKV metadata tags

Writes structured metadata tags into each MKV file at the file level. These are the
tags that general media players and tag editors read, covering artist, title, date, and
description. CrateDigger sets `SYNOPSIS` to a generated description and explicitly
clears the `DESCRIPTION` tag, which yt-dlp often fills with the full video description
from YouTube.

**Only applies to MKV and WEBM files.** Other formats are skipped.

### chapter_artist_mbids: per-track artist IDs

Resolves each performer named in the chapter tags to a MusicBrainz ID (a permanent
unique identifier from [musicbrainz.org](https://musicbrainz.org)), then writes those
IDs back into the chapter tags.

This only runs on files that were processed by [`identify`](identify.md), since that
is what embeds the per-chapter performer names.

**Lookup order for each artist name:**

1. Your override file (`~/CrateDigger/artist_mbids.json` on Linux, `Documents\CrateDigger\artist_mbids.json` on Windows): manually curated, never
   expires, never auto-written by CrateDigger
2. Auto cache (in `~/.cache/CrateDigger/` on Linux, `%LOCALAPPDATA%\CrateDigger\Cache\` on Windows): populated automatically by MusicBrainz
   searches, expires after 90 days by default
3. Live MusicBrainz search: result is saved to the auto cache

If an artist cannot be resolved, a WARNING is logged and an empty slot is left in the
tag so the alignment with performer names is preserved.

**If artists are not resolving correctly**, add them to the override file manually:

```json
{
    "Afrojack": "3abb6f9f-5b6a-4f1f-8a2d-1111111111aa",
    "Oliver Heldens": "6e7dde91-4c02-47ea-a2b4-2222222222bb"
}
```

Then rerun to apply:

```bash
cratedigger enrich ~/Music/Library/ --only chapter_artist_mbids
```

No `--regenerate` needed. CrateDigger compares the newly resolved IDs against what is
already stored and writes the update automatically when they differ.

### album_artist_mbids: set-level artist IDs

The same lookup process as `chapter_artist_mbids`, but applied at the file level rather
than per chapter. Resolves the full list of artists for the set and writes their
MusicBrainz IDs as a set-level tag.

The same override file is used for both operations (`~/CrateDigger/artist_mbids.json` on Linux, `Documents\CrateDigger\artist_mbids.json` on Windows).
An entry in that file fixes the ID everywhere, per-chapter and album-level alike.

## What files change

For each video, `enrich` may create or update:

| File | Created by |
|------|-----------|
| `{name}-thumb.jpg` | `art` |
| `{name}-fanart.jpg` | `art` (copy of thumb) |
| `{name}-poster.jpg` | `posters` |
| `{name}.nfo` | `nfo` |
| `folder.jpg` | `posters` (one per folder; generated even without a thumbnail, using gradient fallback) |

Artist artwork is cached to `~/.cache/CrateDigger/artists/{artist}/` (Linux) or `%LOCALAPPDATA%\CrateDigger\Cache\artists\{artist}\` (Windows) and reused across runs.
MKV tag changes (`tags`, `chapter_artist_mbids`, `album_artist_mbids`) are written
directly into the MKV file's metadata section. The video and audio streams are not touched.

## Common examples

**Enrich an entire library:**

```bash
cratedigger enrich ~/Music/Library/
```

**Regenerate all posters (for example, after adding a festival logo):**

```bash
cratedigger enrich ~/Music/Library/ --only posters --regenerate
```

**Update only NFO files:**

```bash
cratedigger enrich ~/Music/Library/ --only nfo --regenerate
```

**Fix unresolved MusicBrainz IDs after updating the override file:**

```bash
cratedigger enrich ~/Music/Library/ --only chapter_artist_mbids,album_artist_mbids
```

**Enrich and notify Kodi when done:**

```bash
cratedigger enrich ~/Music/Library/ --kodi-sync
```

## Console output

Each file gets a two-line verdict block showing what happened:

```
done  [3/12] Afrojack - Ultra Miami 2024.mkv  .  4.2s
             nfo, art, posters
```

The second line lists the operations that ran. If everything was already
up to date, it shows `all up to date` instead. Errors are called out
inline:

```
error  [5/12] Eric Prydz - Creamfields 2023.mkv  .  1.1s
              nfo; posters error: no thumbnail found
```

Use `--verbose` to see a per-operation breakdown under each verdict,
showing which operations ran, were skipped, or failed and why.

After all files are processed, a summary panel shows total file counts
(done, up to date, errors), a per-operation breakdown, any errors
encountered, and total elapsed time.

## Common problems

**"not a CrateDigger library"**

The folder you pointed `enrich` at has no `.cratedigger/` marker. Run
[`organize`](organize.md) on your library first to create it.

**Posters are not generated for some files**

The poster operation requires `{name}-thumb.jpg` to exist first. Run `enrich` without
`--only` (so `art` runs before `posters`), or run `--only art` first, then `--only posters`.

**Artist artwork from fanart.tv is missing**

The artist may not have a MusicBrainz ID resolved yet. Run `--only chapter_artist_mbids`
first, then rerun the full enrich. See the [FAQ](../faq.md) for more fanart troubleshooting.

## Re-running enrich after identify

If you re-run [`identify`](identify.md) on your library to pick up updated tracklist data
from the 1001Tracklists community, run `enrich` again afterward to apply the new metadata
to your NFO files, MKV tags, and posters:

```bash
cratedigger enrich ~/Music/Library/ --regenerate
```

Updated artist names, genres, stage information, and other tracklist fields are picked up
from the newly embedded tags.

## Optional: curated festival logos

Festival folder posters use a curated logo if one is available, and fall back to a color
gradient if not. Adding a logo for a festival upgrades its folder poster from a plain
gradient to a logo-based design. You can add logos at any time and then re-run to rebuild:

```bash
cratedigger enrich ~/Music/Library/ --only posters --regenerate
```

Use [`audit-logos`](audit-logos.md) to see which festivals in your library have logos
and which are missing them.

## Related

- [Kodi integration](../kodi-integration.md): automatic Kodi refresh after enrich
- [Tag reference](../tag-reference.md): full list of tags written by enrich and identify
