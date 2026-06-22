# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.28.1] - 2026-06-22

### Fixed

- Artist and folder posters built from a monochrome (black-and-white) artist image now render the portrait on a neutral gray gradient instead of collapsing to a bare gradient with just the name. The gradient tone is derived from the image's luminance. Previously, any background image with no saturated pixels (a common style for dramatic B/W promos) was dropped entirely. Fully empty or transparent images still fall back to a plain gradient.

## [0.28.0] - 2026-06-15

### Added

- Colorful year folder posters. A year folder's `folder.jpg` now shows the year in a brand-colored rounded-square badge (in the logo/photo slot used by festival and artist posters), with the parent place or artist name as the hero and, for editioned places (e.g. Tomorrowland Winter), the edition below the accent line. Previously a year folder showed only the year as plain text, or got no poster at all.
- Depth-aware per-level folder posters. `enrich` now generates a `folder.jpg` at every folder level of a nested layout (place, year, artist), each typed by its depth, instead of only the deepest folder. The year poster in particular is now produced by the live pipeline for the standard nested layouts.
- Folder-poster regeneration stamp. Each `folder.jpg` carries an embedded `CDFOLDER` stamp (poster type, name, year, edition, version, and a lightweight fingerprint of the background image), reusing the JPEG-comment mechanism set posters already use. Folder posters now regenerate when their content changes, including after a layout change (e.g. switching `place_nested` to `artist_nested`), a `FOLDER_POSTER_VERSION` bump, or when the underlying artwork changes (refreshed DJ artwork, a swapped curated logo), instead of only when the file is missing.

### Changed

- Folder posters are typed by their depth in the layout rather than by the first layout segment. Some existing folder posters change type or content and regenerate once on the next `enrich`; the Kodi sync clears textures for every regenerated folder level.
- The year badge stays legible on light brand colors via a WCAG contrast safeguard (`_darken_for_white_text`), the inverse of the existing accent-contrast helper.
- Set posters on non-Matroska files (e.g. `.mp4`) now carry the same staleness stamp as `.mkv`/`.webm` files and regenerate on metadata changes, instead of only when the sidecar is missing.

## [0.27.1] - 2026-06-13

### Fixed

- Set posters now build their artist lines from the billed per-act 1001TL list instead of string-splitting the joined name, so an act whose own name contains a separator is no longer mis-split. A single act such as "Above & Beyond" stays on one line, and a duo inside a B2B such as "Dimitri Vegas & Like Mike & Martin Garrix" renders as `Dimitri Vegas & Like Mike` / `& Martin Garrix` rather than three broken lines. Genuine back-to-back sets are unchanged, and the poster keeps showing the billed (alias) name, not the resolved canonical. This matches TrackSplit's cover layout. Existing posters regenerate and their covers re-embed on the next enrich run.

## [0.27.0] - 2026-06-12

### Added

- Interactive library browser on the landing page. Visitors can switch the folder layout (`artist_flat`, `place_flat`, `artist_nested`, `place_nested`) and click through real enriched sets to see the per-folder `folder.jpg`, the set poster, and the set's NFO metadata and tracklist. This is a documentation/site change only; CrateDigger's behaviour is unchanged.
- App icons and favicons for the landing page and docs: a split-monogram mark (off-white `C` + coral `D`) on a dark rounded square, wired into the site `<head>` and as the MkDocs favicon and header logo.

### Changed

- Refreshed the showcase artwork (README gallery, landing-page hero and gallery, hero and social banners) from the current poster pipeline. The galleries now show all three folder-poster layouts (festival, artist, year) instead of festival-only examples, and the README version badge was corrected from the stale `v0.15.0`.

## [0.26.0] - 2026-06-12

### Fixed

- Run-summary emails now show the event edition. The email grouped and labelled sets by the bare canonical place (`Dreamstate`, `UMF`), dropping the edition that the rest of the library (Kodi titles, NFOs, folder layout) renders via `Config.get_place_display`. Emails now build the event name the same way `build_display_title` does, folding in the edition for festival/venue/location places (`Dreamstate SoCal`, `Dreamstate Australia`), so different editions of the same festival are labelled and grouped separately. The place name itself was already resolved through `places.json`; only the edition was missing. Concerts/albums (artist-kind places) are unaffected.

