# 1001Tracklists Integration

CrateDigger integrates with [1001Tracklists](https://www.1001tracklists.com/) to match your recordings against known tracklists, embed chapter markers, and populate rich per-track and per-set metadata. 1001TL is the source of everything in CrateDigger that goes beyond what the filename and embedded metadata can tell us.

## Do I need an account?

Short answer: no, but the feature gap is significant.

| Capability | No account (best-effort) | With account |
|---|---|---|
| Filename + embedded-metadata parsing | ✓ | ✓ |
| Alias resolution (`artists.json`, festival aliases) | ✓ | ✓ |
| Organize into library tree | ✓ | ✓ |
| Cover art (embedded → frame sample) | ✓ | ✓ |
| Posters (per-video + folder) | ✓ | ✓ |
| fanart.tv / TheAudioDB artist artwork | ✓ | ✓ |
| NFO metadata | ✓ (from filename + embedded tags) | ✓ (richer, 1001TL-sourced) |
| MKV file-level tags (`ARTIST`, `TITLE`, `DATE_RELEASED`) | ✓ (from filename) | ✓ (+ canonicalized DJ names) |
| Chapter markers per track | ✗ | ✓ |
| Per-chapter track metadata (title, label, genre, artist MBIDs) | ✗ | ✓ |
| Album-level multi-artist tags (`CRATEDIGGER_ALBUMARTIST_*`) | ✗ | ✓ |
| Stage / venue / festival / event taxonomy | partial (aliases only) | full |
| DJ artwork from 1001TL | ✗ | ✓ |
| Canonical DJ name (casing, learned aliases) | partial | full |

**Without an account**, CrateDigger still produces a watchable library. Metadata comes from parsing the filename (using your `festivals.json` aliases and `artists.json` rules), reading embedded MKV tags via MediaInfo, looking up fanart.tv artwork via a MusicBrainz ID resolved from the parsed artist name, and extracting cover art from embedded attachments or sampled video frames. You get decent posters and a sensibly organized folder tree. What you lose is everything tied to the authoritative tracklist: chapter markers, per-track metadata (title, label, genre, artist MBIDs), canonical DJ naming beyond your manual aliases, and the stage/venue/event taxonomy that drives album-level context tags.

**With an account**, every item in the matrix is filled in. `identify` runs against 1001TL, picks a matching tracklist, and embeds per-chapter metadata plus album-level event context into the MKV.

## Account setup

Configure credentials in one of two ways.

### Config file

```json
{
    "tracklists": {
        "email": "your@email.com",
        "password": "your-password"
    }
}
```

### Environment variables

```bash
export TRACKLISTS_EMAIL="your@email.com"
export TRACKLISTS_PASSWORD="your-password"
```

Environment variables take priority over config file values. If no credentials are configured at all, CrateDigger prompts for them interactively on first use.

## What CrateDigger extracts from a tracklist

For each identified tracklist, CrateDigger captures:

- **Chapter markers** — one per track with timestamp and title. Written directly into the MKV as Matroska chapters. See [per-chapter tags](tag-reference.md#per-chapter-ttv30) for details.
- **Per-track metadata** — artist, title, label, genre, and MusicBrainz artist IDs per chapter. All pipe-aligned for multi-artist tracks. See [per-chapter tags](tag-reference.md#per-chapter-ttv30).
- **Album-level event context** — tracklist URL, title, ID, date, and source taxonomy (festival / venue / conference / event promoter / country / stage). See [collection-level tags](tag-reference.md#collection-level-ttv70).
- **DJ list and album-artist MBIDs** — canonical DJ names, 1001TL slugs, and aligned MusicBrainz IDs for multi-value album-artist credits. See [album-level artist tags](tag-reference.md#album-level-artist-tags).
- **DJ artwork URL** — the DJ photo from the tracklist page, used as a background source in the [poster pipeline](library-layout.md#poster-layouts).

## What identification looks like

Interactive selection is the default mode. `identify` prints a ranked results panel and prompts you to pick the correct match (or skip). See [identify command: interactive selection](commands/identify.md#interactive-selection) for a sample transcript and the auto-mode behaviour.

## Rate limiting and caching

CrateDigger respects 1001TL's rate limits with a configurable delay between requests (default 5 seconds). The delay uses smart throttling: if you already spent time picking a result in interactive mode, the explicit sleep is reduced or skipped.

Two local caches make subsequent runs faster and more accurate:

- **DJ cache** — canonical DJ names and aliases learned from tracklist pages. Used to canonicalize casing (so 1001TL's "SOMETHING ELSE" becomes "Something Else" on disk) and to improve search scoring on subsequent identifies.
- **Source cache** — festival, venue, radio, and conference names. Used to classify tracklists by source type.

Each cache entry randomises its TTL within ±20% of the configured base, so a bulk first-run population doesn't all expire at the same time and stampede the API on the next run. Config keys (`delay_seconds`, `cache_ttl.dj_days`, `cache_ttl.source_days`) live in [configuration](configuration.md#cache-ttl).

## See also

- [Identify command](commands/identify.md) — command reference, flags, interactive/auto selection, examples.
- [Tag reference](tag-reference.md) — every tag written into the MKV.
- [Library layout](library-layout.md) — sidecar files, NFO contents, poster layouts, artwork sources.
- [Configuration](configuration.md) — config keys for tracklists, caching, and credentials.
