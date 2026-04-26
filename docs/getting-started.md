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

**pipx (recommended for end users):** pipx installs CrateDigger into an isolated environment and puts the `cratedigger` command on your PATH automatically.

```bash
pipx install git+https://github.com/Rouzax/CrateDigger.git
```

Upgrade later with:

```bash
pipx upgrade cratedigger
```

**pip (user site or venv):** If you prefer pip or are working inside a virtual environment:

```bash
pip install git+https://github.com/Rouzax/CrateDigger.git
```

Upgrade later with:

```bash
pip install --upgrade git+https://github.com/Rouzax/CrateDigger.git
```

Verify the installation:

```bash
cratedigger --version
```

This prints the installed version and exits. For a quick look at all available subcommands, run:

```bash
cratedigger --help
```

Use `--version` as the fast confirmation that the install worked. Use `--help` when you want to browse the full command tree.

### Verify your environment with `--check`

After installing CrateDigger, run `--check` to confirm that all required external tools, config files, credentials, and Python packages are present and reachable:

```bash
cratedigger --check
```

CrateDigger prints a grouped report with a status marker for each item:

- `✓` the item is present and working
- `!` the item is missing or unconfigured, but optional
- `✗` the item is missing and required
- `~` informational (using built-in defaults or skipped because it is not configured)

A summary line at the end reports `All checks passed.` when nothing is wrong, or counts the errors and warnings otherwise.

The command exits with code 0 if all required checks pass. Warnings (optional items missing) do not affect the exit code. The command exits with code 1 if any required tool or Python package is absent.

Nothing is processed: `--check` reads your environment and exits without touching any media files or your library.

Use it after a fresh install to confirm the setup is complete, after updating a [config file](configuration.md) to verify the new paths are valid, or in CI to validate the environment before a scheduled run.

### Optional: video frame sampling

By default, CrateDigger reads artwork that is already embedded in your video files. Files
without embedded artwork get no thumbnail, and their posters and NFO images are lower
quality or missing as a result.

The `vision` extra adds a fallback: when a file has no embedded artwork, CrateDigger
extracts a still frame from the video and uses that as cover art instead. This is an
opt-in feature, not the default behaviour.

To include it at install time, use whichever command matches the install path you chose
in the "Install CrateDigger" section above:

**pipx**
```bash
pipx install "cratedigger[vision] @ git+https://github.com/Rouzax/CrateDigger.git"
```

**pip**
```bash
pip install "cratedigger[vision] @ git+https://github.com/Rouzax/CrateDigger.git"
```

The extra pulls in OpenCV, which is the library that scores and selects the frame.

## Set up your config files

CrateDigger stores your settings in a `CrateDigger` folder. Where that folder lives depends on your platform:

| Platform | Config location |
|----------|----------------|
| Linux | `~/CrateDigger/config.toml` |
| macOS | `~/CrateDigger/config.toml` |
| Windows | `Documents\CrateDigger\config.toml` (your Documents folder) |

You do not need to create a config file. CrateDigger has sensible built-in defaults for
everything. Create it only if you want to customize behavior.

To get a ready-to-edit starting point, download the example config:

=== "Linux / macOS"

    ```bash
    mkdir -p ~/CrateDigger
    curl -o ~/CrateDigger/config.toml \
      https://raw.githubusercontent.com/Rouzax/CrateDigger/main/config.example.toml
    ```

=== "Windows (PowerShell)"

    ```powershell
    New-Item -ItemType Directory -Force "$env:USERPROFILE\Documents\CrateDigger"
    Invoke-WebRequest `
      -Uri "https://raw.githubusercontent.com/Rouzax/CrateDigger/main/config.example.toml" `
      -OutFile "$env:USERPROFILE\Documents\CrateDigger\config.toml"
    ```

Or, if you have cloned the repository locally, copy from the repo root:

=== "Linux / macOS"

    ```bash
    cp config.example.toml ~/CrateDigger/config.toml
    ```

=== "Windows (PowerShell)"

    ```powershell
    Copy-Item config.example.toml "$env:USERPROFILE\Documents\CrateDigger\config.toml"
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
festivals or customize aliases, copy the example festivals file to the same folder as
your config:

=== "Linux / macOS"

    ```bash
    curl -o ~/CrateDigger/festivals.json \
      https://raw.githubusercontent.com/Rouzax/CrateDigger/main/places.example.json
    ```

=== "Windows (PowerShell)"

    ```powershell
    Invoke-WebRequest `
      -Uri "https://raw.githubusercontent.com/Rouzax/CrateDigger/main/places.example.json" `
      -OutFile "$env:USERPROFILE\Documents\CrateDigger\festivals.json"
    ```

Or from a cloned repo:

=== "Linux / macOS"

    ```bash
    cp places.example.json ~/CrateDigger/festivals.json
    ```

=== "Windows (PowerShell)"

    ```powershell
    Copy-Item places.example.json "$env:USERPROFILE\Documents\CrateDigger\festivals.json"
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
