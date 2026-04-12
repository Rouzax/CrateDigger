# CrateDigger

Festival set and concert library manager. CrateDigger organizes, enriches, and tags your media files with artwork, metadata, and chapter markers.

## What it does

CrateDigger takes a collection of festival sets and concert recordings and turns them into a well-organized, richly tagged media library. It handles everything from matching tracklists and embedding chapter markers to generating poster artwork and syncing with Kodi.

## Three-command workflow

CrateDigger follows a simple pipeline:

1. **[Identify](commands/identify.md)**: Match recordings against 1001Tracklists, embed chapter markers and metadata tags into MKV files.
2. **[Organize](commands/organize.md)**: Move or copy files into a structured library with smart folder layouts and consistent filenames.
3. **[Enrich](commands/enrich.md)**: Add cover art, fanart, poster images, NFO files, and MKV tags to your library.

You can run each step independently, or chain them together. The organize command can optionally run enrichment in a single pass with `--enrich`.

## Quick start

```bash
# Install from GitHub
pip install git+https://github.com/Rouzax/CrateDigger.git

# Identify tracklists and embed chapters
cratedigger identify ~/Downloads/sets/

# Organize into a library
cratedigger organize ~/Downloads/sets/ --output ~/Music/Library/

# Enrich with artwork and metadata
cratedigger enrich ~/Music/Library/
```

See the [Getting Started](getting-started.md) guide for detailed setup instructions.

## Additional tools

- **[Audit Logos](commands/audit-logos.md)**: Check which festivals in your library have curated logo artwork available for poster generation.

## Related projects

- **[TrackSplit](https://github.com/Rouzax/TrackSplit)**: A sibling CLI that extracts chapter-based audio from your video library into gapless, tagged FLAC albums for music servers like Jellyfin and Lyrion. TrackSplit reads CrateDigger's festival and artist config, so canonical naming and MusicBrainz IDs stay consistent across your video and music libraries.

## Learn more

- [Configuration](configuration.md): Full reference for all config options
- [Festival Database](festivals.md): How festivals are defined, matched, and customized
- [1001Tracklists Integration](tracklists.md): Account setup, searching, and chapter embedding
- [Kodi Integration](kodi-integration.md): Automatic library sync with Kodi
- [FAQ](faq.md): Common questions and troubleshooting
