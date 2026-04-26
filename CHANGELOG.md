# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.15.0] - 2026-04-26

Place routing replaces festival-only routing with a full `festival → venue → location → artist` chain. Sets that previously had no linked festival were silently routed by artist; they now file under their venue or location name. All festival-specific surface (config keys, template tokens, layout names, curated asset paths) is superseded by place-equivalent names and will be removed at 1.0.0.

### Migration

No action required for 0.15.0. Existing libraries and config files keep working without any changes. When deprecated names are detected, CrateDigger emits one WARNING per process run naming the old key and the replacement. To migrate: rename `festivals.json` to `places.json`, update layout names if you use `festival_flat` or `festival_nested` to `place_flat` or `place_nested`, and rename `.cratedigger/festivals/` to `.cratedigger/places/`. All of these steps are optional until 1.0.0.

On first run after upgrade, CrateDigger automatically copies your existing `festivals.json` and user-global `.cratedigger/festivals/<name>/` curated logo directories to the new place-named locations (`places.json` and `.cratedigger/places/<name>/`). The legacy paths stay in place so you can roll back to 0.14.x without losing data; delete them once you have verified the new locations work.

If you keep curated logos under a library-local `<library>/.cratedigger/festivals/` directory, that location is NOT auto-migrated. Rename it to `<library>/.cratedigger/places/` to keep those logos picked up.

### Added

- `places.json` curated registry replaces `festivals.json` as the primary file. It uses the same schema (aliases, color, editions, and so on) and extends the domain to cover festivals, clubs, permanent venues, residencies, and any other named branded entity that hosts DJ sets. `festivals.json` is still loaded as a fallback while the deprecation window is open.
- `{place}` template token for routing. The token resolves to the canonical name derived from `mf.place` and works identically to `{festival}` for festival-routed sets. For venue- or location-routed sets it carries the canonical venue or location name.
- `place_flat` and `place_nested` layouts replace `festival_flat` and `festival_nested`. They behave identically and accept the same sub-options; only the key name changes.
- `place_background_priority` config setting replaces `festival_background_priority`. Controls the order of artwork sources used for poster backgrounds when routing by place.
- `unknown_place` fallback config value replaces `unknown_festival`. Used as the folder name when a set cannot be matched to any known place.
- `mf.place` MediaFile field carrying the canonical place name as resolved by the full routing chain.
- `mf.place_kind` MediaFile field carrying one of `festival`, `venue`, `location`, or `artist`, indicating which tier of the routing chain was authoritative for this set.
- `mf.venue_full` MediaFile field carrying the raw 1001TL venue text as scraped, mirroring the existing `mf.festival_full` field for festivals.
- `.cratedigger/places/<name>/<edition>/` curated assets directory replaces `.cratedigger/festivals/<name>/<edition>/`. The old path is checked as a fallback while the deprecation window is open.
- Real artist poster when no festival, venue, or location information is available. Previously these sets received a gradient image with the artist name rendered on it. They now receive a proper artist portrait sourced through the same `dj_artwork` then `fanart_tv` chain used by `artist_flat` and `artist_nested` layouts, falling back to the gradient only when no artwork can be fetched.

### Changed

- Sets without a 1001Tracklists festival now route by venue or location instead of by artist. The full chain is `festival → venue → location → artist`. A set recorded at "Alexandra Palace" with no linked festival now files under `Alexandra Palace/` (or the equivalent under the configured layout) rather than inside the performing artist's folder.
- Poster hero text always matches the folder name. Previously a venue-routed set could produce a folder named after the venue while the poster title showed the artist name. Both now show the same canonical place name.
- `mf.venue` now carries the alias-resolved canonical venue name. The raw 1001TL venue text moves to `mf.venue_full`. This mirrors the existing `mf.festival` / `mf.festival_full` split and means alias-resolved names appear consistently in folder paths, poster text, and metadata fields.
- The `LOCATION` embedded MKV tag now carries the best available raw venue text (`festival_full`, `venue_full`, or location string) rather than a mix of canonical and raw values. The tag is an archival record of where the set was performed; canonical names appear in folder paths and poster text.

### Deprecated

The following user-facing surface continues to work in 0.15.0 but logs one WARNING per process run when detected. All items are slated for removal at 1.0.0.

- Config file `festivals.json`. Use `places.json` instead.
- Template token `{festival}`. Use `{place}` instead.
- Layouts `festival_flat` and `festival_nested`. Use `place_flat` and `place_nested` instead.
- Config keys `festival_background_priority` and `unknown_festival`. Use `place_background_priority` and `unknown_place` instead.
- Curated assets directory `.cratedigger/festivals/`. Use `.cratedigger/places/` instead.
- Internal `Config` methods `festival_aliases`, `festival_config`, `resolve_festival_alias`, `resolve_festival_with_edition`, `get_festival_display`, and `known_festivals`. Use the corresponding `place_*` equivalents.

## [0.14.5] - 2026-04-25

### Changed

