# 1001Tracklists Integration

CrateDigger integrates with [1001Tracklists](https://www.1001tracklists.com/) to match your recordings against known tracklists and embed chapter markers into MKV files.

## Account setup

A 1001Tracklists account is required for the identify command. Configure your credentials in one of two ways:

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

Environment variables take priority over config file values. If no credentials are configured, CrateDigger prompts for them interactively.

## How searching works

When you run `cratedigger identify`, the tool processes each MKV/WEBM file:

1. **Query generation**: CrateDigger builds a search query from the filename, extracting artist names, festival names, and year information.

2. **Alias expansion**: Short festival abbreviations (AMF, ASOT, EDC, UMF) are expanded to their full names using your festival configuration, improving search accuracy on 1001Tracklists.

3. **Search**: The query is sent to 1001Tracklists. Results come back with titles, durations, and dates.

4. **Scoring**: Results are scored based on artist match, festival match, year match, and duration similarity. Known DJ names and source names from the cache improve scoring accuracy.

5. **Selection**: In interactive mode, you pick from the ranked results. In auto mode, the top result is selected if it meets confidence thresholds.

### Direct URL or ID

You can bypass searching by providing a tracklist URL or numeric ID directly:

```bash
cratedigger identify recording.mkv --tracklist "https://www.1001tracklists.com/tracklist/abc123"
cratedigger identify recording.mkv --tracklist 12345
```

## Chapter format and embedding

Tracklists are converted into MKV chapter markers. Each track entry becomes a chapter with:

- A timestamp (from the tracklist timing data)
- A title (the track name, artist, and mix information)

Chapters are embedded using `mkvpropedit`. The chapter language defaults to "eng" and can be changed via the `chapter_language` config setting.

### Metadata tags

In addition to chapters, CrateDigger embeds several MKV tags:

| Tag | Scope | Content |
|-----|-------|---------|
| Tracklist URL | Global | Link to the 1001Tracklists page |
| Tracklist title | Global | Title of the tracklist |
| Tracklist ID | Global | Numeric identifier |
| Tracklist date | Global | Event date |
| Genres | Global | Top 5 most frequent per-track genres from the tracklist page |
| DJ artwork | Global | URL to the DJ photo from the page |
| Stage | Global | Stage name (if listed) |
| Festival/venue/radio | Global | Source information by type |
| Artists | Global | DJ names associated with the tracklist (display form, pipe-separated) |
| PERFORMER | Per chapter | Primary artist of this track, display name taken directly from the 1001TL track row HTML and then passed through `artists.json` alias resolution (e.g. `SOMETHING ELSE` → `ALOK`). Preserves original casing (`deadmau5`, `CIElll`, `S3PPA`). |
| PERFORMER_SLUGS | Per chapter | Pipe-separated 1001TL slugs for every artist linked on the track row |
| PERFORMER_NAMES | Per chapter | Pipe-separated display names for every artist, aligned slot-for-slot with `PERFORMER_SLUGS` (written by identify) |
| MUSICBRAINZ_ARTISTIDS | Per chapter | Pipe-separated MusicBrainz artist IDs, aligned slot-for-slot with `PERFORMER_NAMES`; empty slot `""` for unresolved names (written by enrich `chapter_mbids`) |
| TITLE | Per chapter | Clean track title with artist prefix stripped (e.g. `Take Over Control` from the row `AFROJACK ft. Eva Simons - Take Over Control`) |
| LABEL | Per chapter | Record label as plain text (e.g. `WALL`, `MAU5TRAP`) |
| GENRE | Per chapter | Pipe-separated per-track genres |

Per-chapter tags use Matroska `TargetTypeValue=30` targeting each chapter's `ChapterUID`. They surface directly in `ffprobe -show_chapters` output (under `chapters[].tags`), which makes them readable by downstream tools like TrackSplit without any format bridge.

**Alignment invariant**: when `MUSICBRAINZ_ARTISTIDS` is present on a chapter, its pipe count matches the other two artist-aligned tags: `len(PERFORMER_SLUGS.split("|")) == len(PERFORMER_NAMES.split("|")) == len(MUSICBRAINZ_ARTISTIDS.split("|"))`. Downstream tools can zip the three lists by index to produce multi-valued FLAC artist tags. See [Enrich / Chapter MBIDs](commands/enrich.md#chapter-mbids-chapter_mbids) and [artist_mbids.json](configuration.md#artist-mbid-override-file).

These tags are used by later pipeline stages (enrich) for artwork lookups, poster generation, and NFO metadata; per-chapter tags feed per-track FLAC metadata when extracting individual tracks from a set.

## Caching and rate limiting

### Rate limiting

CrateDigger respects 1001Tracklists rate limits with a configurable delay between requests. The default is 5 seconds, adjustable via `tracklists.delay_seconds`.

The delay uses smart throttling: if you already spent time making a selection in interactive mode, the delay is reduced or skipped entirely.

### Caching

CrateDigger maintains local caches that improve search accuracy and reduce API calls:

- **DJ cache**: Stores DJ names and aliases learned from tracklist pages. Used for search scoring and artist alias resolution. TTL: 90 days (configurable via `cache_ttl.dj_days`).
- **Source cache**: Stores festival, venue, radio, and conference names. Used for scoring and classification. TTL: 365 days (configurable via `cache_ttl.source_days`).

Each cache entry stamps its own randomised TTL within ±20% of the configured base to prevent synchronised expiry and thundering-herd re-fetches after a bulk first-run fill.

Cache files are stored in `~/.cratedigger/`.

## Auto mode vs interactive mode

### Interactive mode (default)

CrateDigger shows a ranked results table for each file and prompts you to select the correct tracklist. Options:

- Enter a number (1-15) to select a result
- Enter 0 to skip the file
- If a stored URL exists: use it, skip, or research

### Auto mode (`--auto`)

The top-scoring result is selected automatically if it meets two thresholds:

- **Minimum score**: The best result must score at least 150 points
- **Minimum gap**: The best result must lead the runner-up by at least 20 points

Files that fall below either threshold are skipped. This prevents incorrect matches when the search is ambiguous.

Enable auto mode per-run with the `--auto` flag, or set `auto_select: true` in the tracklists config to make it the default.

## Config reference

```json
{
    "tracklists": {
        "email": "",
        "password": "",
        "delay_seconds": 5,
        "chapter_language": "eng",
        "auto_select": false
    }
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `email` | `""` | 1001Tracklists account email |
| `password` | `""` | 1001Tracklists account password |
| `delay_seconds` | `5` | Delay between API requests in seconds |
| `chapter_language` | `"eng"` | ISO 639-2 language code for chapter names |
| `auto_select` | `false` | Use auto-select by default |
