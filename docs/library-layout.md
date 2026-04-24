# Library layout

After running `organize` and `enrich`, your library is more than a folder tree of video files. Each video has sidecar files placed beside it, each folder has album-level artwork, and a cache of downloaded artist artwork lives in your home directory. This page maps every file CrateDigger writes and where the content comes from.

For the metadata tags written inside MKV files, see the [tag reference](tag-reference.md).

---

## What the library looks like

A B2B set (Armin van Buuren & KIKI at AMF 2025, Two Is One stage) after a full `identify` → `organize` → `enrich` pass looks like this:

```
Music/Library/
└── Armin van Buuren/
    ├── folder.jpg
    ├── 2025 - Armin van Buuren & KIKI - AMF [Two Is One].mkv
    ├── 2025 - Armin van Buuren & KIKI - AMF [Two Is One].nfo
    ├── 2025 - Armin van Buuren & KIKI - AMF [Two Is One]-thumb.jpg
    ├── 2025 - Armin van Buuren & KIKI - AMF [Two Is One]-poster.jpg
    └── 2025 - Armin van Buuren & KIKI - AMF [Two Is One]-fanart.jpg
```

For B2B sets, CrateDigger uses the primary artist's name for folder routing. The B2B partner is carried in the MKV tags and NFO, not in the folder or filename.

