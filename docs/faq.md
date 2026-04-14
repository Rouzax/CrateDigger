# FAQ

---

## General

### A required tool is not found

CrateDigger relies on three external tools. If any of them is missing or not on your system PATH, you will see an error on startup.

| Tool | Install |
|------|---------|
| **MediaInfo** | `sudo apt install mediainfo` / `brew install media-info` / `scoop install mediainfo` |
| **FFmpeg** (includes ffprobe) | `sudo apt install ffmpeg` / `brew install ffmpeg` / `scoop install ffmpeg` |
| **MKVToolNix** (mkvpropedit, mkvextract, mkvmerge) | `sudo apt install mkvtoolnix` / `brew install mkvtoolnix` / `scoop install mkvtoolnix` |

If the tools are installed but not on your PATH (for example, a custom install location), tell CrateDigger where to find them in `~/.cratedigger/config.json`:

```json
{
    "tool_paths": {
        "mediainfo": "/usr/local/bin/mediainfo",
        "ffprobe": "/usr/local/bin/ffprobe",
        "mkvpropedit": "/usr/local/bin/mkvpropedit",
        "mkvextract": "/usr/local/bin/mkvextract",
        "mkvmerge": "/usr/local/bin/mkvmerge"
    }
}
```

See [getting started](getting-started.md#required-tools) for full installation instructions.

### CrateDigger skips some of my files

CrateDigger only processes files with recognized media extensions. The defaults include `.mp4`, `.mkv`, `.webm`, `.avi`, `.mov`, `.m2ts`, `.ts` for video and common audio formats. Add extensions in the `media_extensions` config section if your files use something else.

Also check `skip_patterns` in your config. Files matching any skip pattern are excluded. The defaults skip `*/BDMV/*` (Blu-ray disc structures) and `Dolby*` (demo content).

### A file is classified as the wrong type

CrateDigger classified a concert as a festival set, or vice versa. Force the correct classification using path rules in `content_type_rules`:

```json
{
    "content_type_rules": {
        "force_concert": ["Coldplay/*", "Pink Floyd/*"],
        "force_festival": ["*/Ultra Miami/*"]
    }
}
```

Each rule is matched against the file's path relative to the source root. `Coldplay/*` matches any file directly inside a `Coldplay` folder. See [Configuration: content type rules](configuration.md#content-type-rules) for more examples.

---

## identify

### "Error: credentials required"

Your 1001Tracklists email and password are not configured. Add them to `~/.cratedigger/config.json`:

```json
{
    "tracklists": {
        "email": "your@email.com",
        "password": "your-password"
    }
}
```

Or set them as environment variables:

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

### No results found for a file

CrateDigger builds the search query from the filename only. If the filename does not contain recognizable artist and event names, the search may return no results. Try:

- Pass a manual search query: `cratedigger identify recording.mkv --tracklist "Tiesto Ultra Miami 2025"`
- Pass the tracklist URL directly if you find it on 1001Tracklists: `cratedigger identify recording.mkv --tracklist "https://www.1001tracklists.com/tracklist/..."`
- Rename the file to include the artist name and festival name before running identify

### A file is skipped in auto mode

Auto mode requires the top result to score 150 or higher and the gap to the second result to be at least 20. If either threshold is not met, the file is skipped rather than guessing.

To handle skipped files, run the same folder interactively (without `--auto`) and pick manually:

```bash
cratedigger identify ~/Downloads/sets/
```

For files that are consistently hard to match automatically, use `--tracklist` to provide the URL directly.

### Chapters are not embedding

Chapter embedding requires:

1. The file must be MKV or WEBM format. MP4 and other formats are not supported. Convert with FFmpeg or MKVToolNix if needed.
2. `mkvpropedit` must be installed and on your PATH.
3. The matched tracklist must have at least 2 tracks with timing data. Single-track or unresolved tracklists are skipped because they provide no chapter navigation value.

### CrateDigger is rate-limited by 1001Tracklists

If 1001Tracklists returns a rate-limit response, CrateDigger waits 30 seconds and retries. If the retry also fails, it stops with a message asking you to solve a captcha at [1001tracklists.com](https://www.1001tracklists.com) in your browser. After solving the captcha, re-run identify.

Increase the delay between files to reduce the chance of hitting rate limits: set `tracklists.delay_seconds` in your config (default: 5 seconds).

### identify updated but enrich still shows old metadata

After re-running `identify` to pick up updated tracklist data, run `enrich` again to apply the new metadata to your NFO files, tags, and posters:

```bash
cratedigger enrich ~/Music/Library/ --regenerate
```

`--regenerate` forces enrich to overwrite existing artifacts with the newly embedded data.

---

## organize

### "--dry-run and --move cannot be used together"

These two flags are mutually exclusive. Use `--dry-run` first to preview what would happen, then run again with `--move` (without `--dry-run`) to actually move the files.

### "not a CrateDigger library" after organize

If `enrich` says the folder is not a CrateDigger library, check that `organize` completed successfully. It creates the `.cratedigger/` marker folder that `enrich` requires. If you pointed `enrich` at a subfolder rather than the library root, point it at the root instead.

---

## enrich

### "not a CrateDigger library"

The folder you passed to `enrich` does not have a `.cratedigger/` marker. Run `organize` on your library first:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/
cratedigger enrich ~/Music/Library/
```

### No thumbnail is produced for some files

CrateDigger tries three sources for cover art, in order:

1. Embedded artwork in the MKV file (embedded by yt-dlp with `--embed-thumbnail`)
2. A sampled video frame (requires the `vision` extra)
3. A generated gradient image (always available as a last resort)

If you are getting gradient thumbnails and want actual artwork, either embed a thumbnail when downloading (see [getting started: preparing your recordings](getting-started.md#preparing-your-recordings)) or install the `vision` extra:

```bash
pip install "cratedigger[vision] @ git+https://github.com/Rouzax/CrateDigger.git"
```

### Posters are not generated for some files

The per-video poster (`{stem}-poster.jpg`) requires `{stem}-thumb.jpg` to exist first. If you ran `--only posters` without running `art` first, no thumb exists yet. Either run the full enrich (without `--only`) so `art` runs before `posters`, or run them in sequence:

```bash
cratedigger enrich ~/Music/Library/ --only art
cratedigger enrich ~/Music/Library/ --only posters
```

### Artist artwork from fanart.tv is not downloading

Fanart.tv artwork requires a MusicBrainz ID to be resolved for the artist. If `fanart` runs before `chapter_artist_mbids`, or if the artist's MBID has not been resolved yet, the lookup is skipped.

Run `chapter_artist_mbids` first to resolve MBIDs, then rerun enrich:

```bash
cratedigger enrich ~/Music/Library/ --only chapter_artist_mbids
cratedigger enrich ~/Music/Library/ --only fanart
```

If the artist still has no MBID after that, they may not be in the MusicBrainz database or the search may be returning the wrong result. Add the correct MBID to `~/.cratedigger/artist_mbids.json` manually:

```json
{
    "Artist Name": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

Find the correct MBID at [musicbrainz.org](https://musicbrainz.org).

### MusicBrainz IDs are not resolving for some artists

CrateDigger looks up MBIDs in this order: your override file (`~/.cratedigger/artist_mbids.json`), the auto cache, then a live MusicBrainz search. If an artist is not resolving:

1. Check if the search is returning the wrong artist (a name collision). Run with `--verbose` to see what MusicBrainz returns.
2. Look up the correct MBID at [musicbrainz.org](https://musicbrainz.org) and add it to your override file:

```json
{
    "Afrojack": "3abb6f9f-5b6a-4f1f-8a2d-1111111111aa"
}
```

3. Rerun (no `--regenerate` needed):

```bash
cratedigger enrich ~/Music/Library/ --only chapter_artist_mbids,album_artist_mbids
```

CrateDigger detects that the resolved ID has changed and writes the update automatically.

See [Configuration: artist MBID override file](configuration.md#artist-mbid-override-file) for details.

### Festival folder posters show a plain gradient instead of a logo

Add a curated logo for the festival and regenerate:

1. Find out which festivals are missing logos: `cratedigger audit-logos ~/Music/Library/`
2. Place a logo file at the path the command suggests (for example, `~/.cratedigger/festivals/Tomorrowland/logo.png`)
3. Regenerate the folder posters:

```bash
cratedigger enrich ~/Music/Library/ --only posters --regenerate
```

See [audit-logos](commands/audit-logos.md) and [library layout: festival logos](library-layout.md#festival-logos) for supported formats and placement paths.

---

## fanart.tv

### Fanart lookups fail or return no images

Requirements for fanart.tv lookups:

- `fanart.enabled` must be `true` in your config (this is the default)
- The artist must have a MusicBrainz ID resolved. Run `--only chapter_artist_mbids` first if MBIDs are missing.
- A built-in project API key is included. If you are being rate-limited on large libraries, add your own personal key from [fanart.tv/get-an-api-key](https://fanart.tv/get-an-api-key/) to `fanart.personal_api_key` in your config.

Run with `--verbose` to see the lookup process and any errors.

### Fanart images are stale or outdated

The fanart cache expires after the number of days configured in `cache_ttl.images_days` (default: 90 days, with ±20% jitter per entry). To force a fresh download for all artists, delete the artist cache folder and rerun:

```bash
rm -rf ~/.cratedigger/artists/
cratedigger enrich ~/Music/Library/ --only fanart
```

---

## Kodi

### "Kodi sync failed: connection refused"

Kodi is not running, or the JSON-RPC web server is not enabled. Check **Settings** > **Services** > **Control** in Kodi and verify that **Allow remote control via HTTP** is on. Also confirm that the host and port in your config match.

### "Kodi sync failed: 401 Unauthorized"

The username or password does not match Kodi's web server credentials. Check the `kodi.username` and `kodi.password` values in your config against the Kodi settings.

### Items are not updating in Kodi after a sync

The library path that Kodi uses may not match the path CrateDigger is using. If they differ (for example, Kodi accesses the library over a network share while CrateDigger uses a local path), configure path mapping in your `kodi` config:

```json
{
    "kodi": {
        "path_mapping": {
            "local": "/home/user/Music/Library/",
            "kodi": "smb://server/music/Library/"
        }
    }
}
```

See [Kodi integration: path mapping](kodi-integration.md#path-mapping) for details.

### Sync runs but nothing changes in Kodi

CrateDigger only sends a refresh for files that had actual changes in that run. If all artifacts were already up to date (skipped), no sync request is sent. Use `--regenerate` to force re-creation of artifacts, which will trigger a sync. Run with `--debug` to confirm whether the sync pathway fired.
