# CrateDigger

Festival set and concert library manager. CrateDigger organizes, enriches, and tags your DJ set and concert recordings into a clean, media-player-ready library.

## What you get

After running CrateDigger on a folder of recordings:

- Consistent folder structure and filenames, organized by artist, festival, year, or any combination
- Cover art and generated poster images for every recording and every folder
- NFO files that Kodi, Jellyfin, and Plex read to display title, artist, genre, and artwork
- Structured MKV metadata tags for any tag-aware tool
- Chapter markers (one per track) for navigation inside DJ sets, sourced from [1001Tracklists](https://www.1001tracklists.com/)
- MusicBrainz artist IDs, aligned with track-level performer tags

## Three-command workflow

```bash
# Match recordings against 1001Tracklists, embed chapter markers
cratedigger identify ~/Downloads/sets/

# Organize into a library with consistent folder and file names
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/

# Add artwork, posters, NFO files, and metadata tags
cratedigger enrich ~/Music/Library/
```

Or organize and enrich in one pass:

```bash
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/ --enrich
```

!!! note "1001Tracklists account (optional)"
    `identify` needs a free [1001Tracklists](https://www.1001tracklists.com/) account. Without one, skip straight to `organize` and `enrich`. You still get an organized library, artwork, posters, and NFO files built from filename parsing and embedded metadata. See [what you get with vs. without an account](tracklists.md#do-i-need-an-account).

## Install

**pipx (recommended):** installs CrateDigger into an isolated environment and puts `cratedigger` on your PATH.

```bash
pipx install git+https://github.com/Rouzax/CrateDigger.git
```

**pip** also works, for example inside a virtual environment:

```bash
pip install git+https://github.com/Rouzax/CrateDigger.git
```

See [Getting Started](getting-started.md) for required tools, upgrade commands, config setup, and the recommended yt-dlp download settings.

## Related projects

**[TrackSplit](https://rouzax.github.io/TrackSplit/)** is a sibling CLI that extracts chapter-based audio from your CrateDigger library into gapless, tagged FLAC albums for music servers like Jellyfin and Lyrion. TrackSplit reads CrateDigger's festival and artist config so canonical naming and MusicBrainz IDs stay consistent across your video and music libraries. See the [TrackSplit documentation](https://rouzax.github.io/TrackSplit/docs/) or [source on GitHub](https://github.com/Rouzax/TrackSplit).

## Documentation

| | |
|---|---|
| [Getting Started](getting-started.md) | Installation, required tools, first run |
| [identify](commands/identify.md) | Match tracklists, embed chapters |
| [organize](commands/organize.md) | Library layouts, move vs. copy, templates |
| [enrich](commands/enrich.md) | Artwork, posters, NFO, MBIDs |
| [audit-logos](commands/audit-logos.md) | Check festival logo coverage |
| [Configuration](configuration.md) | All config options |
| [Festivals](festivals.md) | Festival names, aliases, editions |
| [1001Tracklists](tracklists.md) | Account setup, caching, what you get |
| [Library layout](library-layout.md) | Every file CrateDigger writes and why |
| [Tag reference](tag-reference.md) | Every MKV tag CrateDigger writes |
| [Kodi Integration](kodi-integration.md) | JSON-RPC sync, path mapping |
| [FAQ](faq.md) | Common problems and troubleshooting |
