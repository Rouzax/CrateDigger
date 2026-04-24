# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.14.1] - 2026-04-24

### Changed

- The rotating log file introduced in 0.14.0 now captures a complete post-mortem trail. Every subprocess invocation (mediainfo, ffprobe, mkvextract, mkvpropedit) logs its command line and, on non-zero exit, a tail of stderr. Silent retry loops in the 1001Tracklists client (429 rate limit, 502/503/504 transient, network errors) and the fanart.tv client now log each retry with reason and wait duration. The `enrich` tag-write step logs a one-line diff (`+added -removed ~changed`) per file. Previously-silent failure branches in `nfo`, `executor`, `parsers`, `frame_sampler`, and `embed_tags` now leave a WARNING or DEBUG trace. The update-check network and cache paths log their skip or failure reasons. No behavior changes; console output is unchanged.

## [0.14.0] - 2026-04-21

Companion release to [TrackSplit 0.7.0](https://github.com/Rouzax/TrackSplit/releases/tag/v0.7.0), which implements the matching storage layout on the TrackSplit side.

### Added

- `CRATEDIGGER_DATA_DIR` env var now overrides the default data directory (must point at an existing directory). Matches TrackSplit's discovery so both tools agree when set.
- Rotating log file written on every startup: `~/.local/state/CrateDigger/log/cratedigger.log` on Linux, `~/Library/Logs/CrateDigger/cratedigger.log` on macOS, `$env:LOCALAPPDATA\CrateDigger\Logs\cratedigger.log` on Windows. Five rotating files, 5 MB each. Console output is unchanged.
- Startup WARNING on every run while legacy paths remain from before 0.14.0 (`~/.cratedigger/` or `~/.1001tl-cookies.json`). CrateDigger does not migrate files automatically; the warning tells you to move or delete them.
- Startup WARNING on every run while a library still contains a pre-0.14.0 `{library}/.cratedigger/config.json`. The file is no longer read; copy its `default_layout` value into `config.toml` (same directory) or delete it.

### Changed

- Config file is now TOML (`config.toml`) instead of JSON (`config.json`).
- Library-local override at `{library}/.cratedigger/config.toml` is now TOML too. `organize` writes `config.toml` into the library marker folder (previously `config.json`).
- Config and curated data files (`festivals.json`, `artists.json`, `artist_mbids.json`) now live in a visible user folder: `~/CrateDigger/` on Linux and macOS, `Documents\CrateDigger\` on Windows. Previously everything was mixed into `~/.cratedigger/`.
- User-global festival logos moved from `~/.cratedigger/festivals/` to `~/CrateDigger/festivals/` (Linux) or `Documents\CrateDigger\festivals\` (Windows). Library-local `{library}/.cratedigger/festivals/` is unchanged.
- Caches (`mbid_cache.json`, `dj_cache.json`, `source_cache.json`, `update-check.json`, artist artwork) moved to the platform cache directory: `~/.cache/CrateDigger/` on Linux, `~/Library/Caches/CrateDigger/` on macOS, `$env:LOCALAPPDATA\CrateDigger\Cache\` on Windows.
- 1001TL session cookies moved from the rogue `~/.1001tl-cookies.json` in `$HOME` to `~/.local/state/CrateDigger/1001tl-cookies.json` on Linux, `~/Library/Application Support/CrateDigger/1001tl-cookies.json` on macOS, `$env:LOCALAPPDATA\CrateDigger\State\1001tl-cookies.json` on Windows.
- `--check` output updated to show new file locations.
- Warn when a curated data file (`festivals.json`, `artists.json`, or `artist_mbids.json`) exists but fails to parse, instead of silently falling back to defaults. The next candidate path is still tried; if all candidates fail, defaults are used and a WARNING per failed file is emitted.

### Removed

- `~/.cratedigger/` user-global grab-bag folder. The library-local `{library}/.cratedigger/` marker directory created by `organize` is unchanged.
- JSON config loading path. Only TOML is supported from 0.14.0 onward.

## [0.13.4] - 2026-04-21

### Added

- Scraping canary: a structural health check that runs after every 1001Tracklists page fetch and logs a `WARNING` naming the missing selectors when the page is shaped in a way our parsers would silently fail on. Covers the four page types the scraper reads (tracklist detail, search results, DJ profile, source info). Previously, a site HTML change would cause parsers to return empty lists or dicts with no user-visible signal, leading to missing genres, missing event dates, wrong or absent DJ artwork, and empty NFOs; the canary surfaces this the first time it happens so the problem is visible while it is still fresh. One WARNING per unique (page type, missing selector set) pair is emitted per run, so a bulk operation that hits the same breakage across many files does not spam the log; subsequent identical failures log at `DEBUG` instead.

### Changed

- The 1001Tracklists scraping code has been migrated from regex parsing to BeautifulSoup across the board (`_extract_genres`, `_extract_dj_slugs`, `_parse_h1_structure` anchor extraction, `_parse_dj_profile`, `_parse_search_results`, and the inline parser in `fetch_source_info`). This makes parsing robust to cosmetic HTML changes on 1001tracklists.com that the old regex approach was silently fragile to: attribute reordering (`<meta content="X" itemprop="genre">` vs the other order), quote-style variations (single vs double-quoted hrefs), intervening attributes on tags, and false-positive matches against strings embedded in script blocks. No user-visible behavior change in the happy path; existing tags, chapters, artwork, and NFOs still populate from the same fields.
- The tracklist detail page is now parsed into BeautifulSoup once per fetch and the soup is shared across all four downstream parsers (`_parse_tracks`, `_parse_h1_structure`, `_extract_genres`, `_extract_dj_slugs`), replacing three redundant full-page parses per export.

### Removed

- The DEBUG-only `site format may have changed` heuristic in `search()` has been removed. The canary replaces it with a `WARNING` that names the exact missing selector and is visible without `--verbose`.

## [0.13.3] - 2026-04-20

### Added

- `--check` flag on the CLI. Verifies that required external tools (mediainfo, ffprobe, mkvextract, mkvpropedit, mkvmerge), config files, API credentials, and Python packages are present and reachable. Prints a grouped report with per-item status markers and a summary line. Exits non-zero if any required check fails; warnings for optional items do not affect the exit code. Use after a fresh install, after updating configuration, or in CI to validate the environment before a scheduled run.

### Changed

- The release workflow is now triggered manually via `gh workflow run release.yml -f version=X.Y.Z` (or the GitHub UI), replacing the prior commit-message-matched trigger. The workflow still validates `pyproject.toml` and `CHANGELOG.md`, builds, tags, and publishes. The local `scripts/release.sh`, `scripts/git-hooks/pre-push`, and `scripts/setup-hooks.sh` have been removed; they existed to construct and gate a very specific commit-message format that the workflow no longer relies on.

### Fixed

- `identify` now writes `CRATEDIGGER_1001TL_DATE` in more cases. The event date embedded in the h1 of a 1001Tracklists page (for example, the trailing `2025-10-24` in `Martin Garrix & Alesso @ Red Rocks Amphitheatre, United States 2025-10-24`) was being stripped out during parsing but never captured, so files whose search result lacked a "tracklist date" field ended up with no event-date tag. The h1 date now surfaces as a fallback, so downstream commands stop treating the YouTube publish date as the event date. Affected files self-heal on the next `identify` run.
- `identify` summary "Metadata tagged" count now reflects all successfully tagged files, not only those linked to a festival. Previously, standalone club sets, concerts, and other non-festival events were processed and tagged but excluded from the count, so the top-line number was smaller than the total processed even when every file had tracklist metadata embedded. The festival breakdown still only lists festival-linked files.

## [0.13.2] - 2026-04-20

### Fixed

- `enrich` no longer rewrites global tags on every run when no values have changed. `mkvpropedit` strips the `<Targets>` element when writing a `TargetTypeValue=50` block, and a parser bug then treated the resulting Targets-less block as empty, causing `embed_tags` to rewrite the same values on every run.
- `enrich` now folds accumulated duplicate global Tag blocks into one on the next touch. Files affected by the prior re-write loop could carry many copies of `ARTIST`, `TITLE`, `DATE_RELEASED`, and `SYNOPSIS`; these self-heal on the next `enrich` run.

## [0.13.1] - 2026-04-20

### Added

- `--version` flag on the CLI.
- scripts/git-hooks/pre-push hook that gates 'chore: release' commits behind an interactive prompt.
- Startup update notification: prints a notice when a newer GitHub Release is available. Silent in non-interactive contexts; suppressible with CRATEDIGGER_NO_UPDATE_CHECK=1.

## [0.13.0] - 2026-04-19

### Added

- `organize` and `enrich` now emit a two-line verdict block per file: a badge line (`moved`, `copied`, `renamed`, `preview`, `done`, `updated`, `skipped`, `error`) followed by a context detail line showing what changed (destination path, operations applied, elapsed time). The single summary panel at the end breaks down counts by outcome and lists any errored files. This brings `organize` and `enrich` in line with the verdict shape introduced for `identify` in 0.12.7.
- Running `organize --enrich` now emits two verdict blocks per file: one for the file-move or rename, and a second for the enrichment operations. Both summaries are printed side by side at the end so you can see organize and enrich outcomes separately in one run.
- Dry-run mode (`--dry-run`) for `organize` now uses a distinct `preview` badge, making it unambiguous that no files were modified.
- A transient spinner is now shown during `organize` and `enrich` operations in a live terminal. It disables automatically when stdout is piped, or when `--quiet`, `--verbose`, or `--debug` is active.
- New MKV tag `CRATEDIGGER_1001TL_LOCATION` is written by `identify` when the 1001Tracklists page heading carries a plain-text location (for example, "Alexandra Palace London") and no linked festival, venue, or conference source is present. The tag is cleared automatically on re-identify when a more authoritative linked source later appears. `MediaFile.location` exposes the value to downstream commands.
- The `CRATEDIGGER_1001TL_LOCATION` value is now used as a lowest-priority fallback in the embedded MKV `DESCRIPTION` synopsis line, after festival name and venue. Files with no structured venue still receive a readable location line.
- 1001Tracklists "Club" source type is now recognized as a venue. Previously, club entries did not write `CRATEDIGGER_1001TL_VENUE`, did not contribute to country derivation, and left `SOURCE_TYPE` unset. They are now treated consistently with Event Location entries.
- Set posters for concert files (no linked festival) now use the venue or freeform location as the large accent headline instead of the full file title. This avoids redundant or over-long headlines such as "FRED AGAIN.. @ USB002" when the artist name is already shown above. File title remains as a last-resort fallback when no location data is available.

### Changed

- `enrich` summary panel now breaks down the operations applied across all files (poster rebuild, NFO write, tag embed, and so on) in addition to the per-file outcome counts. Operation labels use their display names throughout.
- Kodi sync output now uses `StepProgress` for individual steps and a `library_sync_summary_line` for the final result, matching the consistent progress style used by other commands.
- `CRATEDIGGER_1001TL_COUNTRY` is now populated whenever the page heading carries a recognised country name, including pages with no linked source. Previously the country was only written when no linked source was present.

### Fixed

- Set poster accent headline no longer shows a duplicate venue name in the subline when the venue filled the festival slot via the fallback chain. The subline is suppressed in that case so the venue name appears only once.
- Venue and location values that fill the festival slot are now passed through the festival alias resolver, so user-configured aliases (for example, "Red Rocks Amphitheatre" mapped to "Red Rocks") apply consistently regardless of which tag the value originated from.
- `fanart.tv` MBID lookup warnings are no longer emitted per-file. They are demoted to info level and aggregated into a single count in the summary panel, reducing noise when many files share the same unresolved MBID.

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
- Configurable at user level (config.toml) and library level
- TTL-based caching for API lookups (MusicBrainz, fanart.tv, 1001Tracklists)
- Rich terminal UI with progress reporting, colored status indicators, and spinners
- Audit command for checking festival logo coverage
