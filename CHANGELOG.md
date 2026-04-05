# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.9.1] - 2026-04-05

### Added

- NFO files now emit multiple `<artist>` elements for B2B/collaborative sets
- Individual artist `<tag>` elements in NFOs for Kodi smart playlist filtering
- DJ group member expansion in NFO tags via DJ cache reverse-lookup (e.g. a Gaia set tags Armin van Buuren)
- Curated MKV DESCRIPTION tag replacing raw yt-dlp YouTube descriptions with structured metadata (artist, stage, festival, country, source type, edition)
- New MKV tags `CRATEDIGGER_1001TL_COUNTRY` and `CRATEDIGGER_1001TL_SOURCE_TYPE` embedded during chapter writing
- `MediaFile.artists` field carrying the full resolved artist list from pipe-separated 1001TL tag
- `DjCache.derive_group_members()` for group-to-member reverse lookups

## [0.9.0] - 2026-04-03

First public release.

### Added

- Intelligent content classification: automatic detection of festival sets vs concert films
- File organization with four built-in folder layouts (artist_flat, festival_flat, artist_nested, festival_nested)
- Smart filename templates with Sonarr-style collapsing tokens for optional fields
- 1001Tracklists integration: search, match, and embed tracklist metadata and chapter markers
- DJ artwork extraction from 1001Tracklists profiles
- MediaInfo and ffprobe-based metadata extraction and analysis
- Cover art extraction from video files with frame sampling fallback
- fanart.tv integration for HD ClearLOGOs and artist fanart via MusicBrainz lookup
- Professional poster generation: set posters (artist photo + metadata) and album posters (festival logo + gradient)
- Kodi NFO file generation (musicvideo XML standard) with genre, festival, and content-type tags
- Kodi JSON-RPC sync with selective library refresh and automatic path mapping
- MKV tag embedding with safe extract-merge-write workflow
- Festival database with 30+ pre-configured festivals, edition support, and color branding
- Artist database with alias resolution and group definitions
- Configurable at user level (~/.cratedigger/config.json) and library level
- TTL-based caching for API lookups (MusicBrainz, fanart.tv, 1001Tracklists)
- Rich terminal UI with progress reporting, colored status indicators, and spinners
- Audit command for checking festival logo coverage