- `cratedigger --version` now performs a live check against GitHub Releases on every invocation, ignoring the cached freshness window. Output is one of three states: a single `cratedigger X.Y.Z` line followed by `(latest)` when current; the existing two-line stale notice when a newer release is available; or just the version line when the network call fails or the check is suppressed via `CRATEDIGGER_NO_UPDATE_CHECK=1`. Suppression by non-TTY output no longer applies on `--version`, since explicit invocation overrides the implicit-suppression rule.
- `cratedigger --check` adds a new `Update status` row reporting the same freshness state, sitting between the `Credentials` and `Python packages` sections. A newer release counts as a warning in the summary; failed or suppressed checks show as informational and do not affect the count.
- `cratedigger --version` and `--check` now contribute to the rotating log file. The seven tool-version subprocess probes from `--check` and the GitHub Releases HTTP call from both paths now leave DEBUG records that can be attached to bug reports. Previously these flags were Typer eager callbacks and exited before `setup_logging` ran, so their activity was never captured.
- `cratedigger --check` no longer reports spurious warnings for genuinely optional items. `cv2/numpy`, `artists.json`, and `artist_mbids.json` now display with the dim `~` (informational) marker instead of the yellow `!` (warning) marker, and do not increment the warnings counter. A clean install with required tools and configured 1001TL credentials reports `All checks passed.` instead of `3 warnings.`. The `!` marker is now reserved for missing items that meaningfully degrade a core workflow (`config.toml`, `festivals.json`, missing 1001TL credentials).

### Performance

- `Config.artist_aliases` and `Config.artist_groups` now cache their result for the lifetime of each `Config` instance. Previously the underlying `DjCache` was re-instantiated on every property access, reading `dj_cache.json` from disk and emitting a duplicate `Loaded DJ cache` DEBUG line each time. During analyse, this fired up to eight times per file, flooding the rotating log with duplicates and degrading per-file throughput. One DJ cache load per process now.

## [0.14.4] - 2026-04-24

### Fixed

- `identify` rate limiting now delivers what the 0.13.1 "smart throttle" patch promised. The pacing was previously re-armed after every 1001Tracklists request, so time you spent in the interactive selection menu never shortened the wait before the next file, and each internal source and DJ fetch inside a single file blocked for the full `delay_seconds` (5s each by default). Identifying one fresh-cache file with two uncached sources and a handful of DJs could stack up around 30 seconds of silent pauses on top of the network time. The between-files wait now anchors on when the previous file's processing began, so interactive-menu time and per-file API work count against it and a file that already ran longer than `delay_seconds` adds no extra wait at all. Internal pacing inside one file drops to a short fixed 0.5 seconds between consecutive requests, just enough to avoid bursting the server right after a pick. The spinner now shows the real remaining cooldown (for example `Cooling down 2.3s`) instead of always advertising the nominal delay. No config changes; `tracklists.delay_seconds` and `--delay` keep their between-files meaning.

## [0.14.3] - 2026-04-24

### Added

- Startup WARNING when the resolved data directory looks like a CrateDigger source checkout. If you clone the repository into `~/CrateDigger/` on Linux (or the equivalent platform default), that folder doubles as the default data directory, which means any test files you drop at the repo root can be silently read as curated user data. CrateDigger now detects this condition by checking for a `pyproject.toml` whose `[project].name` is `cratedigger` and emits a single WARNING naming the path and recommending you set `CRATEDIGGER_DATA_DIR` to a dedicated folder. The check is skipped when `CRATEDIGGER_DATA_DIR` is already set.

### Changed

- The legacy-path WARNING (present since 0.14.0, fired when `~/.cratedigger/` or `~/.1001tl-cookies.json` still exist) now fires at most once per day. A stamp file at `~/.local/state/CrateDigger/legacy-warning.stamp` (or the platform equivalent) records the date of the last warning; subsequent runs on the same day are silent. Previously, a bulk session running several subcommands in sequence would emit the same warning block once per subcommand. The warning itself is unchanged; only the repeat suppression is new.

### Fixed

- Interactive selection during `identify` now shows the filename and search query above the results table, and the "Use stored?" prompt shows the filename above the stored URL. The 0.13.0 StepProgress refactor replaced the per-file `[i/N] filename` header with a transient spinner that is stopped before any interactive prompt opens, so you were left picking between candidates with no indication of which file the prompt was for or what query produced the results. Both prompts now print a `[i/N] filename` line (and, for search, a `Query:` line with the expanded search string) before the existing content. No other behavior changes.

## [0.14.2] - 2026-04-24

### Fixed

- Metadata extraction no longer reads a chapter-scoped `TITLE` when the underlying MKV carries both chapter and global `TITLE` tags. MediaInfo flattens multi-scope `TITLE` into `General.Title` by picking the last per-chapter value, which for identified files (festival sets with per-track chapter tags) meant the analyzer received a track title where it expected the set title. The `TITLE` field is now read scope-aware via `mkvextract`, preferring the global (`TargetTypeValue=50`) value. Files with no Matroska tags at all keep their `SegmentInfo.Title` (for example, yt-dlp downloads), and non-MKV formats are unaffected. The bug was masked on identified files by the 1001Tracklists layer overriding the artist field, but would have produced a junk artist on any MKV with chapter `TITLE` tags and no 1001TL tags.

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
