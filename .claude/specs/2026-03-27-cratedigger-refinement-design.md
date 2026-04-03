# CrateDigger Refinement Design

**Date:** 2026-03-27
**Status:** Draft
**Scope:** CLI UX overhaul, pipeline architecture, cross-platform support, NFO improvements

## Background

CrateDigger is a festival set and concert recording library manager. It scans media files, extracts metadata from multiple sources (1001Tracklists tags, embedded media tags, filenames, parent directories), classifies content, organizes files into a library structure, and enriches them with Kodi NFO files, cover art, posters, and Plex tags.

The current tool works but has usability problems:
- The `execute` command is all-or-nothing — moving files is coupled to enrichment
- No way to enrich files in place without moving them (standalone commands exist but feel bolted on)
- No live progress — output dumps at the end
- Config is a single monolithic JSON mixing tool settings, festival knowledge, and library preferences
- Hardcoded Windows paths for tools and fonts make it non-portable
- The command structure maps to technical operations, not user workflows

This design addresses all of these issues.

## Goals

1. Commands map to what users want to accomplish, not technical operations
2. Operations are composable and independent — mix and match freely
3. Smart gap detection — only do work that's needed
4. Live progress output as files are processed
5. Cross-platform support (Windows, macOS, Linux) for community distribution
6. Richer Kodi NFO metadata following the official spec
7. Simplified, layered configuration with sensible defaults

## Non-Goals

- yt-dlp integration (future, but design should not preclude it)
- Poster text readability refinement (separate design pass)
- Packaging and distribution strategy (separate decision)
- Renaming the package/CLI command (deferred)

---

## 1. Command Structure

Four top-level commands mapped to user workflows:

```
cratedigger scan <path>                  # Preview what would happen (dry run)
cratedigger organize <path>              # Move/copy files into library structure
cratedigger enrich <path>                # Add metadata artifacts to files in place
cratedigger chapters <path>              # Add 1001Tracklists chapters
```

### `scan`

Dry run. Scans, analyzes, classifies, plans — shows what `organize` would do without touching anything. Live output as each file is analyzed.

### `organize`

Moves, copies, or renames files into the target library structure.

Flags:
- `--copy` — copy instead of move
- `--rename-only` — rename in place
- `--enrich` — after organizing, run full enrichment on results
- `-o <output>` — target directory (default: library root if detected, else same as input)
- `--layout <name>` — folder structure to use

### `enrich`

Runs enrichment operations on files where they already are. Smart gap-filling by default: detects what's already present and only generates what's missing.

Flags:
- No flags needed for "do everything that's missing"
- `--only nfo,art,posters,tags,chapters` — restrict to specific operations
- `--force` — regenerate even if artifacts already exist

Works on a single file or a directory. When `chapters` is included, runs in batch/auto mode (uses stored URLs, auto-picks top results for files without).

### `chapters`

Three modes:

- **Interactive mode** (default): For files with stored tracklist URLs, prompts Y/S/R (use/skip/re-search). For files without, shows the scored result list with keyword highlighting for manual selection.
- **Batch mode** (`--auto`): For files with stored URLs, reuses them directly. For files without, auto-picks the top search result. No prompts. Good for automation or "just do it for my whole library."
- **Single tracklist** (`-t <url|id|query>`): Specify exactly which tracklist to use.

Additional flags:
- `--preview` — show chapters without embedding
- `--force` — ignore stored URLs, force fresh search (note: on `enrich`, `--force` means regenerate existing artifacts; on `chapters`, it means ignore stored URLs)
- `--delay <seconds>` — rate limiting between files (default: 5)

### No-argument help

Running `cratedigger` with no arguments shows workflow examples:

```
CrateDigger - Festival set & concert library manager

Common workflows:
  cratedigger scan ./downloads          Preview what would happen (dry run)
  cratedigger organize ./downloads      Organize files into library structure
  cratedigger enrich ./library          Add art, posters, tags to existing files
  cratedigger chapters ./file.mkv       Add 1001Tracklists chapters

Run 'cratedigger <command> --help' for details on each command.
```

---

## 2. Pipeline Architecture

Every action is an **operation** — a self-contained unit that knows how to check if its work is needed and how to execute it.

```
Scanner ──> Analyzer ──> Planner ──> Runner
(find files) (metadata)  (what to do)  (do it, with live progress)
                              |              |
                         Operations     Per-file status
```

### Operations

Each operation is independent and composable:

| Operation | What it does | Gap detection |
|-----------|-------------|---------------|
| `organize` | Move/copy/rename to target path | File not at target location |
| `nfo` | Generate Kodi NFO XML | No `.nfo` beside the video |
| `art` | Extract/sample cover art | No `*-thumb.jpg` beside the video |
| `poster` | Generate set poster | No `*-poster.jpg` (requires thumb) |
| `tags` | Embed Plex tags via mkvpropedit | Tags not present in MKV |
| `chapters` | Embed 1001Tracklists chapters | No chapters in MKV, or stored URL without timestamps |