### Changed

- The run-summary email step now reports progress on the console instead of working silently. After `organize` or `identify` finishes, building and sending the email can take a while on large imports because it resizes a poster thumbnail for every set (and `identify` re-analyses each updated file first). A transient spinner now shows those phases (re-analysing updated sets, resizing posters with an `i/N` counter, sending), followed by a one-line verdict: `New-sets email -> sent to N recipients` / `Updated-sets email -> ...` on success, or `Email -> send failed (...)` on failure. Runs that send nothing (no changes, no recipients, or the channel disabled) stay silent in normal mode, matching the previous behaviour. The spinner follows the standard suppression rules (hidden when output is piped or under `--quiet` / `--verbose` / `--debug`); the verdict still prints.

## [0.25.0] - 2026-06-12

### Fixed

- Headline DJs that were identified after their folder's last enrich, or whose set resolves to a different artist via an alias, now reliably get a per-artist image folder. Enrich warms `cache/artists/<slug>/dj-artwork.jpg` directly from the DJ cache for every cached DJ that has profile artwork, instead of only for the headline artist of files physically present at poster time. This is the create counterpart to the existing artist-cache reconcile step (which only pruned orphan folders, never created the canonical ones); downloads are TTL-gated, so repeat runs stay cheap.

## [0.24.0] - 2026-06-12

### Fixed

- Identified files no longer become invisible to enrichment/organize after an MKV rewrite. CrateDigger now reads metadata with ffprobe, which reads embedded tags reliably regardless of where the Matroska Tags element sits in the file. The previous MediaInfo-based reader did a fast, partial scan that could miss a Tags element relocated late in the file (after an `mkvpropedit` attachment or tag write), silently dropping the embedded `CRATEDIGGER_1001TL_*` tags so the file looked unidentified and fell back to filename parsing. The tags were never lost (ffprobe and mkvextract always read them).
- The filename parser no longer swaps artist and place when re-reading organize's own `YYYY - Artist - Place [stage]` output. The `YYYY - A - B` pattern previously assumed `Festival - Artist` order; it now uses known-place detection (and strips a trailing `[stage]`) to keep the artist and place in the right fields for unidentified files. A filename-parsed festival also now defers to an authoritative 1001Tracklists venue/location tag, so venue sets are not mis-routed as festivals.

### Removed

- MediaInfo is no longer used or required. ffprobe (already required for frame sampling, artwork extraction, and cover embedding) is now the single metadata reader. Removing the MediaInfo fallback also removes a silent-failure path: a partial MediaInfo read could return a non-empty but tagless result, which is the bug above. If ffprobe cannot read a file, CrateDigger now logs a warning instead of degrading quietly. If you inspect an MKV with MediaInfo and the `CRATEDIGGER_*` tags appear missing, that is a MediaInfo display limitation, not missing data; verify with `ffprobe` or `mkvextract` (see the FAQ).

## [0.23.0] - 2026-06-12

### Added

