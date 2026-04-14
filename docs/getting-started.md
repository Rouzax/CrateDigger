# Getting Started

CrateDigger is a command-line tool that organizes your DJ set and concert recordings into a
clean library, then enriches them with artwork, track listings, and metadata.

## Before you start

### Python

CrateDigger requires Python 3.11 or newer.

Check your version:

```bash
python3 --version
```

### Required tools

CrateDigger relies on three external programs. Install them before running CrateDigger.

| Tool | What it does |
|------|-------------|
| **MediaInfo** | Reads video and audio file properties (duration, resolution, codec) |
| **FFmpeg** (includes ffprobe) | Probes media files and extracts thumbnail images |
| **MKVToolNix** (mkvpropedit, mkvextract, mkvmerge) | Reads and writes chapters and tags inside MKV video files |

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

If the tools are installed somewhere other than your system PATH, you can tell CrateDigger
where to find them. See [Configuration: Tool paths](configuration.md#tool-paths).

## Install CrateDigger

```bash
pip install git+https://github.com/Rouzax/CrateDigger.git
```

Verify it installed correctly:

```bash
cratedigger --help
```

### Optional: video frame sampling

By default, CrateDigger uses artwork that is already embedded inside your video files.
If a file has no embedded artwork, CrateDigger can extract a still frame from the video
to use as cover art instead. This also improves poster and NFO image quality for files
without embedded covers.

To enable this fallback, install the `vision` extra:

```bash
pip install "cratedigger[vision] @ git+https://github.com/Rouzax/CrateDigger.git"
```

This adds OpenCV, which does the frame extraction. Without it, files with no embedded
artwork simply won't have a thumbnail, and their posters may be lower quality or missing.

## Set up your config files

CrateDigger looks for your settings in a folder called `.cratedigger` inside your home directory:

| Platform | Path |
|----------|------|
| Linux / macOS | `~/.cratedigger/` |
| Windows | `C:\Users\YourName\.cratedigger\` |

You do not need to create a config file. CrateDigger has sensible built-in defaults for
everything. Create it only if you want to customize behavior.

To get a ready-to-edit starting point, download the example config:

=== "Linux / macOS"

    ```bash
    mkdir -p ~/.cratedigger
    curl -o ~/.cratedigger/config.json \
      https://raw.githubusercontent.com/Rouzax/CrateDigger/main/config.example.json
    ```

=== "Windows (PowerShell)"

    ```powershell
    New-Item -ItemType Directory -Force "$env:USERPROFILE\.cratedigger"
    Invoke-WebRequest `
      -Uri "https://raw.githubusercontent.com/Rouzax/CrateDigger/main/config.example.json" `
      -OutFile "$env:USERPROFILE\.cratedigger\config.json"
    ```

Or, if you have cloned the repository locally, copy from the repo root:

```bash
cp config.example.json ~/.cratedigger/config.json
```

The settings most users change first:

- **1001Tracklists credentials**: needed for the `identify` command's search
  functionality. Add your email and password under the `tracklists` section.
  See [Do I need an account?](tracklists.md#do-i-need-an-account) to understand what you
  gain and what still works without one.
- **fanart.tv personal API key**: optional. Speeds up artist artwork lookups.
  A built-in project key is used automatically as a fallback.
- **Default layout**: controls how CrateDigger names and arranges your library folders.

See [Configuration](configuration.md) for all options.

### Festival definitions

CrateDigger includes built-in knowledge of common festival names. To add your own
festivals or customize aliases, copy the example festivals file:

=== "Linux / macOS"

    ```bash
    curl -o ~/.cratedigger/festivals.json \
      https://raw.githubusercontent.com/Rouzax/CrateDigger/main/festivals.example.json
    ```

=== "Windows (PowerShell)"

    ```powershell
    Invoke-WebRequest `
      -Uri "https://raw.githubusercontent.com/Rouzax/CrateDigger/main/festivals.example.json" `
      -OutFile "$env:USERPROFILE\.cratedigger\festivals.json"
    ```

Or from a cloned repo:

```bash
cp festivals.example.json ~/.cratedigger/festivals.json
```

See [Festivals](festivals.md) for how to add entries and what the file format looks like.

## Preparing your recordings

CrateDigger works best with MKV files that have an embedded thumbnail. If you are
downloading sets from YouTube, the following yt-dlp command produces exactly the right
format:

=== "Windows (PowerShell)"

    ```powershell
    yt-dlp.exe -U --merge-output-format mkv --no-post-overwrites --embed-thumbnail `
      --convert-thumbnails png --windows-filenames --embed-chapters `
      --sponsorblock-mark all -P "$env:USERPROFILE\Downloads\sets" <YouTube URL>
    ```

=== "Linux / macOS"

    ```bash
    yt-dlp -U --merge-output-format mkv --no-post-overwrites --embed-thumbnail \
      --convert-thumbnails png --embed-chapters \
      --sponsorblock-mark all -P ~/Downloads/sets/ <YouTube URL>
    ```

What these flags do:

| Flag | Why it helps |
|------|-------------|
| `--merge-output-format mkv` | Produces MKV output, the format CrateDigger works best with |
| `--embed-thumbnail --convert-thumbnails png` | Embeds cover art directly in the file; CrateDigger uses this as the recording's artwork without needing the `vision` extra |
| `--embed-chapters` | Embeds any chapter markers YouTube already has (CrateDigger will replace these with full tracklist chapters from 1001Tracklists) |
| `--sponsorblock-mark all` | Marks sponsor segments as chapters, useful for navigation before identification |
| `--windows-filenames` | Sanitizes filenames to be safe on Windows |

The downloaded filename will contain the YouTube video ID in brackets (for example,
`Tiesto Live Miami 2026 [2EQGqEvLAuE].mkv`). CrateDigger automatically strips this ID
from the search query so it does not interfere with matching on 1001Tracklists.

## The three-step workflow

CrateDigger is designed around three commands you run in order.

### Step 1: Identify

Match your recordings against 1001Tracklists, embed chapter markers, and store tracklist metadata:

```bash
cratedigger identify ~/Downloads/sets/
```

**What this does:** CrateDigger scans every MKV and WEBM file in the folder. For each file,
it searches [1001Tracklists](https://www.1001tracklists.com) (a website that logs the tracks
DJs play during sets), shows you the best matches, and lets you pick the right one. Once you
confirm, CrateDigger embeds chapter markers directly into the file, one chapter per track,
along with track names, artist names, genres, and tracklist source details.

**For batch processing without prompts:** Add `--auto` to let CrateDigger pick the best
match automatically when it is confident enough:

```bash
cratedigger identify ~/Downloads/sets/ --auto
```

See the [identify command](commands/identify.md) for all options including how to provide
a tracklist URL directly.

### Step 2: Organize

Move files into a structured library with consistent folder names and filenames:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/
```

**What this does:** CrateDigger reads each file's metadata (from `identify`, or from the
filename if `identify` was skipped), classifies it as a festival set or concert recording,
then copies it into your output folder using your configured folder layout. Folder names and
filenames are standardized automatically.