Named acts that perform together permanently (such as "Axwell & Ingrosso" or "Swedish House Mafia") are treated as a single artist and get their own dedicated folder. CrateDigger learns these group names automatically from 1001Tracklists, or you can define them manually in [`artists.json`](configuration.md#artist-aliases).

---

## Files written per video

These files are written into the same folder as the video, sharing the video's base name:

| File | Written by | Content |
|------|-----------|---------|
| `{stem}.nfo` | enrich `nfo` | XML metadata file read by Kodi, Jellyfin, and Plex: title, artists, album, date, genres, stage, artwork references |
| `{stem}-thumb.jpg` | enrich `art` | Cover art image (see [Artwork](#artwork) below) |
| `{stem}-poster.jpg` | enrich `posters` | Composite poster with artist name, festival, date, and stage overlaid on a background image |
| `{stem}-fanart.jpg` | enrich `art` | Copy of `{stem}-thumb.jpg`; Kodi and Jellyfin expect this filename for per-item fanart |

---

## Files written per folder

These files represent the whole folder and are shared by all videos in it:

| File | Written by | Content |
|------|-----------|---------|
| `folder.jpg` | enrich `posters` | Album poster for the folder; layout depends on folder type (see [Poster layouts](#poster-layouts) below) |
| `fanart.jpg` | User-placed only | CrateDigger recognizes this file for sidecar migration during `organize`, but does not generate it |

Artist artwork downloaded from fanart.tv is stored in the cache folder (`~/.cache/CrateDigger/artists/{Artist}/` on Linux, `~/Library/Caches/CrateDigger/artists/{Artist}/` on macOS, `$env:LOCALAPPDATA\CrateDigger\Cache\artists\{Artist}\` on Windows) and used by the poster pipeline. It is not copied into the library tree itself.

---

## Artwork

### Cover art sources

CrateDigger tries three sources in order when generating `{stem}-thumb.jpg`:

1. **Embedded artwork:** if the MKV file has an image attachment (for example, a thumbnail embedded by yt-dlp), it is extracted and used directly. This is the best quality source.
2. **Video frame sample:** if no embedded artwork exists and the `vision` extra is installed, CrateDigger samples a still frame from the video. See [getting started](getting-started.md#optional-video-frame-sampling) for installation.
3. **Generated gradient:** if neither source is available, a color gradient image is generated from the available metadata. This ensures a thumbnail always exists so the rest of the pipeline can continue, but it contains no imagery from the actual video.

### Poster layouts

CrateDigger generates two types of poster: a per-video set poster (`{stem}-poster.jpg`) and a per-folder album poster (`folder.jpg`).

#### Per-video poster

The video's thumb image forms the background, blurred and darkened across the full poster. A sharpened crop of the same image is pinned to the top with a fade. Metadata text is centered below: artist name, festival name, date, stage, and venue. The accent color is derived from the source image.

Background image tried in order: DJ artwork from 1001Tracklists, then fanart.tv artist background, then the thumb itself.

#### Album poster (folder.jpg)

The album poster layout is selected automatically based on what images are available and what type of folder it is:

| Situation | Layout |
|-----------|--------|
| Festival folder with a curated logo | Gradient base derived from the logo's colors; logo centered; festival name below |
| Artist folder with fanart.tv or DJ artwork | Background image fading to dark; artist name overlaid |
| No background image available | Color gradient from metadata; artist or festival name overlaid |

For multi-artist folders (multiple DJs sharing one directory), CrateDigger treats the folder as festival-style since there is no single artist to key on.

**Background source priority by folder type:**

| Folder type | Sources tried in order |
|-------------|----------------------|
| Festival folder | Curated festival logo, then gradient |
| Artist folder | DJ artwork from 1001Tracklists, then fanart.tv artist background, then gradient |
| Year folder | Gradient only |

The gradient color comes from the festival's `color` field in [`festivals.json`](festivals.md) if set, otherwise from the dominant color across the folder's thumb images.

---

## NFO files

CrateDigger writes Kodi-compatible musicvideo NFO files. Jellyfin reads the same format. Plex can read them via musicvideo-compatible agents.

| Element | Content |
|---------|---------|
| `<title>` | For festival sets: `Artist @ Stage, Festival [SetTitle]`. For concerts: the concert title. |
| `<artist>` | One element per DJ (from 1001Tracklists). Falls back to a single primary artist when no list is available. |
| `<album>` | For festival sets: `Festival Year` (e.g., `Amsterdam Music Festival 2025`). For concerts: concert title or festival name. |
| `<premiered>` | Release date (`YYYY-MM-DD`), or `YYYY-01-01` if only a year is known. |
| `<genre>` | One element per genre extracted from 1001Tracklists track data. Falls back to the genre configured in [`nfo_settings`](configuration.md#nfo-settings). |
| `<tag>` | Content type, festival name, each artist name, plus expanded group members. Used for Kodi smart playlists. |
| `<studio>` | Stage name for festival sets; venue for concerts. |
| `<plot>` | Stage, edition, and set title, one per line. Only lines with data are included. |
| `<runtime>` | Duration in whole minutes. |
| `<thumb aspect="thumb">` | Path to `{stem}-thumb.jpg`. |
| `<thumb aspect="poster">` | Path to `{stem}-poster.jpg`. |
| `<fanart><thumb>` | Path to `{stem}-fanart.jpg`. |
| `<dateadded>` | Timestamp of the enrich run that wrote this file. |

Sample NFO for the Armin b2b KI/KI example:

```xml
<musicvideo>
  <title>Armin van Buuren &amp; KI/KI @ Two Is One, AMF</title>
  <artist>Armin van Buuren</artist>
  <artist>KIKI</artist>
  <album>AMF 2025</album>
  <premiered>2025-10-25</premiered>
  <genre>Techno</genre>
  <genre>Trance</genre>
  <genre>Hard Dance</genre>
  <tag>festival_set</tag>
  <tag>AMF</tag>
  <tag>Armin van Buuren</tag>
  <tag>KIKI</tag>
  <studio>Two Is One</studio>
  <plot>Stage: Two Is One</plot>
  <runtime>47</runtime>
  <thumb aspect="thumb">2025 - Armin van Buuren &amp; KIKI - AMF [Two Is One]-thumb.jpg</thumb>
  <thumb aspect="poster">2025 - Armin van Buuren &amp; KIKI - AMF [Two Is One]-poster.jpg</thumb>
  <fanart>
    <thumb>2025 - Armin van Buuren &amp; KIKI - AMF [Two Is One]-fanart.jpg</thumb>
  </fanart>
  <dateadded>2026-04-13 19:27:27</dateadded>
</musicvideo>
```

Without a 1001Tracklists account, the NFO still populates from filename parsing and embedded tags: title, primary artist, album, year, and fallback genre. The multi-artist list, 1001Tracklists-sourced genres, stage, set title, and any field the filename parser cannot infer are omitted.

---

## Festival logos

For festival-style folder posters, CrateDigger looks for a curated logo image to place as the centered mark. The filename convention is `logo.<ext>` inside a folder named after the canonical festival display name (for example `Tomorrowland`, `Tomorrowland Winter`, `EDC Las Vegas`).

**Supported formats:** JPG, PNG, WebP. SVG, GIF, BMP, and TIFF are not supported.

### Where to place logo files

CrateDigger searches two locations, library-local first:

1. `{library}/.cratedigger/festivals/{FestivalName}/logo.<ext>`: travels with the library; takes precedence when both locations have a file
2. User-level, shared across all your libraries:

| Platform | Path |
|----------|------|
| Linux | `~/CrateDigger/festivals/{FestivalName}/logo.<ext>` |
| macOS | `~/CrateDigger/festivals/{FestivalName}/logo.<ext>` |
| Windows | `Documents\CrateDigger\festivals\{FestivalName}\logo.<ext>` |

### Checking coverage

Use [`audit-logos`](commands/audit-logos.md) to see which festivals in your library have logos and which are missing them. The command shows the suggested placement path for each missing festival.

When a logo is missing, the folder poster falls back to a gradient layout.

---

## See also

- [Tag reference](tag-reference.md): metadata tags written inside the MKV
- [enrich command](commands/enrich.md): the operations that produce these files
- [audit-logos command](commands/audit-logos.md): check festival logo coverage
- [Kodi integration](kodi-integration.md): how Kodi and Jellyfin consume these files
- [Configuration](configuration.md): `poster_settings`, `nfo_settings`, layout templates