### Command-to-operation mapping

- `scan` -> Scanner + Analyzer + Planner (report only, no Runner)
- `organize` -> Scanner + Analyzer + Planner + Runner with `[organize]`
- `organize --enrich` -> same + Runner gets `[organize, nfo, art, poster, tags]`
- `enrich` -> Scanner + Analyzer + Runner with `[nfo, art, poster, tags]`
- `enrich --only chapters` -> Scanner + Analyzer + Runner with `[chapters]`
- `chapters` -> own auth/selection flow, uses Runner for embedding

### Runner behavior

The Runner processes files sequentially:
1. For each file, runs planned operations in order
2. Checks gap detection before each operation (skips if already done)
3. Emits live progress as each file/operation completes
4. Collects results for the final summary

---

## 3. Library Root Detection

When `organize` first runs on a directory, it creates a `.cratedigger/` marker directory at that level. This serves two purposes:

1. **Root detection**: When running `organize` or `enrich` on a subfolder (e.g., `d:\concerts\Martin Garrix\`), the tool walks up looking for `.cratedigger/`. If found at `d:\concerts\`, that's the library root. Files are placed relative to the root, not the input path. Only the input subfolder is scanned.

2. **Library-level config**: `.cratedigger/config.json` stores library-specific settings (layout choice, overrides). See Configuration section.

If no marker is found, the input path is treated as both scan root and output root (current behavior).

---

## 4. Configuration

Three layers, most specific wins:

### Layer 1: Built-in defaults (bundled with package)

Never edited by users. Contains:
- Media extensions (video and audio)
- Fallback values (Unknown Artist, _Needs Review, etc.)
- Default filename and folder templates
- Base festival aliases (Tomorrowland, EDC, Ultra, AMF, etc.)
- Tracklist search aliases (amf -> Amsterdam Music Festival, etc.)
- Default NFO genre settings

### Layer 2: User config (`~/.cratedigger/config.json`)

Personal preferences, created by user:
- Tool path overrides (for non-standard installs)
- 1001Tracklists credentials (email, password)
- Personal festival aliases and content type rules
- NFO settings (genre defaults, custom tags)
- Any built-in defaults the user wants to override

### Layer 3: Library config (`.cratedigger/config.json` at library root)

Per-library settings:
- Layout choice for this library
- Library-specific overrides

### Merge order

`built-in < user < library` — most specific wins. Deep merge on objects, replace on scalars.

### Credentials

1001Tracklists credentials are stored in the user config layer:

```json
{
  "tracklists": {
    "email": "user@example.com",
    "password": "...",
    "delay_seconds": 5,
    "chapter_language": "eng"
  }
}
```

Environment variables (`TRACKLISTS_EMAIL`, `TRACKLISTS_PASSWORD`) remain supported as an override for CI/automation use cases.

---

## 5. Layouts

Four layout options for folder structure:

| Layout | Folder template (festival sets) | Folder template (concerts) | Best for |
|--------|-------------------------------|---------------------------|----------|
| `artist_flat` **(default)** | `{artist}/` | `{artist}/` | "I follow artists" |
| `festival_flat` | `{festival}/` | `{artist}/` | "I follow festivals" |
| `artist_nested` | `{artist}/{festival}/{year}/` | `{artist}/{year} - {title}/` | Deep organization |
| `festival_nested` | `{festival}/{year}/{artist}/` | `{artist}/{year} - {title}/` | Festival-centric deep org |

Concert films always fall back to `{artist}/` in flat layouts since they don't have a festival to group by.

Filename templates remain as today:
- Festival sets: `{year} - {festival} - {artist}`
- Concert films: `{artist} - {title}`

The flat layouts are new. `artist_first` and `festival_first` are renamed to `artist_nested` and `festival_nested` for clarity.

---

## 6. NFO / Kodi Metadata

Based on the official Kodi musicvideo NFO specification (https://kodi.wiki/view/NFO_files/Music_videos).

### Field mapping

| Tag | Required | Multiple | What we populate |
|-----|----------|----------|-----------------|
| `title` | **yes** | no | Clean title: artist name (sets) or descriptive title (concerts) |
| `artist` | **yes** | yes | Artist name(s) |
| `album` | no | no | Festival + Year for grouping (e.g., "Tomorrowland 2024") |
| `premiered` | no | no | Date as YYYY-MM-DD |
| `genre` | no | yes | Configurable per content type (default: "Electronic" / "Live") |
| `tag` | no | yes | Content type, festival name, location — enables smart playlists |
| `studio` | no | yes | Stage name (festival sets) or venue (concerts) |
| `director` | no | yes | If available (concerts only), otherwise omit |
| `plot` | no | no | Rich text: stage, location, edition info, set description |
| `runtime` | no | no | Minutes |
| `thumb` | no | yes | `-thumb.jpg` and `-poster.jpg` with `aspect` attributes |
| `dateadded` | no | no | Timestamp when file was processed |
| `playcount` | no | no | Omit (let Kodi manage) |
| `userrating` | no | no | Omit (user sets in Kodi) |
| `fileinfo` | no | no | Video: codec, aspect, width, height, durationinseconds. Audio: codec, language, channels |

### Key decisions

- **`year` tag removed** — deprecated since Kodi v17, removed in v20. Use `premiered` only.
- **`title`** = clean descriptor, not the full filename with year/festival baked in.
- **`album`** = grouping key. Festival + year (e.g., "AMF 2024") so Kodi groups all sets from the same edition.
- **`tag`** = power feature for Kodi smart playlists. Multiple tags per file: `festival_set`, `Tomorrowland`, `Belgium`, etc.
- **`studio`** = stage name, surfaced in the Kodi UI.
- **`plot`** = rich description with stage, location, edition info. No 1001Tracklists URL (stored in MKV tags for the chapters workflow, not useful in Kodi UI).
- **`actor`** with artist name/photo — parked for future (requires artist image source).

---

## 7. Live Progress Output

Output streams as files are processed:

```
CrateDigger - Organize
════════════════════════════════════════════════════
Source:  D:\Downloads\sets
Output:  D:\Concerts
Layout:  artist_flat
Tools:   mediainfo, mkvpropedit, mkvextract
════════════════════════════════════════════════════

Scanning... 12 files found.

 [1/12] 2024 - AMF - Martin Garrix.mkv
        -> Martin Garrix/
        v moved  v nfo  v art  v poster  v tags

 [2/12] Armin van Buuren @ Tomorrowland 2023.mkv
        -> Armin van Buuren/
        v moved  v nfo  v art  skip poster (exists)  v tags

 [3/12] Unknown_set_1080p.mkv
        -> _Needs Review/
        v moved  v nfo  ! art (no embedded, no frames)

════════════════════════════════════════════════════
Done: 10 moved, 2 skipped | NFO: 10 | Art: 9 | Posters: 8 | Tags: 10
Log:  D:\Concerts\cratedigger_20260327_143022.csv
════════════════════════════════════════════════════
```

### Principles

- Each file prints as it's processed — no waiting for the end
- Operation status inline per file — see what happened at a glance
- Skip reasons shown: `(exists)`, `(no tool)`, `(no embedded, no frames)`
- Clean aggregate summary at the end
- `--quiet` suppresses per-file output, keeps summary only
- `--verbose` adds metadata details (detected artist, festival, source, etc.)

---

## 8. Album Posters

Two levels of posters:

### Set poster (per video file)

What exists today. `{stem}-poster.jpg` beside the video. Generated from the video's embedded cover art or sampled frame.

### Album poster (per album grouping folder)

`folder.jpg` at the album folder level. Kodi uses this for folder/album views.

Uses the existing clean poster generation (no thumbnail, text/design only). This is the right fit for album level — it represents the festival edition or artist without being tied to a specific set's video frame.

- **Flat layouts** (`artist_flat`, `festival_flat`): `folder.jpg` at the artist or festival folder. Text shows the artist name or festival name.
- **Nested layouts**: `folder.jpg` at the deepest grouping folder. Text shows the festival + year or artist + festival context.

The clean poster is generated during the `poster` operation's gap detection: if a folder has video files but no `folder.jpg`, generate one.

---

## 9. Cross-Platform

### Tool discovery

Priority order:
1. System PATH (`mediainfo`, `ffprobe`, `mkvpropedit`, `mkvextract`)
2. User config `tool_paths` overrides
3. If not found, clear error with platform-specific install hint:
   - macOS: `brew install mediainfo mkvtoolnix ffmpeg`
   - Linux: `apt install mediainfo mkvtoolnix ffmpeg`
   - Windows: `winget install mediainfo mkvtoolnix ffmpeg`

Hardcoded Windows fallback paths in `metadata.py` are removed.

### Fonts

- Bundle a free font with the package (Inter or Noto Sans) for poster generation
- User config override for custom fonts
- Drop hardcoded `C:\Windows\Fonts\segoeui*.ttf` paths

### Filenames

- Keep Windows illegal character rules (`<>:"/\|?*` + control chars) as the baseline on all platforms
- Files created on any platform will work everywhere (important for NAS/shared libraries)

### Paths

- `pathlib.Path` throughout (already mostly done)
- `~/.cratedigger/` for user config (expands correctly on all platforms)
- Drop all hardcoded Windows tool paths

---

## 10. Future Considerations

These are explicitly out of scope but the design should not preclude them:

- **yt-dlp integration**: A future `download` or `fetch` command that downloads sets based on criteria. The pipeline architecture supports adding new operations.
- **Poster readability**: Text sizing and contrast for TV viewing in Kodi. Separate design pass.
- **Artist images**: Could source from MusicBrainz or Discogs for the `actor` NFO field.
- **Multi-artist sets**: B2B sets (e.g., "Dimitri Vegas & Like Mike") need special handling in parsing and NFO generation.
- **Web UI**: A browser-based companion for interactive tracklist selection (alternative to terminal UI).
