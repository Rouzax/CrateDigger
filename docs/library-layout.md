# Library layout

After you run `organize` and `enrich`, your library is more than a folder tree of MKV files. Each video has sidecar files beside it, each folder has album-level files, and a cache of downloaded artwork lives under `~/.cratedigger/`. This page is the canonical map of every file CrateDigger writes and where each piece of data comes from.

For tags inside the MKV, see the [tag reference](tag-reference.md).

## Library tree example

A B2B set (Armin van Buuren & KI/KI at AMF 2025) after a full `identify` → `organize` → `enrich` pass looks like this:

```
Music/Library/
└── Armin van Buuren/
    ├── folder.jpg                                        ← album poster for this folder
    ├── 2025 - Armin van Buuren & KI_KI - Amsterdam Music Festival.mkv
    ├── 2025 - Armin van Buuren & KI_KI - Amsterdam Music Festival.nfo
    ├── 2025 - Armin van Buuren & KI_KI - Amsterdam Music Festival-thumb.jpg
    ├── 2025 - Armin van Buuren & KI_KI - Amsterdam Music Festival-poster.jpg
    └── 2025 - Armin van Buuren & KI_KI - Amsterdam Music Festival-fanart.jpg
```

CrateDigger routes the file to the primary DJ's folder (`Armin van Buuren`); the B2B partner is carried in the MKV tags, not the filesystem. The primary-artist routing is what `media_file.artist` and the TTV=50 `ARTIST` tag preserve.

## Per-video sidecars

Written into the same folder as the MKV, sharing the video's stem:

