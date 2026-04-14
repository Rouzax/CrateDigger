# Getting Started

## Prerequisites

CrateDigger requires Python 3.11 or newer, plus several media tools.

### Required tools

| Tool | Purpose |
|------|---------|
| **MediaInfo** | Extract media metadata (duration, codec, resolution) |
| **FFmpeg** (includes ffprobe) | Probe media files, extract thumbnails |
| **MKVToolNix** (mkvpropedit, mkvextract, mkvmerge) | Read and write MKV tags, chapters |

### Install dependencies

=== "Ubuntu / Debian"

    ```bash
    sudo apt install mediainfo ffmpeg mkvtoolnix
    ```

=== "macOS (Homebrew)"

    ```bash
    brew install media-info ffmpeg mkvtoolnix
    ```

=== "Windows (Scoop)"

    ```powershell
    scoop install mediainfo ffmpeg mkvtoolnix
    ```

=== "Windows (manual)"

    Download and install each tool, then add their directories to your system PATH:

    - [MediaInfo](https://mediaarea.net/en/MediaInfo/Download)
    - [FFmpeg](https://ffmpeg.org/download.html)
    - [MKVToolNix](https://mkvtoolnix.download/downloads.html)

If the tools are not on your PATH, you can set explicit paths in the [configuration](configuration.md#tool-paths).

## Install CrateDigger

```bash
pip install git+https://github.com/Rouzax/CrateDigger.git
```

For poster generation with advanced image processing (optional):

```bash
pip install "cratedigger[vision] @ git+https://github.com/Rouzax/CrateDigger.git"
```

Verify the installation:

```bash
cratedigger --help
```

## First run

### 1. Copy the example config

```bash
mkdir -p ~/.cratedigger
cp config.example.json ~/.cratedigger/config.json
```

Edit `~/.cratedigger/config.json` to add your credentials and preferences. At minimum, you may want to:

- **1001Tracklists credentials** (required for `identify`, optional overall). Set email and password to fetch tracklists. Without them, the `identify` step is skipped; the rest of the pipeline still works from filename parsing and embedded metadata. See [Do I need an account?](tracklists.md#do-i-need-an-account) for what's gained with vs. without.
- **fanart.tv personal API key** (optional). Speeds up artist artwork lookups. A built-in project key is used as a fallback.
- **Default layout** — folder structure used by `organize`.

See [Configuration](configuration.md) for all available options.

### 2. Copy the example festivals file

```bash
cp festivals.example.json ~/.cratedigger/festivals.json
```

This provides a starting set of festival definitions with aliases, editions, and colors. See [Festivals](festivals.md) for details.

## Recommended workflow

### Step 1: Identify

Match your recordings against 1001Tracklists to embed chapter markers and metadata:

```bash
cratedigger identify ~/Downloads/sets/
```

This searches 1001Tracklists for each MKV/WEBM file, lets you pick the correct tracklist, and embeds chapter markers directly into the file. Use `--auto` for batch processing without prompts.

### Step 2: Organize

Move files into a structured library:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/
```

This classifies each file as a festival set or concert recording, then copies it into the library using your configured folder layout and filename template.

### Step 3: Enrich

Add artwork, posters, NFO files, and tags:

```bash
cratedigger enrich ~/Music/Library/
```

This generates cover art, looks up artist fanart, creates poster images, writes NFO metadata files, and embeds MKV tags.

### One-step organize + enrich

You can combine organizing and enriching in a single pass:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --enrich
```

### Without a 1001Tracklists account

If you don't want a 1001TL account, skip step 1 and run organize + enrich directly:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --enrich
```

The resulting library uses filename parsing (via your `festivals.json` aliases and `artists.json` rules) and embedded MKV metadata. You keep the organized folder tree, NFO files, posters, cover art, and artist artwork from fanart.tv. You lose chapter markers, per-track metadata, album-level multi-artist tags, stage/venue/event taxonomy, and DJ artwork from 1001TL. See [Do I need an account?](tracklists.md#do-i-need-an-account) for the full matrix.
