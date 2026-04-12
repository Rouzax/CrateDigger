# Per-Chapter Artist & Genre Tags (1001TL → MKV → TrackSplit)

## Context

**Problem:** TrackSplit (standalone CLI at `/home/martijn/TrackSplit/`) extracts per-track FLACs from CrateDigger-tagged MKVs. It currently has no source of truth for per-track `ARTIST` or `GENRE` — only the set-level `CRATEDIGGER_1001TL_ARTISTS` (which is the *set owner*, not per-track) and a single deduped `CRATEDIGGER_1001TL_GENRES` list covering the whole set. FLAC tags TrackSplit writes are therefore coarse: every track on a set FLAC carries the set owner's name as `ARTIST` and the merged genre blob.

**Observation:** 1001TL tracklist HTML already contains richer per-track data:
- Per-track `<meta itemprop="genre">` tags (currently parsed but merged into a set-level deduped list at `api.py:538-555`)
- Per-track `<a href="/dj/<slug>/">` artist links (currently not parsed at all)

And Matroska natively supports per-chapter tags via `TargetTypeValue=30` + `ChapterUID` targeting, fully writable through the existing `mkvpropedit --tags` flow.

**Secondary problem (surfaced during design):** artist-name canonicalisation is currently inconsistent across tags. `DJCache` (`dj_cache.json`) holds the canonical titlecased name (e.g. `Afrojack`), which already matches the top-level `ARTIST` tag and the `.cratedigger/artists/` directory. But `CRATEDIGGER_1001TL_ARTISTS` stores the 1001TL display form (`AFROJACK`, all-caps, their set-owner convention), and chapter title strings mix cases within the same file. There is no single source of truth.

**Outcome:** per-track `ARTIST` (canonical) + `GENRE` (per track) written as Matroska chapter-targeted tags (`TargetTypeValue=30`); `DJCache` extended to resolve any per-track slug on-demand; all new writes use `DJCache` canonical name as the single source of truth. Existing files can be re-enriched to pick up canonical names. Version bumps 0.9.8 → 0.9.9.

## Design decisions (from brainstorm)

