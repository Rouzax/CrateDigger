# 1001Tracklists Integration

CrateDigger integrates with [1001Tracklists](https://www.1001tracklists.com/) to match your recordings against known tracklists, embed chapter markers, and populate rich per-track and per-set metadata. 1001Tracklists is a community website that logs exactly what tracks DJs played during sets, including timestamps. It is the source of everything in CrateDigger that goes beyond what a filename and embedded video tags can provide.

## Do I need an account?

Short answer: no, but the feature gap is significant.

| Capability | Without account | With account |
|---|---|---|
| Filename and embedded metadata parsing | Yes | Yes |
| Alias resolution (artists.json, festival aliases) | Yes | Yes |
| Organize into library tree | Yes | Yes |
| Cover art (embedded or sampled video frame) | Yes | Yes |
| Posters (per-video and folder) | Yes | Yes |
| Artist artwork from fanart.tv and TheAudioDB | Yes | Yes |
| NFO metadata | Yes (from filename and embedded tags) | Yes (richer, from 1001Tracklists) |
| MKV file-level tags (ARTIST, TITLE, DATE_RELEASED) | Yes (from filename) | Yes (with canonicalized DJ names) |
| Chapter markers per track | No | Yes |
| Per-chapter track metadata (title, label, genre, artist MBIDs) | No | Yes |
| Album-level multi-artist tags | No | Yes |
| Stage, venue, festival, and event taxonomy | Partial (aliases only) | Full |
| DJ artwork from 1001Tracklists | No | Yes |
| Canonical DJ name (casing, learned aliases) | Partial | Full |

**Without an account**, CrateDigger still produces a usable library. Metadata comes from parsing your filenames using your `festivals.json` aliases and `artists.json` rules, reading any embedded MKV tags, looking up artist artwork from fanart.tv via a resolved MusicBrainz ID, and extracting cover art from embedded attachments or sampled video frames. You get organized folders, reasonable posters, and NFO files. What you lose is everything tied to the authoritative tracklist: chapter markers, per-track metadata (title, label, genre, artist MBIDs), canonical DJ naming beyond your manual aliases, and the stage and venue context tags.

**With an account**, every row in the table is filled in. `identify` matches your recording against 1001Tracklists, and embeds per-chapter metadata plus album-level event context directly into the MKV.

## Account setup

You need a free account at [1001Tracklists](https://www.1001tracklists.com/). Configure your credentials in one of two ways.

### Config file

Add your email and password under the `tracklists` section in `~/.cratedigger/config.json`:

```json
{
    "tracklists": {
        "email": "your@email.com",
        "password": "your-password"
    }
}
```

### Environment variables

=== "Linux / macOS"

    ```bash
    export TRACKLISTS_EMAIL="your@email.com"
    export TRACKLISTS_PASSWORD="your-password"
    ```

=== "Windows (PowerShell)"

    ```powershell
    $env:TRACKLISTS_EMAIL = "your@email.com"
    $env:TRACKLISTS_PASSWORD = "your-password"
    ```

Environment variables override config file values. If your email is not configured at all, CrateDigger prompts for both credentials interactively before starting. If your email is set but your password is missing, it exits with an error.

## What CrateDigger extracts from a tracklist

For each identified tracklist, CrateDigger captures:

- **Chapter markers:** one per track with timestamp and title, written directly into the MKV as Matroska chapters. See [per-chapter tags](tag-reference.md#per-chapter-tags-ttv30).
- **Per-track metadata:** artist, title, label, and genre per chapter, with pipe-aligned multi-artist support. See [per-chapter tags](tag-reference.md#per-chapter-tags-ttv30).
- **Album-level event context:** tracklist URL, title, ID, date, and source taxonomy (festival, venue, conference, event promoter, country, stage). See [collection-level tags](tag-reference.md#collection-level-tags-ttv70).
- **DJ list and album-artist MBIDs:** canonical DJ names, 1001Tracklists slugs, and aligned MusicBrainz IDs for multi-value album-artist credits. See [album-level artist tags](tag-reference.md#album-level-artist-tags).
- **DJ artwork URL:** the DJ photo from the tracklist page, used as a background source in the [poster pipeline](library-layout.md#poster-layouts).

## What identification looks like

Interactive selection is the default mode. `identify` prints a ranked list of results and prompts you to pick the correct match or skip. See [identify: step-by-step](commands/identify.md#step-by-step-what-happens-when-you-run-identify) for a sample transcript and auto-mode behavior.

## Rate limiting and caching

CrateDigger waits between requests to avoid hitting 1001Tracklists rate limits (default: 5 seconds, configurable via `tracklists.delay_seconds`). The delay is smart: it tracks the time that has already elapsed since the last request and only sleeps for whatever remains. In interactive mode, if you spent more than the delay period choosing a match, no extra sleep is added.

If 1001Tracklists returns a rate-limit response, CrateDigger waits 30 seconds and retries. After the retry limit, it stops with a message asking you to solve a captcha on the 1001Tracklists website.

Two local caches make subsequent runs faster:

- **DJ cache:** canonical DJ names and aliases learned from tracklist pages. Used to standardize name casing and improve search scoring on later runs.
- **Source cache:** festival, venue, radio, and conference names. Used to classify tracklists by source type.

Each cache entry's actual lifetime jitters by ±20% around the configured base (see [Configuration: cache TTL](configuration.md#cache-ttl)), so a bulk first-run fill does not cause all entries to expire at the same time.

## See also

- [identify command](commands/identify.md): command reference, flags, interactive and auto selection, examples
- [Tag reference](tag-reference.md): every tag written into the MKV
- [Library layout](library-layout.md): sidecar files, NFO contents, poster layouts, artwork sources
- [Configuration](configuration.md): config keys for tracklists, caching, and credentials
