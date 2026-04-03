# Enrich

Add artwork, posters, NFO metadata files, and MKV tags to your library.

## Usage

```bash
cratedigger enrich <library> [options]
```

The `<library>` argument must point to an existing CrateDigger library (a folder containing a `.cratedigger` marker created by the organize command).

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--only <ops>` | | Comma-separated list of operations to run |
| `--regenerate` | | Regenerate artifacts even if they already exist |
| `--kodi-sync` | | Notify Kodi to refresh updated items |
| `--config <path>` | | Path to config.json |
| `--quiet` | `-q` | Suppress per-file progress |
| `--verbose` | `-v` | Show detailed progress and decisions |
| `--debug` | | Show cache hits, retries, and internal mechanics |

### The --only flag

Use `--only` to run a subset of operations. Valid values:

| Value | Operation |
|-------|-----------|
| `nfo` | Generate NFO metadata files |
| `art` | Extract or set cover art |
| `fanart` | Look up artist artwork on fanart.tv |
| `posters` | Generate poster images |
| `tags` | Write MKV tags |

Combine multiple values with commas:

```bash
cratedigger enrich ~/Music/Library/ --only nfo,art
cratedigger enrich ~/Music/Library/ --only posters,tags
```

When `--only` is omitted, all operations run.

## Operations

### Cover art (`art`)

Extracts or assigns cover art for each media file. The cover image is placed alongside the media file.

### Fanart (`fanart`)

Looks up artist artwork on [fanart.tv](https://fanart.tv) using the MusicBrainz ID. Downloads artist backgrounds and thumbnails for use in poster generation and Kodi display.

Requires `fanart.enabled: true` in your config (enabled by default). A built-in project API key is included. You can optionally add your own personal API key for faster cache updates.

### Posters (`posters`)

Generates poster images for each media file and album-level poster images (`folder.jpg`) for each folder. Poster backgrounds are selected based on priority chains defined in `poster_settings`:

- **Artist backgrounds**: dj_artwork (from 1001Tracklists), fanart_tv, gradient fallback
- **Festival backgrounds**: curated_logo, gradient fallback
- **Year backgrounds**: gradient fallback

Album posters are generated per folder and use a festival logo if available. Use the [audit-logos](audit-logos.md) command to check logo coverage.

### NFO files (`nfo`)

Creates Kodi-compatible NFO metadata files alongside each media file. NFO files include title, artist, year, genre, and other metadata. Genre defaults are configurable via `nfo_settings`.

### MKV tags (`tags`)

Writes structured MKV tags into each file, including artist, title, date, and other metadata fields extracted during analysis and identification.

## Examples

Enrich an entire library with all operations:

```bash
cratedigger enrich ~/Music/Library/
```

Only generate NFO files:

```bash
cratedigger enrich ~/Music/Library/ --only nfo
```

Regenerate posters even if they already exist:

```bash
cratedigger enrich ~/Music/Library/ --only posters --regenerate
```

Enrich and sync with Kodi:

```bash
cratedigger enrich ~/Music/Library/ --kodi-sync
```
