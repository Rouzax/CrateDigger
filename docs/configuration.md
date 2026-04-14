# Configuration

CrateDigger works without a config file, using sensible defaults for everything. Create a config file only to override specific settings.

## Config file locations

CrateDigger merges configuration from three layers (later layers override earlier ones):

1. **Built-in defaults**: Always present, covers all settings
2. **User config**: `~/.cratedigger/config.json`
3. **Library config**: `<library>/.cratedigger/config.json`

You can also pass an explicit config path with the `--config` flag on any command.

### Getting started

Copy the example config as your starting point:

```bash
mkdir -p ~/.cratedigger
cp config.example.json ~/.cratedigger/config.json
```

Only include settings you want to override. Omitted settings fall back to built-in defaults.

## Config sections

### Default layout

```json
{
    "default_layout": "artist_flat"
}
```

Sets the folder layout used by the organize command. Available layouts: `artist_flat`, `festival_flat`, `artist_nested`, `festival_nested`. See [Organize layouts](commands/organize.md#layouts) for details.

### Layouts

```json
{
    "layouts": {
        "artist_flat": {
            "festival_set": "{artist}",
            "concert_film": "{artist}"
        },
        "festival_flat": {
            "festival_set": "{festival}{ edition}",
            "concert_film": "{artist}"
        },
        "artist_nested": {
            "festival_set": "{artist}/{festival}{ edition}/{year}",
            "concert_film": "{artist}/{year} - {title}"
        },
        "festival_nested": {
            "festival_set": "{festival}{ edition}/{year}/{artist}",
            "concert_film": "{artist}/{year} - {title}"
        }
    }
}
```

Folder path templates for each layout and content type. Uses [collapsing token syntax](commands/organize.md#template-syntax).

### Filename templates

```json
{
    "filename_templates": {
        "festival_set": "{year} - {artist} - {festival}{ edition}{ [stage]}{ - set_title}",
        "concert_film": "{artist} - {title}{ (year)}"
    }
}
```

Templates for generated filenames. The original file extension is preserved automatically.

### Content type rules

```json
{
    "content_type_rules": {
        "force_concert": [
            "Adele/*",
            "Coldplay/*",
            "U2/*"
        ],
        "force_festival": []
    }
}
```

Glob patterns (relative to the source root) that force a file to be classified as `concert_film` or `festival_set`, bypassing automatic classification.

### Skip patterns

```json
{
    "skip_patterns": ["*/BDMV/*", "Dolby*"]
}
```

Glob patterns for paths to skip during scanning. Matched against the relative path (forward slashes).

### Media extensions

```json
{
    "media_extensions": {
        "video": [".mp4", ".mkv", ".webm", ".avi", ".mov", ".m2ts", ".ts"],
        "audio": [".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg", ".opus"]
    }
}
```

File extensions recognized as media files, grouped by type.

### Fallback values

```json
{
    "fallback_values": {
        "unknown_artist": "Unknown Artist",
        "unknown_festival": "_Needs Review",
        "unknown_year": "Unknown Year",
        "unknown_title": "Unknown Title"
    }
}
```

Placeholder values used in templates when metadata is missing.

### Poster settings

```json
{
    "poster_settings": {
        "artist_background_priority": ["dj_artwork", "fanart_tv", "gradient"],
        "festival_background_priority": ["curated_logo", "gradient"],
        "year_background_priority": ["gradient"]
    }
}
```

Priority chains for poster background image selection. CrateDigger tries each source in order and uses the first one available.

| Source | Description |
|--------|-------------|
| `dj_artwork` | DJ photo from 1001Tracklists (embedded during identify) |
| `fanart_tv` | Artist artwork from fanart.tv |
| `curated_logo` | Hand-placed festival logo (see [Audit Logos](commands/audit-logos.md)) |
| `gradient` | Solid gradient fallback (always available) |

### Tracklists

```json
{
    "tracklists": {
        "email": "",
        "password": "",
        "delay_seconds": 5,
        "chapter_language": "eng",
        "auto_select": false,
        "genre_top_n": 5
    }
}
```

Settings for 1001Tracklists integration. See [1001Tracklists](tracklists.md) for details.

| Key | Description |
|-----|-------------|
| `email` | 1001Tracklists account email |
| `password` | 1001Tracklists account password |
| `delay_seconds` | Delay between API requests in seconds (default: 5) |
| `chapter_language` | Language code for chapter names (default: "eng") |
| `auto_select` | Default auto-select behavior (overridden by `--auto` flag) |
| `genre_top_n` | Cap on the set-level `CRATEDIGGER_1001TL_GENRES` tag: keep only the top-N most frequent per-track genres (default: 5). Ties broken by first-appearance order so the result is deterministic. Set to `0` to disable the cap and write every per-track genre. |

Credentials can also be set via environment variables `TRACKLISTS_EMAIL` and `TRACKLISTS_PASSWORD`.

### Fanart

```json
{
    "fanart": {
        "personal_api_key": "",
        "enabled": true
    }
}
```

Settings for fanart.tv artwork lookups. A project API key is built into CrateDigger. Adding your personal API key provides faster cache updates.

Get a personal API key at [fanart.tv](https://fanart.tv/get-an-api-key/).

The personal API key can also be set via the `FANART_PERSONAL_API_KEY` environment variable. The project API key can be overridden with `FANART_PROJECT_API_KEY`.

### Kodi

```json
{
    "kodi": {
        "enabled": false,
        "host": "localhost",
        "port": 8080,
        "username": "kodi",
        "password": ""
    }
}
```

Kodi JSON-RPC settings for automatic library sync. See [Kodi Integration](kodi-integration.md) for setup instructions.

All Kodi settings can be overridden with environment variables: `KODI_HOST`, `KODI_PORT`, `KODI_USERNAME`, `KODI_PASSWORD`.

### NFO settings

```json
{
    "nfo_settings": {
        "genre_festival": "Electronic",
        "genre_concert": "Live"
    }
}
```

Genre tags written into NFO files. `genre_festival` is used for festival sets, `genre_concert` for concert recordings.

### Tool paths

```json
{
    "tool_paths": {
        "mediainfo": null,
        "ffprobe": null,
        "mkvextract": null,
        "mkvpropedit": null,
        "mkvmerge": null
    }
}
```

Explicit paths to external tools. Set these if the tools are not on your system PATH. Use `null` for auto-detection.

### Cache TTL

```json
{
    "cache_ttl": {
        "mbid_days": 90,
        "dj_days": 90,
        "source_days": 365,
        "images_days": 90
    }
}
```

Base time-to-live settings for various caches, in days. After a cache entry's TTL expires, cached data is refreshed on the next lookup.

Values are *base* TTLs: each cache entry's actual lifetime jitters by ±20% around the base (so a `dj_days: 90` entry lives 72-108 days). This prevents synchronised expiry after a bulk first-run cache fill, which would otherwise cause a thundering-herd re-fetch on a single day months later.

| Key | Description |
|-----|-------------|
| `mbid_days` | MusicBrainz ID cache (default: 90) |
| `dj_days` | DJ name and alias cache (default: 90) |
| `source_days` | Source/venue name cache (default: 365) |
| `images_days` | Downloaded images cache (default: 90) |

## Artist MBID override file

`~/.cratedigger/artist_mbids.json` is a user-curated flat JSON map from artist display name to MusicBrainz artist ID. It is consulted first by both the `chapter_artist_mbids` and `album_artist_mbids` enrich operations, ahead of the auto cache and any live MusicBrainz lookup. A pin here applies to both per-chapter and album-level artist MBID tags, since MusicBrainz IDs are properties of the artist, not of the tag context.

```json
{
    "Afrojack": "3abb6f9f-5b6a-4f1f-8a2d-1111111111aa",
    "Oliver Heldens": "6e7dde91-4c02-47ea-a2b4-2222222222bb"
}
```

| Property | Value |
|----------|-------|
| Path | `~/.cratedigger/artist_mbids.json` |
| Format | Flat JSON object, `{"Artist Name": "mbid-uuid"}` |
| Matching | Case-insensitive on the artist name |
| Precedence | Checked before `mbid_cache.json` and before any live MusicBrainz search |
| Expiry | Never expires |
| Written by code | No; CrateDigger never writes to this file |

**Distinction from `mbid_cache.json`**: `mbid_cache.json` is disposable, TTL-bound (see `cache_ttl.mbid_days`), and populated automatically by CrateDigger from MusicBrainz search results. It can be deleted at any time and will refill. `artist_mbids.json` is your curated override list, and is the correct place to record MBIDs for artists that MusicBrainz searches misidentify or fail to find.

See [Enrich / Chapter artist MBIDs](commands/enrich.md#chapter-artist-mbids-chapter_artist_mbids) for the full fix loop.

## Environment variables

| Variable | Overrides |
|----------|-----------|
| `TRACKLISTS_EMAIL` | `tracklists.email` |
| `TRACKLISTS_PASSWORD` | `tracklists.password` |
| `FANART_PROJECT_API_KEY` | `fanart.project_api_key` |
| `FANART_PERSONAL_API_KEY` | `fanart.personal_api_key` |
| `KODI_HOST` | `kodi.host` |
| `KODI_PORT` | `kodi.port` |
| `KODI_USERNAME` | `kodi.username` |
| `KODI_PASSWORD` | `kodi.password` |
