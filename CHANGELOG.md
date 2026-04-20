# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `--version` flag on the CLI.

## [0.12.7] - 2026-04-15

### Changed

- `identify` now emits one padded-badge verdict line per file (`done`, `updated`, `up-to-date`, `skipped`, `error`) with a per-file elapsed time, plus a total `Elapsed` row in the summary panel. Previous runs mixed several ad-hoc status phrases into the scrollback; the new shape is consistent and grep-friendly.
- A transient spinner now shows the current step (sign-in, search, fetch, embed, throttle) during blocking operations in a live terminal. The spinner auto-disables when stdout is piped, or when running with `--quiet`, `--verbose`, or `--debug`, so captured logs and CI output stay clean.
- If you had shell scripts grepping old phrases like `Embedded N chapters` or `Up to date`, update them to key off the new verdict badges (`done`, `updated`, `up-to-date`, `skipped`, `error`). The new shape is documented at `docs/commands/identify.md` (section: "What you see when it runs").

### Added

- Summary panel now lists errored files in the `Unmatched` section alongside skipped files, so failures are not lost between runs.

### Fixed

- Interactive selection prompt no longer collides with the next file's output. The `Select (1-N, or 0):` line and the following file's verdict used to be stitched onto one visual line.

## [0.12.0] - 2026-04-14

### Changed

- `organize` now picks the action automatically from the source/output relationship: atomic rename when you organize an existing library (source == output, or source inside output), copy when importing into a separate library, `--move` still opts into moving on import. The old copy-default when `source == output` silently duplicated files; the new behaviour re-organizes in place without duplication.
- Confirmation prompt for re-organizing inside an existing library now clarifies that files will be renamed to match the layout.
- In-place re-organize now follows `folder.jpg` / `fanart.jpg` across a layout or alias change, and cleans up emptied source folders — previously these were orphaned and only the `--move` path ran cleanup.

### Removed

- `--rename-only` flag: the new smart default already picks rename for in-place organize, and `--rename-only` added nothing beyond that intent. Scripts using `--rename-only` will get a Typer error; drop the flag.

### Fixed

- `organize` is now idempotent for identified files: the filename-only `set_title` / `title` fields are no longer parsed from the filename when any `CRATEDIGGER_1001TL_*` tag is present, so the rendered name converges after one pass and subsequent runs skip cleanly.

## [0.9.1] - 2026-04-05

### Added

- NFO files now emit multiple `<artist>` elements for B2B/collaborative sets
- Individual artist `<tag>` elements in NFOs for Kodi smart playlist filtering
- DJ group member expansion in NFO tags via DJ cache reverse-lookup (e.g. a Gaia set tags Armin van Buuren)
- Curated MKV DESCRIPTION tag replacing raw yt-dlp YouTube descriptions with structured metadata (artist, stage, festival, country, source type, edition)
- New MKV tags `CRATEDIGGER_1001TL_COUNTRY` and `CRATEDIGGER_1001TL_SOURCE_TYPE` embedded during chapter writing
- `MediaFile.artists` field carrying the full resolved artist list from pipe-separated 1001TL tag
- `DjCache.derive_group_members()` for group-to-member reverse lookups

## [0.9.0] - 2026-04-03

First public release.

### Added

- Intelligent content classification: automatic detection of festival sets vs concert films
- File organization with four built-in folder layouts (artist_flat, festival_flat, artist_nested, festival_nested)
- Smart filename templates with Sonarr-style collapsing tokens for optional fields
- 1001Tracklists integration: search, match, and embed tracklist metadata and chapter markers
- DJ artwork extraction from 1001Tracklists profiles
- MediaInfo and ffprobe-based metadata extraction and analysis
- Cover art extraction from video files with frame sampling fallback
- fanart.tv integration for HD ClearLOGOs and artist fanart via MusicBrainz lookup
- Professional poster generation: set posters (artist photo + metadata) and album posters (festival logo + gradient)
- Kodi NFO file generation (musicvideo XML standard) with genre, festival, and content-type tags
- Kodi JSON-RPC sync with selective library refresh and automatic path mapping
- MKV tag embedding with safe extract-merge-write workflow
- Festival database with 30+ pre-configured festivals, edition support, and color branding
- Artist database with alias resolution and group definitions
- Configurable at user level (~/.cratedigger/config.json) and library level
- TTL-based caching for API lookups (MusicBrainz, fanart.tv, 1001Tracklists)
- Rich terminal UI with progress reporting, colored status indicators, and spinners
- Audit command for checking festival logo coverage