- **Artist semantics:** store a structured per-chapter `ARTIST_SLUGS` list (all linked artists on the track row, comma-joined slugs) plus a resolved `ARTIST` canonical string (first slug's `DJCache` canonical name). TrackSplit decides how to present.
- **Canonical name enforcement:** all *new* writes resolve artist references through `DJCache`. That includes rewriting `CRATEDIGGER_1001TL_ARTISTS` to canonical form and normalising the set-owner token inside chapter title strings. Existing files unchanged unless re-enriched. (Option 2 from brainstorm.)
- **Unknown slugs:** fetched on-the-fly via existing `DJCache.get_or_fetch` flow, respecting the 5s throttle. First enrichment of a set with N uncached artists takes ~N × 5s; all subsequent enrichments hit cache.
- **Cache TTL (project-wide change):** applies jittered per-entry TTL to *all five* TTL-based caches in the project (`DJCache`, `SourceCache`, `MBIDCache`, and the two cache classes in `operations.py`). Not just the DJ cache. Two parts:
  - Bump `DJCache` default from 30 → **90 days**. Bump `SourceCache` default from 30 → **365 days** (festival/venue metadata for a given source ID effectively never changes). Leave the 90-day caches (`MBIDCache`, image/artwork caches) at 90 days.
  - Add **per-entry randomised TTL** at every cache insert: `entry["ttl"] = base_ttl_seconds * random.uniform(0.8, 1.2)` (±20% jitter → actual lifetimes spread ±20% around the base). Staleness check becomes `now - entry["ts"] > entry.get("ttl", default_ttl_seconds)`. Legacy entries without `ttl` fall back to the class default. Natural re-fetches dribble across a ~5-week window (for a 90-day base) instead of all hitting one day.

## Critical files to modify

- `festival_organizer/tracklists/api.py` — extend tracklist HTML parse to produce structured `Track` rows (timestamp, raw title text, artist slugs, genres). Stop throwing away per-track genre meta.
- `festival_organizer/models.py` — add `Track` dataclass; extend `TracklistExport` with `tracks: list[Track]` (alongside existing `lines: list[str]` for backward compatibility during transition).
- **New shared utility** `festival_organizer/cache_ttl.py` — two small functions: `jittered_ttl_seconds(base_days, jitter_pct=0.2)` returns a randomised lifetime to stamp onto an entry at write time; `is_fresh(entry, default_ttl_seconds)` reads `entry.get("ttl", default)` and compares against `now - entry["ts"]`. Single source of truth for jitter logic.
- `festival_organizer/tracklists/dj_cache.py` — bump default TTL to 90 days; call shared `jittered_ttl_seconds` on insert; call shared `is_fresh` on read; add batch helper `get_or_fetch_many(slugs)` that drives the Rich progress UI and handles the throttle loop.
- `festival_organizer/tracklists/source_cache.py` — bump default TTL to 365 days; same shared helper calls on insert and read.
- `festival_organizer/fanart.py` (`MBIDCache`) — keep 90-day default; same shared helper calls on insert and read.
- `festival_organizer/operations.py` — the two cache classes at lines 233 and 643 get the same shared helper calls on insert and read (defaults stay 90 days).
- `festival_organizer/config.py` — no schema change required, but document the new `cache_ttl` behaviour (values are now *base* TTLs; actual lifetimes jitter ±20% per entry).
- `festival_organizer/tracklists/chapters.py` — `build_chapter_xml` gains an optional `per_chapter_tags` arg; when present, emit sibling `<Tag>` blocks at `TargetTypeValue=30` targeting each `ChapterUID`. `embed_chapters` wires the tags through to `write_merged_tags` at TTV=30.
- `festival_organizer/mkv_tags.py` — extend tag-scope handling to accept TTV=30 entries keyed by `ChapterUID`. Ensure the extract-merge-write cycle round-trips chapter-targeted tags (preserve tags the user added manually, just as is already done for TTV=50/70).
- `festival_organizer/metadata.py` (or wherever set-owner artist string is composed for `CRATEDIGGER_1001TL_ARTISTS` and the chapter-title set-owner token) — route through `DJCache.canonical_name(slug)` instead of using the raw H1 display string.
- `festival_organizer/cli.py` / operations layer — surface fetch progress per the logging contract (see below). No new flags required.
- `pyproject.toml` — version bump 0.9.8 → 0.9.9.

## Data flow (new)

1. `export_tracklist()` fetches tracklist HTML (existing) → parses per-track rows → builds `list[Track]`, each with `start_ms`, `raw_text`, `artist_slugs: list[str]`, `genres: list[str]`.
2. Enrichment collects the union of all per-track slugs + set-owner slugs → single `DJCache.get_or_fetch_many(slugs)` call resolves them, fetching any uncached entries with the 5s throttle and Rich progress.
3. Chapter build: for each `Track`, emit a `<ChapterAtom>` (existing) **plus** a per-chapter `<Tag>` with `ARTIST` = canonical name of first resolved slug, `ARTIST_SLUGS` = comma-joined slug list, `GENRE` = pipe-joined per-track genres.
4. `write_merged_tags` writes TTV=50 (unchanged), TTV=70 (unchanged, but `CRATEDIGGER_1001TL_ARTISTS` now canonical), and TTV=30 (new, per-chapter) in one `mkvpropedit` call.
5. TrackSplit reads chapter tags via its existing `mkvmerge -J` parse (tags already appear on chapter objects in that output) and writes FLAC Vorbis comments from them.

## Canonical-name unification (all new writes)

- `CRATEDIGGER_1001TL_ARTISTS` ← `DjCache.canonical_name(set_owner_slug)`. For multi-DJ B2B sets, canonical names joined with `|` (pipe) — matches the existing convention across all 79 enriched files (`Armin van Buuren|KI/KI`, `AFROJACK|R3HAB`, `Agents Of Time|MORTEN`). Same separator used by `CRATEDIGGER_1001TL_GENRES`. Artist names are guaranteed not to contain `|` (unlike `&`, `,`, or spaces, which appear inside legitimate names like `Above & Beyond`, `Axwell & Ingrosso`, `W&W`).
- **Alias chain**: the set-owner slug on 1001TL can be an alias of a different canonical artist (example: the 1001TL page shows `SOMETHING ELSE` as the artist but `SOMETHING ELSE` is an alias of canonical `ALOK` in `artists.json`). The canonical resolution must walk: 1001TL slug → `DjCache.canonical_name` → `artists.json` alias map → final canonical. Existing code already does the alias resolution for the top-level `ARTIST` tag; reuse that resolver when composing `CRATEDIGGER_1001TL_ARTISTS` so both tags end up pointing at the same canonical name.
- Chapter title strings: the set-owner token (currently `AFROJACK` in `"AFROJACK - ID"`) swapped for `DJCache.canonical_name`. Non-set-owner tokens inside the track text are left alone (they're part of the track's own artist/mashup string and parsing them out robustly isn't worth the risk of mangling).
- Top-level `ARTIST` (TTV=50) already uses canonical; no change.
- `CRATEDIGGER_1001TL_GENRES` (set-level) now computed as **top 5 most frequent per-track genres** across the set instead of the current "union of every `<meta itemprop="genre">` on the page, deduped". Rationale: the current approach produces a noisy kitchen-sink list (12+ genres for a 30-track set), most of which apply to a single outlier track. Top-5-by-count gives a useful dominant-genre fingerprint for the set. Ties broken by first-appearance order so results are deterministic. Fallback: if the per-track parser yields no genres (HTML shape change, empty tracklist), keep the existing scrape-and-dedupe behaviour so enrichment never silently produces an empty genre list.

## Logging (per `.claude/docs/logging.md`)

- **Default stdout:** Rich progress counter for the per-artist fetch loop, e.g. `Fetching artist pages: 12/30 (Afrojack)`. Silent when cache fully hits.
- **`--verbose` (INFO):** per-slug cached-vs-new decision, end-of-set summary (`Resolved 47 per-track artists (30 cached, 17 fetched)`).
- **`--debug` (DEBUG):** cache lookups, throttle waits, HTML parse counts per row.
- **WARNING:** slug 404, artist page parses zero fields, slug collision (two slugs → same canonical name).

## Backward compatibility

- Existing files: untouched until re-enriched. No migration script.
- `TracklistExport.lines` kept for any caller still reading text-formatted chapter labels; `tracks` is additive.
- Existing TTV=50/70 tag shape unchanged; only the *value* of `CRATEDIGGER_1001TL_ARTISTS` changes (to canonical case) for new writes.
- Chapter XML stays valid for players that don't read chapter tags (they just see the `<ChapterDisplay>` string as today).

## Verification

1. **Unit:** `Track` parser given a saved 1001TL tracklist HTML fixture, asserts expected per-track slugs and genres. Use the Afrojack EDC 2025 set as the golden fixture (matches the mkv-info-dump sample).
2. **Unit:** `DJCache.get_or_fetch_many`, mock HTTP, verify throttle (5s gaps), cache-hit skip, progress callback invoked.
3. **Unit:** `cache_ttl.jittered_ttl_seconds`, 1000 samples land within `[0.8×base, 1.2×base]`; `is_fresh` reads `entry["ttl"]` when present and falls back to default when absent. Exercise each of the five caches at least once to confirm the wiring.
4. **Unit:** `build_chapter_xml` with `per_chapter_tags`, XML round-trips through `mkvpropedit --tags` and reads back the right `ARTIST`/`GENRE` per `ChapterUID`.
5. **Integration:** end-to-end re-enrichment of the Afrojack EDC 2025 MKV at `/home/martijn/_temp/cratedigger/data/mkv-info-dump/...`:
   - `mkvmerge -J` output shows per-chapter tags attached to each chapter object.
   - `CRATEDIGGER_1001TL_ARTISTS` now reads `Afrojack` (not `AFROJACK`).
   - Chapter title `"AFROJACK - ID"` reads `"Afrojack - ID"`.
   - `dj_cache.json` grew by the set of new per-track slugs.
6. **TrackSplit smoke test:** run TrackSplit against the re-enriched MKV, confirm output FLACs carry per-track `ARTIST` and `GENRE` Vorbis comments matching the chapter tags.
7. **Logging:** verify default/`--verbose`/`--debug` output matches the logging contract.

## Out of scope

- Role-aware artist split (primary / featured / remixer / mashup-component). Deferred until a concrete consumer needs it; `ARTIST_SLUGS` preserves enough data to add later without re-scraping.
- Per-track BPM/key/label extraction (not currently reliably on 1001TL track rows; separate project if wanted).
- Migration script for already-enriched files. User can re-run enrichment on demand.