After organizing, CrateDigger creates a `.cratedigger/` folder inside your library.
This marker is required before you can run `enrich`.

See the [organize command](commands/organize.md) for layout options, move vs. copy, and dry-run.

### Step 3: Enrich

Add artwork, posters, sidecar files, and metadata tags to your library:

```bash
cratedigger enrich ~/Music/Library/
```

**What this does:** For each file in your library, CrateDigger:

- Extracts or assigns cover art (from embedded MKV artwork, or a sampled video frame if the
  `vision` extra is installed)
- Downloads artist artwork from [fanart.tv](https://fanart.tv) (a community site with
  high-quality artist logos and backgrounds), if available
- Generates a poster image for each recording and each folder
- Writes an NFO file alongside each video. An NFO is a small XML file that media players
  like [Kodi](https://kodi.tv), Plex, and Jellyfin read to display title, artist, genre,
  and artwork.
- Embeds structured metadata tags into MKV files
- Resolves MusicBrainz IDs for artists when possible. [MusicBrainz](https://musicbrainz.org)
  is a community music encyclopedia that assigns permanent unique IDs to artists.

See the [enrich command](commands/enrich.md) for details on each operation and how to run
only specific parts.

### One-step organize + enrich

You can organize and enrich in a single command:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --enrich
```

## Without a 1001Tracklists account

You do not need a 1001Tracklists account to use CrateDigger. Skip the `identify` step and
run organize and enrich directly:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --enrich
```

CrateDigger will build your library using metadata from your filenames and any tags already
embedded in your video files. Your [festivals.json](festivals.md) aliases help it recognize
festival names in filenames, and your [artists.json](configuration.md#artist-aliases) aliases
help normalize artist names.

**What you still get:**

- An organized library with consistent folder and file names
- Cover art and poster images
- Artist artwork from fanart.tv
- NFO files for Kodi, Plex, and Jellyfin
- Structured MKV metadata tags

**What requires a 1001Tracklists account:**

- Chapter markers (track-by-track navigation inside your recordings)
- Per-track metadata (track titles, labels, and genres from the tracklist)
- Album-level multi-artist credits
- Stage, venue, and event taxonomy
- DJ artwork from 1001Tracklists

For the full feature comparison, see [Do I need an account?](tracklists.md#do-i-need-an-account).

## What to do next

- [identify](commands/identify.md): detailed options for matching and embedding
- [organize](commands/organize.md): layouts, templates, move vs. copy, dry-run
- [enrich](commands/enrich.md): artwork, posters, MBIDs, selective operations
- [Configuration](configuration.md): all config settings explained
- [Tracklists integration](tracklists.md): 1001Tracklists account setup and what it adds
- [Festivals](festivals.md): how to add and customize festival definitions