- Editions can now be selected by the scraped event **country** when the festival name does not already carry one. 1001Tracklists names every geographic variant of some festivals the same (every Dreamstate event's source is just "Dreamstate"), so a set's edition was previously unrecoverable from the name alone. Now, if the name yields no edition, the country is matched against the resolved place's editions (by edition name or an edition alias, case-insensitive): a Dreamstate set in Australia lands in the `Australia` edition. The name still wins when it carries an edition (`Tomorrowland Winter` stays `Winter`), and a place's main edition stays editionless when its host country is not an edition (the main `Tomorrowland`, in Belgium, stays `Tomorrowland`). Only country-named editions are matched this way; region or season editions like `SoCal` or `Winter` continue to rely on the name or an alias.

## [0.22.0] - 2026-06-12

### Added

- The set poster is now embedded as the MKV's primary `cover.jpg` attachment (portrait, 1000x1500), so video players such as Plex show a real poster thumbnail instead of a landscape video frame. The original landscape thumbnail is preserved as a second `cover_land.<ext>` attachment (and remains as the `{stem}-thumb.jpg`/`-fanart.jpg` sidecars), following the Matroska cover-art convention. A new `cover` enrichment operation (run automatically after posters, or selectable with `enrich --only cover`) performs the embedding. The embedded cover and the poster sidecar refresh automatically when the poster's inputs or layout change; `--regenerate` re-embeds. Kodi is unaffected (it keeps reading the `{stem}-poster.jpg` sidecar via the NFO). No new MKV tags are introduced.

### Changed

- Genre labels from 1001Tracklists now use a uniform compact-slash spacing. 1001Tracklists emits compound genres with inconsistent spacing around the slash (for example `Melodic House/Techno` next to `Dance / Electro Pop`); these are now normalized to the compact form (`Dance/Electro Pop`, `Minimal/Deep Tech`). Each genre stays a single label (nothing is split into separate genres). The normalization is applied both when genres are scraped (so newly identified sets are written compact) and when they are read back from the `CRATEDIGGER_1001TL_GENRES` tag, so existing sets get the tidied genres in their NFO on the next `enrich`. The embedded `CRATEDIGGER_1001TL_GENRES` tag itself keeps its original spacing until the set is re-identified.

## [0.21.0] - 2026-06-11

### Fixed

- Artist names that contain `&` (for example `Above & Beyond`) or that end in dots (for example `Fred again..`) are no longer truncated. Previously the primary `ARTIST` tag, and the artwork cache directory, could collapse `Above & Beyond` to `Above` and `Fred again..` to `Fred again`. The primary artist is now taken from the canonical 1001Tracklists name resolved via the album-artist slug, so it stays intact. Existing files self-heal: the next `enrich` run re-derives and rewrites the corrected `ARTIST` tag.

### Changed

- The per-artist artwork cache (`cache/artists/`) is now keyed by the canonical 1001Tracklists slug instead of a sanitized display name. This collapses the case, Unicode/mojibake, and truncation duplicate directories that the old sanitizer produced (for example `Afrojack` plus `AFROJACK`, or `Tiesto` plus a mojibake variant) into one deterministic, OS-independent directory per artist. Slugs are read from the `CRATEDIGGER_ALBUMARTIST_SLUGS` tag already written to every identified file. Compatibility note: companion tools that read this cache by directory name (TrackSplit) must resolve artwork by the same slug to keep finding it.
- The artwork cache is reconciled on every `enrich` run: directories that do not match a known artist slug (orphans left by the old display-name keying) are removed, and the canonical slug directories are re-populated in the same run. This keeps `cache/artists/` structurally clean rather than accumulating stale directories.

### Added

- NFO files now list the complete lineup of a group act as `<tag>` entries. The members of a group (for example Jono Grant and Tony McGuinness for Above & Beyond, or all three members of Swedish House Mafia) are captured from the 1001Tracklists "Group Members" section and stored in the DJ cache, so the lineup is complete even when the individual members do not have their own sets in the library. Previously only members who happened to have their own cached profile were listed.

## [0.20.4] - 2026-06-11

### Changed

- Unified the email's tertiary text color (footer tally, event count) with the landing page and docs at `#80809a`, so the house-style "muted" grey is a single value across email, site, and docs. The previous email value and this one both pass WCAG AA; this only removes a tiny inconsistency. The canonical palette is now documented in `site/style.css`, mirrored by `festival_organizer/notify/render.py` and `docs/stylesheets/extra.css`.

## [0.20.3] - 2026-06-11

### Changed

- Each set card in the email now repeats its event/place name (for example, "UMF Miami &middot; 2026 &middot; Mainstage"), so a row is self-describing instead of relying on the event group header above it.

### Fixed

- Email tertiary text (the footer tally and the per-event set count) used a grey, `#555570`, that only reached 2.81:1 contrast against the dark background, below the WCAG AA minimum of 4.5:1. It is now `#7a7a93` (4.84:1), which passes WCAG AA. All other email text was already AA or better.

## [0.20.2] - 2026-06-11

### Changed

- Updated-sets emails (sent after `identify`) now show the set duration next to the chapter count (for example, "41 chapters &middot; 1h 30m"), matching the new-sets emails.
- The email footer is now channel-aware. After `identify` it reads "N updated &middot; M unchanged &middot; K skipped" instead of the organize-only "added / up to date / errors" tally, which always showed zeros on identify runs.
- The entire email background is now dark (a full-width wrapper), not just the content card, so mail clients no longer show light gutters around the message.
- Poster thumbnails in email rows now use a proportional column width instead of a fixed 140px, so they scale with the client width (smaller on phones, full size on desktop) and no longer push the text into a cramped column on mobile (notably Gmail on Android, which ignores media queries).
- The CrateDigger wordmark in the email header now uses the landing-page two-tone logo style (Crate in white, Digger in the accent color).

### Removed

- Emails no longer include the machine hostname (it added little for most readers), and the now-unused host plumbing was removed.

## [0.20.1] - 2026-06-11

### Changed

- The email self-test is now a standalone top-level command, `cratedigger --email-test`, alongside `--check`. It takes no path, does not touch your library, and prints whether the sample was sent (and to whom) or why it failed. Previously this was an `organize --email-test` flag, which forced you to pass a library path and trigger a run just to send a test message.

### Removed

- The `--email-test` flag on the `organize` command (replaced by the top-level `cratedigger --email-test`).

## [0.20.0] - 2026-06-11

### Added

- Run-summary emails. CrateDigger can send a styled HTML email at the end of a run, with inline poster thumbnails, so you can see what changed in your library at a glance. There are three independent channels, each with its own on/off switch and recipient list:
  - New sets: sent after an `organize` run when one or more sets were newly added to the library.
  - Updated sets: sent after an `identify` run when chapters were added or changed on one or more sets.
  - Update reminder: sent when a newer CrateDigger release is available, throttled to once per version so you are not nagged on every run. It is suppressed when a content email already went out that run, since that email carries the same update banner.

  Emails are sent only when there is something to report; a run that changes nothing sends nothing. Each email is multipart HTML with a plain-text fallback, and poster thumbnails are embedded inline (no external hosting). Very large runs are capped so a bulk first import cannot produce an oversized message.
- Email configuration. A new `[email]` section in `config.toml` holds the shared SMTP settings (`smtp_host`, `smtp_port`, `smtp_security`, `smtp_user`, `smtp_password`, `from_address`, `thumbnail_width`) plus per-channel `[email.new_sets]`, `[email.updated_sets]`, and `[email.update_reminder]` tables with `enabled` and `to`. The SMTP password can be supplied via the `CRATEDIGGER_SMTP_PASSWORD` environment variable instead of the file. Sending uses the Python standard library, so no new dependencies are required. See the Email notifications section in the configuration docs for setup.
- New CLI options. `organize` gains `--email` / `--no-email` (force or suppress the new-sets email for this run, overriding config) and `--email-test` (send a sample email to verify SMTP and rendering, then continue). `identify` gains `--email` / `--no-email` (force or suppress the updated-sets email).

## [0.19.9] - 2026-06-02

### Changed

- Example places file: added Laroc Club (Sao Paulo) with brand color. Updated file comment to reflect that the file covers festivals, clubs, and venues.

## [0.19.8] - 2026-05-31

### Fixed

- Search scoring: removed DJ cache (+25) and source cache (+20) bonuses that distorted rankings. These bonuses were applied to content score before the duration multiplier, amplifying them up to 1.5x. When a cached DJ name appeared in a wrong result but not in the correct one (e.g. searching for Cosmic Gate, Peggy Gou ranked first because she was cached), the amplified bonus flipped the ordering. Keyword matching and duration matching are the real relevance signals; the cache bonuses added noise at festival events where every result mentions known DJs.

## [0.19.7] - 2026-05-26

### Changed

- Poster hero text: removed accent-colored stroke outline. Plain white text is cleaner at thumbnail sizes.
- Set poster: long single-artist names (e.g. "Swedish House Mafia") now word-wrap at a balanced boundary instead of shrinking to fit on one line. Album posters keep single-line auto-fit to avoid colliding with the centered artist image.

### Fixed

- Per-chapter TITLE tag renamed to CRATEDIGGER_TRACK_TITLE. VLC and MediaInfo flatten the last chapter's TTV=30 TITLE into the file-level display, overriding the set title (e.g. showing "Sunrise (Here I Am) (Tiesto Remix)" instead of "Tiesto @ circuitGROUNDS, EDC Las Vegas"). Same class of bug previously fixed for PERFORMER/LABEL/GENRE. Existing files self-heal on next `identify` run.

## [0.19.5] - 2026-05-19

### Fixed

- Search scoring: alias-expanded festival names (e.g. "EDC" expanded to "Electric Daisy Carnival") no longer create phantom keywords that dilute match ratios. The scoring engine now detects multi-word alias values in queries and matches them bidirectionally against result titles (both the abbreviation and full name). This fixes cases where the wrong artist ranked first because 3 unmatchable keywords skewed the keyword ratio.
- Search filtering: queries containing alias-expanded festival names now correctly trigger the stricter event-context filter, removing low-relevance results that only match a single generic keyword.

## [0.19.4] - 2026-05-17

### Fixed

- Kodi sync: clear folder.jpg texture cache when album posters change. Previously only per-video artwork was cleared; folder-level posters stayed stale.
- Kodi sync: suppress debug logging for high-volume texture operations (GetTextures, RemoveTexture). Reduces debug log from ~2200 to ~200 lines for a typical run.

## [0.19.3] - 2026-05-17

### Fixed

- Kodi sync: texture cache clearing now only runs for items where artwork actually changed (art, posters, fanart, folder.jpg). Items with only NFO updates skip the texture lookup/delete calls.

## [0.19.2] - 2026-05-17

### Fixed

- Kodi sync: throttle refresh calls (100ms between each) and add phase delays to prevent Kodi crashes during large batch updates.
- Kodi sync: hard-delete texture cache entries for changed artwork before refreshing, so Kodi displays updated posters immediately instead of showing stale cached images.

## [0.19.1] - 2026-05-17

### Fixed

- Set poster: venue line no longer duplicates the festival name when both are identical (e.g. club venues like [UNVRS] Ibiza).

## [0.19.0] - 2026-05-17

### Changed

- Poster layout harmonized across set posters, album festival posters, and album artist posters for visual consistency.
- Hero text on all poster types now uses accent color stroke outline instead of drop shadow.
- Hero auto-fit range unified to 130-50px across all poster types (was 110-50 for set, 130-60 for album).
- Letter spacing cap unified to 14px across all poster types (was 8 for set, 14 for album).
- Accent line glow radius unified to 16 across all poster types (was 14 for set).
- Padding from accent line unified to 30px in both directions (was 28px above).
- Below-line text uses a two-tier hierarchy: tier 1 (festival name or edition) is bold 68-36px in accent color; tier 2 (year, stage, venue) is semilight 62-28px auto-fit.
- Festival album poster edition text moved from above the accent line to below it, rendered in bold at accent color.

## [0.18.4] - 2026-05-14

### Added

- Add [UNVRS] Ibiza venue to `places.example.json`.

### Fixed

- Search scoring: all-caps artist names in mixed-case queries (like "MARTIN GARRIX Americas Tour") are now matched as keywords instead of being misclassified as abbreviations. Also fixes post-expansion queries where alias substitution introduced mixed case.
- Search scoring: raised the all-keyword-match bonus and keyword score cap so that a correct result with good duration and year match reliably reaches the "+" confidence band.

## [0.18.3] - 2026-05-12

### Added

- `cratedigger --check` now shows the log directory path and file count.

### Changed

- Bug report issue template asks for the automatic log file instead of `--debug` output.
- Kodi integration docs point at the per-run log file instead of suggesting `--debug`.

## [0.18.2] - 2026-05-12

### Fixed

- `identify` search: strip "LIVE FROM" from search queries. This YouTube title pattern polluted 1001TL search results, causing files like "FISHER LIVE FROM EDC LAS VEGAS 2025" to miss the correct tracklist match.

### Dependencies

- Bump minimum `opencv-python-headless` to >=4.13.0.92
- Bump minimum `typer` to >=0.25.1
- Bump minimum `platformdirs` to >=4.9.6

## [0.18.1] - 2026-05-08

### Added

- Per-file attribution in log files: each log record now includes `[filename.mkv]` when a file is being processed, making batch-run logs easier to read.
- `CRATEDIGGER_LOG_LEVEL` environment variable overrides the console log level without affecting the log file. Accepts standard Python level names (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Invalid values fall back to the flag-derived default.

### Fixed

- Third-party loggers (`urllib3`, `PIL`) pinned to INFO so their DEBUG output no longer floods the log file.
- FAQ sync troubleshooting now points at the log file instead of suggesting `--debug`.

## [0.18.0] - 2026-05-08

### Added

- NFO staleness detection: `enrich` now regenerates `.nfo` files when the underlying metadata has changed, not only when the file is missing. Covers changes to artists, genres, stage, edition, title, DJ cache group members, and config display names. The original `dateadded` timestamp is preserved on regeneration so Kodi's "date added" sorting stays correct. Use `--enrich-force` to regenerate unconditionally as before.

### Changed

- `generate_nfo` refactored: XML building extracted into `generate_nfo_xml()` which returns the XML string without writing to disk, enabling in-memory content comparison.

## [0.17.9] - 2026-05-08

### Fixed

- User-facing guidance warnings (legacy paths, source checkout, legacy library config) reverted to readable prose. Structured key=value format is for diagnostic events; actionable warnings that tell the user what to do need to be human-readable.

## [0.17.8] - 2026-05-08

### Changed

- All remaining freeform log messages across the entire codebase now use structured `subsystem.event: key=value` format. Covers 82 messages across 19 modules (artwork, config, embed_tags, executor, frame_sampler, kodi, library, log, metadata, mkv_tags, nfo, operations, paths, poster, scanner, tracklists/api, tracklists/cli_handler, tracklists/dj_cache, update_check).

## [0.17.7] - 2026-05-08

### Changed

- All debug logging in `fanart.py` now uses structured `fanart.*: key=value` format, completing the structured logging migration started in 0.15.1.
- Removed per-artist MBID cache hit log lines. Positive cache hits produced thousands of lines per run with no diagnostic value. Negative hits and override hits are preserved.
- MBIDCache and ArtistMbidOverrides are now shared across FanartOperation, ChapterArtistMbidsOperation, and AlbumArtistMbidsOperation, eliminating hundreds of redundant cache loads per run.
- Pipeline runner now emits a per-file operation summary (`enrich.file: file=... nfo=skipped art=done ...`) so the debug log can answer "what happened to each file?"
- Migrated remaining freeform debug messages in `operations.py` and `cli.py` (Kodi sync, enrich artwork/poster events) to structured format.

## [0.17.6] - 2026-05-08

### Changed

- Identify verdict is now always "updated" when writing to a file. Previously it showed "done" for first-time embeds and "updated" for tag-only changes, which was inconsistent when chapter counts changed.

### Fixed

- Tracklist page canary no longer warns on pages without `@` in the h1 (aftermovies, compilations, radio shows). Now only flags when the h1 element is entirely missing.

## [0.17.5] - 2026-05-08

### Added

- Chapters are now supplemented from HTML-parsed mashup main rows when the export API omits them. Mashup transitions that previously created gaps in the chapter timeline (e.g. "Offshore vs. Greyhound vs. Fine Day vs. Touch Me" on the SHM @ Ultra set) now appear as chapters with full per-chapter metadata.

## [0.17.4] - 2026-05-08

### Fixed

- Mashup rows with valid cue timestamps are no longer silently dropped during tracklist parsing. Previously, rows with the `con` CSS class were rejected regardless of their cue position, causing gaps in the chapter timeline for mashup-heavy sets.

## [0.17.3] - 2026-05-07

### Fixed

- DJ cache is now loaded once per run for organize/enrich (same fix as 0.17.1 for identify). Previously the organize flow constructed a separate `DjCache` instance.

### Changed

- Organize template strings are now logged once at startup (`organize.templates`) instead of repeating on every file. Per-file `organize.template` events are slimmer and include `place_kind`.
- New `organize.target` event in dry-run mode shows source vs target path comparison with match status.
- New `organize.action` event after file operations shows what actually happened (rename/copy/move).
- `organize.is_needed` now logs in all code paths (previously only when output_root was set).
- Sidecar log event migrated to structured `organize.sidecar` format.

## [0.17.2] - 2026-05-07

### Fixed

- Skip Title tag parsing for identified files. Removes noisy `parsers.filename_fallback` debug lines that fired on every identified file (the Title tag contains a chapter title, not a parseable filename).
- `analyzer.result` and `classifier.result` log events now include `file=` so you can tell which file they refer to.

### Changed

- New `identify.genres` log event shows the final genre list written to the file, including how many survived frequency capping vs. how many were scraped (`written=5 scraped=13 source=frequency`).

## [0.17.1] - 2026-05-07

### Fixed

- DJ cache is now loaded once per run instead of three times. `Config` owns a single lazy `DjCache` instance shared by `artist_aliases`, `artist_groups`, and the identify session.

### Changed

- All remaining freeform debug/info log events migrated to structured `command.event: key=value` format across `config.*`, `dj_cache.*`, `source_cache.*`, `analyzer.*`, `classifier.*`, `parsers.*`, `embed_tags.*`, `subprocess.*`, and `tags.write`. Every DEBUG/INFO event in the identify flow is now greppable by prefix.

## [0.17.0] - 2026-05-07

### Changed

- The `Tagged:` metadata line in identify output is now aligned with the filename column instead of flush-left.
- Log files are now per-command (`identify-2026-05-07T13-44-01-a3f2.log`) instead of a single rotating `cratedigger.log`. Each CLI invocation writes its own file, so concurrent runs never conflict. Files older than 7 days are deleted automatically at startup. Writes are buffered for efficiency.
- The identify command now emits structured debug/info events at every decision point: stored URL reuse, search queries, auto-select scoring, chapter comparison, tag updates, self-heal triggers, and skip reasons. All events use the `identify.*` prefix and `key=value` format for grepability.
- All freeform log events in `api.py` and `chapters.py` migrated to structured `identify.*`, `session.*`, and `chapters.*` format.

## [0.16.1] - 2026-05-07

### Fixed

- Standalone venue events (no linked festival) no longer produce a duplicated venue name in the filename. For example, `2026 - FISHER - Bay Oval Park [Bay Oval Park].mkv` is now `2026 - FISHER - Bay Oval Park.mkv`. The same duplication was present in the embedded MKV `TITLE` and `SYNOPSIS` tags; both are fixed.
- Re-identifying a file with a different tracklist now clears tags from the prior identification that no longer apply. Previously, tags such as `FESTIVAL`, `VENUE`, `STAGE`, `COUNTRY`, and `GENRES` from the old tracklist would persist alongside the new data. Every managed 1001TL tag is now explicitly set or cleared on each identification.

### Changed

- The inline tag-building block in `embed_chapters()` is extracted into a standalone `build_1001tl_tags()` function. The identify command's verify path uses the same function, so dry-run output accurately reflects both tag additions and tag clearings.

## [0.16.0] - 2026-05-07

Verdict output redesign across all three commands. The organize output now shows a from/to layout with color-highlighted changes, and up-to-date files use a compact single-line format across identify, organize, and enrich.

### Changed

- Organize preview and done verdicts now show a two-line from/to block: line 1 shows the source path, line 2 shows the target path. The target folder is bold orange when it differs from the source, and only the changed segments of the target filename are highlighted. Previously the output showed a single detail line with just the target path or "would copy/rename/move to" prefix.
- Up-to-date verdicts across all commands are now a single compact line with no detail. Previously identify showed "N chapters", enrich showed "all up to date" or verbose skip reasons, and organize showed "already at target" on a second line.
- Counter index is right-aligned within the total width: `[ 1/86]` instead of `[1/86]`. Filenames now start at the same column regardless of the current file number.
- Source paths in organize output include folder context. Files at the library root show `./` as the folder prefix; files outside the library show the bare filename.

### Removed

- The `_organize_detail()` helper in `progress.py` and its test file `tests/test_organize_detail.py`. Replaced by `organize_verdict()` in `console.py`.

## [0.15.1] - 2026-05-05

### Fixed

- Organize dry-run and live-run now correctly show "up-to-date" on Windows when the typed path prefix differs in case from the resolved library path (e.g., `e:\Data\Festivals\Video` vs `E:\Data\Festivals\Video`). Directory-case renames within the library (e.g., `Alok` to `ALOK`) are still detected.

### Changed

- Subprocess debug logging no longer emits a line for every successful invocation. Only failures (non-zero exit, timeout, spawn error) are logged. This removes roughly 60% of `--debug` output noise.
- New structured debug events for the organize flow: `organize.resolve` (startup), `organize.template` (per-file template rendering), `organize.target` (per-file path comparison), `organize.is_needed` (per-file operation decision). All use `command.event: key=value` format for grepability.

## [0.15.0] - 2026-04-26

Place routing replaces festival-only routing with a full `festival → venue → location → artist` chain. Sets that previously had no linked festival were silently routed by artist; they now file under their venue or location name. All festival-specific API surface, config keys, template tokens, and layout names are removed in this release; the place-named equivalents replace them directly.

### Migration

On first run after upgrade, CrateDigger automatically copies your existing `festivals.json` to `places.json` and copies user-global `.cratedigger/festivals/<name>/` curated logo directories to `.cratedigger/places/<name>/`. The legacy files and directories stay in place so you can roll back to 0.14.x without losing data; delete them once you have verified the new locations work.

The `default_layout` value in your `config.toml` is also rewritten automatically: `festival_flat` becomes `place_flat` and `festival_nested` becomes `place_nested` at load time.

Everything else listed in the Removed section below requires a manual update. There are no runtime aliases or deprecation warnings for those items; they are gone.

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
- `build_display_title` (used for the Kodi browse-view title and the embedded MKV `TITLE` tag) now reads `mf.place` instead of `mf.festival`. Venue and location-routed sets that previously rendered as just the artist name now render as `Artist @ Place` (or `Artist @ Stage, Place` when a stage is set), matching what the folder routing already does.

### Removed (breaking, but auto-migrated where possible)

The festival-named API surface and config keys are removed. Auto-migration covers the on-disk data files transparently:

- `festivals.json` is copied to `places.json` on first run; legacy file retained for rollback.
- `.cratedigger/festivals/<name>/` curated logo subdirectories are copied to `.cratedigger/places/<name>/` on first run; legacy directories retained.
- `default_layout = "festival_flat"` (or `festival_nested`) in your `config.toml` is rewritten to the place-named equivalent at load time.

Manual updates required if your `config.toml` or external code uses any of:

- `[layouts.festival_flat]` / `[layouts.festival_nested]` table headers for custom layout definitions. Rename to `[layouts.place_flat]` or a user-chosen name.
- `{festival}` template token in custom layouts. Replace with `{place}`.
- TOML keys: `[festival_aliases]`, `[festival_config]`, `festival_background_priority`, `unknown_festival`. Use `[place_aliases]`, `[place_config]`, `place_background_priority`, `unknown_place`.
- `Config.festival_aliases` / `festival_config` / `resolve_festival_alias` / `resolve_festival_with_edition` / `get_festival_display` / `known_festivals` in external Python code. Use the `place_*` equivalents.
- Library-local `<library>/.cratedigger/festivals/` directories (NOT auto-migrated). Rename to `<library>/.cratedigger/places/`.

## [0.14.6] - 2026-05-05

### Fixed

- `organize` now shows the full relative target path in both dry-run previews and live verdicts. Previously, when only the folder changed (the common case for in-place organize with well-named files), the detail line showed just the folder with a trailing slash (e.g., `would rename to AMF/`), which made it look like the filename was being lost. The detail now always includes the filename (e.g., `would rename to AMF/2024 - Marlon Hoffstadt - AMF.mkv`).

### Added

- Coachella festival aliases and brand color.

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