| File | Written by | Source | Used by |
|---|---|---|---|
| `{stem}.nfo` | enrich / `NfoOperation` | Metadata from identify + analyzer (artist, festival, date, genres, stage) | Kodi, Jellyfin, Plex (musicvideo NFO spec) |
| `{stem}-thumb.jpg` | enrich / `ArtOperation` | Embedded MKV attachment via `mkvextract`; ffmpeg frame sample fallback | Kodi/Jellyfin/Plex thumbnail view; `PosterOperation` reads this to compose `{stem}-poster.jpg` |
| `{stem}-poster.jpg` | enrich / `PosterOperation` | Composite of thumb + festival logo + metadata text (see [poster layouts](#poster-layouts)) | Kodi/Jellyfin poster view |
| `{stem}-fanart.jpg` | enrich / `ArtOperation` | Copy of `{stem}-thumb.jpg` (Kodi expects the sidecar to exist on disk for per-item fanart) | Kodi/Jellyfin fanart view |

All four are generated during `enrich`. The `art` op produces `-thumb.jpg` and `-fanart.jpg`; the `posters` op produces `-poster.jpg` (per-video) and `folder.jpg` (per-folder). The `nfo` op produces `.nfo`.

## Folder-level files

Written into the folder containing the MKV, shared by all videos in that folder:

| File | Written by | Source | Used by |
|---|---|---|---|
| `folder.jpg` | enrich / `AlbumPosterOperation` | Composite following [poster layouts](#poster-layouts); folder type (festival / artist / year) selected from the layout template in config | Kodi/Jellyfin album/folder artwork |
| `fanart.jpg` | Not written automatically | User-placed only; CrateDigger recognises it as a folder-level sidecar (for cleanup and organize-time preservation) but does not generate it | Kodi/Jellyfin folder fanart |

Per-artist fanart (from fanart.tv) lives in the cache at `~/.cratedigger/artists/<Artist>/fanart.jpg` and `clearlogo.png`. It's fetched by `FanartOperation` and read by the poster pipeline; it isn't copied into the library tree itself.

## Cover art sources

The thumb is the root of the artwork chain — every per-video image derives from it. Source precedence in `festival_organizer/artwork.py:extract_cover`:

1. **Embedded MKV attachment** — `mkvextract` pulls `cover.jpg`/`cover.png` if the file carries one.
2. **Frame sample fallback** — `festival_organizer/frame_sampler.py` scans the video for the best-quality frame (sharp, non-uniform, avoiding title cards and black frames) and encodes it as JPG.

Once the thumb exists, `ArtOperation` copies it to `{stem}-fanart.jpg` so Kodi's per-item fanart slot is populated. The poster pipeline consumes the thumb to compose `{stem}-poster.jpg` and contributes it (along with any sibling thumbs) to folder-level color derivation.

## Poster layouts

CrateDigger composes two kinds of poster: per-video set posters and per-folder album posters. The set-poster layout is fixed; the album-poster layout is auto-selected from four variants.

Run with `--verbose` to see which layout fired: `PosterOperation` / `AlbumPosterOperation` emit a `layout.branch` INFO event on every poster written.

### Set poster (`{stem}-poster.jpg`)

Single "v5b line-anchored" layout. The source image (the thumb) is:

- Blurred and darkened to form the full-poster background.
- Cropped and resized sharp on top, flush to the top edge, with a fade mask starting at 60% of its height.
- Overlaid with stacked centered text: artist name, festival name (accent-colored from the source), date, stage, venue.

Background source priority for the sharp top image: 1001TL DJ artwork → fanart.tv artist background → the thumb itself as a last resort.

### Album poster (`folder.jpg`)

Four variants, auto-selected by the source image shape and folder type:

| Layout | Selected when | Visual |
|---|---|---|
| Festival gradient + logo | A curated festival logo is available and is smaller than 600px wide | Gradient base derived from the logo's dominant hue; sharp centered logo; festival text |
| Artist centered on blur | Small source image and the folder is an artist folder (hero text override set) | Gradient base + blurred overlay of the source + sharp centered logo + artist name |
| Large source with fade | Background image is ≥ 600px wide (fanart.tv photo, DJ artwork) | Sharp top half of the image; fades to dark; hero text below |
| Gradient fallback | No background image available at all | Pure gradient derived from thumb color or config override; hero text only |

### Background source precedence per folder type

`AlbumPosterOperation` picks the background image for each folder based on the layout template in your config:

- **Festival folders** (first segment of template is `{festival}`): curated `festivals/<Festival>/logo.png` → gradient fallback.
- **Artist folders** (first segment is `{artist}`): 1001TL DJ artwork (if a single artist in folder) → fanart.tv artist background → gradient fallback.
- **Year folders** (first segment is `{year}`): gradient only.

Multi-artist folders (multiple DJs in the same directory) are treated as festival-style even if they live under an artist path; fanart.tv is not used because there's no single artist to key it on.

### Color derivation

Priority chain for the gradient base color and accent:

1. `poster_settings` config override (hex) — used verbatim if set for this festival/artist.
2. Logo-derived — saturation-aware circular hue mean of the logo image, ignoring low-saturation pixels; gives a brand color that survives dark/light variants.
3. Thumb-derived — dominant color across sibling `*-thumb.jpg` files in the folder.
4. Gradient composition — base color darkened to ~50% value, radial highlight in the upper center, low-amplitude noise grain.

All posters run the final text through a WCAG contrast check against the base and nudge colors if the ratio would drop below 4.5:1.

## NFO contents

CrateDigger writes Kodi-compatible musicvideo NFO files. Jellyfin reads the same spec, so these files work in both without modification. Plex can also read them via agents that support musicvideo NFOs.

Elements written by `festival_organizer/nfo.py:generate_nfo`:

| Element | Content |
|---|---|
| `<title>` | Display title from `build_display_title`: for festival sets, `Artist @ Stage, Festival [SetTitle]`; for concerts, the concert title. |
| `<artist>` | One element per DJ in `media_file.artists` (from 1001TL). Falls back to a single primary artist when no list is available. |
| `<album>` | For festival sets: `Festival Year` (e.g. `Amsterdam Music Festival 2025`). For concerts: concert title or festival name. |
| `<premiered>` | Release date (`YYYY-MM-DD`), or `YYYY-01-01` if only a year is known. |
| `<genre>` | One element per extracted 1001TL track genre; falls back to `nfo_settings.genre_festival` or `genre_concert` from config. |
| `<tag>` | Content type, festival, edition, each artist name, plus expanded group members (e.g. `Swedish House Mafia` -> each individual member). Used for Kodi smart playlists. Deduplicated case-insensitively. |
| `<studio>` | Stage name for festival sets, venue for concerts. |
| `<plot>` | Multi-line description: `Stage: <stage>`, `Edition: <edition>`, `Edition: <set_title>`. Only lines with data are emitted. |
| `<runtime>` | Duration in whole minutes. |
| `<thumb aspect="thumb">` | Reference to `{stem}-thumb.jpg`. |
| `<thumb aspect="poster">` | Reference to `{stem}-poster.jpg`. |
| `<fanart><thumb>` | Reference to `{stem}-fanart.jpg`. |
| `<dateadded>` | Timestamp of the most recent enrich pass that wrote this NFO. |

Sample NFO for the Armin b2b KI/KI example:

```xml
<musicvideo>
  <title>Armin van Buuren &amp; KI/KI @ Two Is One, Amsterdam Music Festival</title>
  <artist>Armin van Buuren</artist>
  <artist>KI/KI</artist>
  <album>Amsterdam Music Festival 2025</album>
  <premiered>2025-10-25</premiered>
  <genre>Big Room</genre>
  <genre>Tech House</genre>
  <genre>Techno</genre>
  <tag>festival_set</tag>
  <tag>Amsterdam Music Festival</tag>
  <tag>Armin van Buuren</tag>
  <tag>KI/KI</tag>
  <studio>Two Is One</studio>
  <plot>Stage: Two Is One</plot>
  <runtime>75</runtime>
  <thumb aspect="thumb">2025 - Armin van Buuren &amp; KI_KI - Amsterdam Music Festival-thumb.jpg</thumb>
  <thumb aspect="poster">2025 - Armin van Buuren &amp; KI_KI - Amsterdam Music Festival-poster.jpg</thumb>
  <fanart>
    <thumb>2025 - Armin van Buuren &amp; KI_KI - Amsterdam Music Festival-fanart.jpg</thumb>
  </fanart>
  <dateadded>2026-04-14 10:15:30</dateadded>
</musicvideo>
```

Without a 1001TL account, the NFO still populates from filename parsing and embedded metadata: `<title>`, primary `<artist>`, `<album>`, `<premiered>` (year-derived), fallback `<genre>`. What drops away is the multi-artist list, 1001TL-extracted genres, stage, set title, and any field the filename parser can't infer.

## Curated festival logos

For festival-style posters, CrateDigger looks for a curated festival logo to use as the centered mark. The filename convention is `logo.<ext>` inside a folder named after the canonical festival display name (e.g. `Tomorrowland`, `Tomorrowland Winter`, `EDC Las Vegas`).

Supported formats: JPG, JPEG, PNG, WEBP. SVG, GIF, BMP, and TIFF are not supported.

### Location precedence

CrateDigger searches two locations, library-local first:

1. `<library>/.cratedigger/festivals/<FestivalName>/logo.<ext>` — library-local override, travels with the library.
2. `~/.cratedigger/festivals/<FestivalName>/logo.<ext>` — user-level shared across all libraries.

The library-local file wins when both exist. Ship a library-local logo when you want a different crop or brand variant for a specific library; use the user-level location for general-purpose logos you want across all your libraries.

### Coverage auditing

Use [`cratedigger audit-logos`](commands/audit-logos.md) to list festivals in your library that are missing curated logos. The command reports:

- Festivals with logos, and the path to each file.
- Festivals missing logos, with both suggested placement paths.
- Unmatched logo folders that exist but don't correspond to any festival in your library.
- Unsupported format warnings.

When a curated logo is missing, the album poster for that festival falls back to fanart-derived or pure-gradient layout (see [album poster layouts](#album-poster-folderjpg) above).

## See also

- [Tag reference](tag-reference.md) — metadata tags written inside the MKV.
- [Enrich command](commands/enrich.md) — operations that produce these files (`art`, `posters`, `nfo`, `fanart`).
- [Audit Logos command](commands/audit-logos.md) — check festival logo coverage.
- [Kodi integration](kodi-integration.md) — how Kodi (and Jellyfin, which reads the same NFO and sidecar conventions) consume these files.
- [Configuration](configuration.md) — `poster_settings`, `nfo_settings`, layout template keys.
