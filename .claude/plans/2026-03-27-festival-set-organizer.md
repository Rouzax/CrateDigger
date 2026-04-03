# Festival Set Organizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full library manager that scans festival DJ sets and concert recordings, extracts metadata (MediaInfo + 1001Tracklists tags + filename parsing), classifies content, organizes into configurable folder structures, generates Kodi NFO files, and extracts cover art — with dry-run safety by default.

**Architecture:** Pipeline of scan → extract → parse → analyse → classify → plan → execute. Each stage is a separate module with pure-function interfaces. Configuration via JSON file controls folder layout templates, festival aliases, content type rules, and skip patterns. Two content types (festival_set, concert_film) each get their own layout template. The template engine uses `{placeholder}` substitution with conditional segments.

**Tech Stack:** Python 3.13 + Pillow + opencv-contrib-python + scenedetect. Standard library: pathlib, subprocess, json, xml.etree, csv, argparse, dataclasses, re, fnmatch, shutil. External CLI tools: MediaInfo, mkvextract/mkvmerge/mkvpropedit (MKVToolNix), ffmpeg/ffprobe. Windows-first (UNC paths, UTF-8 console forcing).

**External tools on this system:**
- MediaInfo: `C:\Program Files\WinGet\Links\mediainfo.EXE`
- MKVToolNix: `C:\Program Files\MKVToolNix\` (mkvextract, mkvmerge, mkvpropedit)
- ffmpeg/ffprobe: `C:\Program Files\WinGet\Links\ffmpeg.exe` (v8.1)
- Python: 3.13.9 (Pillow 12.1, opencv-contrib-python 4.13, scenedetect 0.6.7)
- Target collection: `\\hyperv\Data\Concerts` (READ-ONLY for testing, 72+ media files)
- Build directory: `C:\GitHub\CrateDigger`

---

## Design Decisions (from prototyping session 2026-03-27)

Prototyping scripts are in `C:\TEMP\poster-test\`. The approved poster layout is in `text_v5b.py`.

### Poster Generation — Set Posters (per-video)

**Image source priority:**
1. Use embedded MKV cover art (extracted via mkvextract) as the poster source image — these are curated YouTube thumbnails, consistently good
2. Fallback for files without embedded art: smart-sample 50 evenly-spaced frames from the video, score by vibrancy (brightness × saturation + soft sharpness bonus), pick the highest-scoring frame
3. Accept that some embedded thumbnails have baked-in text that competes with the overlay — this is fine

**Layout (v5b — line-anchored):**
- Poster size: 1000×1500px (2:3 ratio)
- Source image placed flush to top (`img_y = 0`), scaled to fill poster width
- Image fades out via gradient mask starting at 60% of image height
- Dark gradient overlay from 40% down for text legibility
- **Accent line** anchored at fixed position: `POSTER_H * 0.67` (2/3 down) — this is the visual anchor
- **Artist name builds UP** from the accent line (padding → artist line 2 → artist line 1)
- **Festival/date/detail build DOWN** from the accent line (padding → festival → date → detail)
- All positioning uses `font.getmetrics()` (ascent + descent) for consistent baselines regardless of font size
- Background: blurred + darkened copy of source image fills entire poster behind the sharp image

**Text styling:**
- Artist: Segoe UI Bold, auto-sized 110pt→50pt to fit width, letter-spaced, white
- Festival: Segoe UI Bold, auto-sized 68pt→36pt, accent color with glow effect (radius 18)
- Date/Year: Segoe UI Light, 52pt, accent color with glow (radius 14)
- Detail: Segoe UI Semilight, 36pt, light gray (170, 170, 170)
- Accent line: 400px wide, 4px tall, accent color with glow (radius 14)
- All text has drop shadow (2-3px offset, black 160 alpha) except on editorial album posters

**Accent color:** Auto-derived from source image — convert to HSV, compute mean hue/saturation, convert back with boosted saturation. Contrast guard ensures color is bright enough to read on dark background.

**Artist name splitting:**
1. Parenthetical pattern first: `"Act Name (Artist & Artist)"` → line 1: `ACT NAME`, line 2: `ARTIST & ARTIST` (parens stripped)
2. Then connectors: `&`, `B2B`, `vs`, `x` → split at connector, connector stays on line 2
3. Never split on word count alone — band names like "Swedish House Mafia" stay on one line
4. Lines that would shrink below 60pt trigger line-break at natural break points

**Date display:**
- When full date is available (from 1001TL metadata): `28 March 2025` on the date line
- When only year is available: `2025` on the date line
- No duplication — date line replaces what was previously separate year + detail date
- ISO format (`2025-03-28`) kept in NFO `<premiered>` tag for Kodi

### Poster Generation — Album Posters (per-folder)

**Style:** Clean editorial — color gradient background, no image. Festival name is the hero.

**Layout:** Same line-anchored system as set posters, but festival name sits where artist would be (above the line), and date/venue/set-count sit below.

**Color:** Auto-derived from thumbnails in the folder (mean HSV across all covers). Optional per-festival color override in config. Gradient: lighter at top-center with subtle radial highlight, darker at edges/bottom. Subtle noise grain for texture.

**Layout-dependent behavior:**
- `festival_first` layout: album = all artists at one festival/year → editorial gradient poster
- `artist_first` layout: album = one artist at one festival/year → use set poster as folder art (usually only 1-2 files)

### Video Thumbnails

- Extract embedded MKV cover art as `videoname-thumb.jpg` next to the video
- Save at original resolution (typically 1280×720) — Kodi/Plex cache their own scaled versions
- Referenced in NFO via `<thumb>videoname-thumb.jpg</thumb>`

### Kodi NFO Structure

**Per-video (`videoname.nfo`):** `<musicvideo>` with `<title>`, `<artist>`, `<album>` (= festival name for sets, title for concerts), `<year>`, `<genre>`, `<premiered>` (ISO date), `<plot>`, `<runtime>`, `<thumb>`, `<fileinfo>/<streamdetails>`

**Per-folder (`album.nfo`):** `<album>` with `<title>`, `<year>`, `<genre>`, `<plot>`. Grouping in Kodi relies on matching `<album>` tags across individual video NFOs.

**Output structure example (festival_first):**
```
AMF/2024/
├── 2024 - AMF - Martin Garrix.mkv
├── 2024 - AMF - Martin Garrix-thumb.jpg
├── 2024 - AMF - Martin Garrix.nfo
├── 2024 - AMF - Tiesto.mkv
├── 2024 - AMF - Tiesto-thumb.jpg
├── 2024 - AMF - Tiesto.nfo
├── poster.jpg          (generated album poster)
├── folder.jpg          (copy of poster for Kodi folder browsing)
└── album.nfo
```

### Plex Support

- `mkvpropedit` tag embedding: opt-in via `--embed-tags` flag — embeds artist, title, date into MKV file tags
- Only runs on destination files (never modifies source collection)
- Plex reads embedded MKV tags and uses folder structure for browsing
- `poster.jpg`/`folder.jpg` picked up by Plex "Other Videos" library for folder thumbnails

---

## File Structure

```
C:\GitHub\CrateDigger\
├── organize.py                          # CLI entry point (thin wrapper, ~10 lines)
├── config.json                          # Default configuration file
├── festival_organizer/
│   ├── __init__.py                      # Package init, version string
│   ├── models.py                        # Dataclasses: MediaFile, FileAction
│   ├── config.py                        # Config loading, defaults, validation
│   ├── normalization.py                 # safe_filename, scene tags, festival alias lookup
│   ├── parsers.py                       # 1001TL parser, filename parser, parent-dir parser
│   ├── metadata.py                      # MediaInfo + ffprobe extraction
│   ├── analyzer.py                      # Priority cascade combining all sources → MediaFile
│   ├── classifier.py                    # festival_set vs concert_film classification
│   ├── templates.py                     # Folder/filename template engine
│   ├── planner.py                       # Builds list of FileAction from MediaFile list
│   ├── executor.py                      # Move/copy/rename with collision handling
│   ├── nfo.py                           # Kodi <musicvideo> NFO XML generation
│   ├── album_nfo.py                     # Kodi <album> NFO for folder-level metadata
│   ├── artwork.py                       # MKV cover art extraction + thumbnail saving
│   ├── poster.py                        # Poster generation (Pillow: blur bg + text overlay)
│   ├── frame_sampler.py                 # Smart frame grab from video (OpenCV vibrancy scoring)
│   ├── embed_tags.py                    # mkvpropedit tag embedding for Plex (opt-in)
│   ├── scanner.py                       # Recursive media file discovery
│   ├── logging_util.py                  # UTF-8 console + CSV log export
│   └── cli.py                           # argparse subcommands: scan, execute, check, nfo, posters
└── tests/
    ├── __init__.py
    ├── test_normalization.py
    ├── test_parsers.py
    ├── test_config.py
    ├── test_classifier.py
    ├── test_templates.py
    ├── test_planner.py
    ├── test_nfo.py
    ├── test_artwork.py
    ├── test_poster.py
    ├── test_scanner.py
    ├── test_executor.py
    └── test_integration.py              # End-to-end dry-run against real collection
```

### Module Responsibilities

| Module | Responsibility | Depends on |
|--------|---------------|------------|
| `models.py` | Dataclasses only, no logic | nothing |
| `config.py` | Load JSON, merge defaults, provide typed access | `models` |
| `normalization.py` | Text cleaning: safe_filename, scene tag stripping, alias lookup | `config` |
| `parsers.py` | Three pure parsers: 1001TL title, filename, parent dirs | `normalization` |
| `metadata.py` | MediaInfo/ffprobe subprocess wrapper | nothing |
| `analyzer.py` | Combine metadata + parsers with priority cascade → MediaFile | `metadata`, `parsers`, `normalization`, `models`, `config` |
| `classifier.py` | Determine content_type from MediaFile + path | `models`, `config` |
| `templates.py` | Render `{placeholder}` folder/filename templates | `normalization`, `models`, `config` |
| `planner.py` | Build FileAction list from MediaFile list | `templates`, `classifier`, `models`, `config` |
| `executor.py` | Execute FileActions (move/copy/rename) | `models` |
| `nfo.py` | Generate Kodi `<musicvideo>` NFO sidecar files | `models`, `config` |
| `album_nfo.py` | Generate Kodi `<album>` NFO for folder-level metadata | `models`, `config` |
| `artwork.py` | Extract cover art from MKV, save as `videoname-thumb.jpg` | `models` |
| `poster.py` | Generate set posters (v5b layout) + album posters (editorial gradient) | `models`, `config`, `artwork`, Pillow |
| `frame_sampler.py` | Smart-sample 50 frames from video, vibrancy scoring, fallback for no embedded art | OpenCV |
| `embed_tags.py` | Embed metadata into MKV via mkvpropedit (opt-in `--embed-tags`) | `models` |
| `scanner.py` | Walk directory tree, filter media, skip patterns | `config` |
| `logging_util.py` | Console output + CSV export | nothing |
| `cli.py` | argparse + pipeline orchestration | everything |

---

## Real-World Test Data

These are actual files from the user's collection. Tests reference these patterns:

**Festival sets with 1001TL metadata:**
- `1001TRACKLISTS_TITLE: "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands 2024-10-19"`
- `1001TRACKLISTS_TITLE: "Hardwell @ The Great Library Stage, Tomorrowland Weekend 1, Belgium 2025-07-18"`
- `1001TRACKLISTS_TITLE: "Everything Always (Dom Dolla & John Summit) @ Mainstage, Ultra Music Festival Miami, United States 2025-03-28"`
- `1001TRACKLISTS_TITLE: "Martin Garrix & Alesso @ Red Rocks Amphitheatre, United States 2025-10-24"`
- `1001TRACKLISTS_TITLE: "Armin van Buuren @ kineticFIELD, EDC Las Vegas, United States 2025-05-18"`

**Filename patterns:**
- `MARTIN GARRIX LIVE @ AMF 2024.mkv`
- `Tiësto - AMF 2024 (Live Set) [fgipozjOI10].mkv`
- `2025 - AMF - Armin van Buuren.mkv`
- `2025 - Belgium - Hardwell WE1.mkv`
- `Armin van Buuren live at EDC Las Vegas 2025 [Dp7AwrAKckQ].mkv`
- `glastonbury.2016.coldplay.1080p.hdtv.x264-verum.mkv`
- `Coldplay.A.Head.Full.of.Dreams.2018.1080p.AMZN.WEB-DL.DDP5.1.H.264-NTG.mkv`
- `Adele - Live At The Royal Albert Hall-concert.mkv`

---

### Task 1: Models

**Files:**
- Create: `festival_organizer/__init__.py`
- Create: `festival_organizer/models.py`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write test for MediaFile dataclass**

```python
# tests/test_models.py
from pathlib import Path
from festival_organizer.models import MediaFile, FileAction


def test_media_file_defaults():
    mf = MediaFile(source_path=Path("test.mkv"))
    assert mf.artist == ""
    assert mf.festival == ""
    assert mf.year == ""
    assert mf.content_type == ""
    assert mf.extension == ""
    assert mf.duration_seconds is None
    assert mf.has_cover == False


def test_media_file_with_values():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        content_type="festival_set",
    )
    assert mf.artist == "Martin Garrix"
    assert mf.festival == "AMF"


def test_media_file_resolution_property():
    mf = MediaFile(source_path=Path("test.mkv"), width=3840, height=2160)
    assert mf.resolution == "3840x2160"

    mf2 = MediaFile(source_path=Path("test.mkv"))
    assert mf2.resolution == ""


def test_media_file_duration_formatted():
    mf = MediaFile(source_path=Path("test.mkv"), duration_seconds=7260.0)
    assert mf.duration_formatted == "121m00s"

    mf2 = MediaFile(source_path=Path("test.mkv"))
    assert mf2.duration_formatted == ""


def test_file_action_defaults():
    mf = MediaFile(source_path=Path("src.mkv"))
    fa = FileAction(
        source=Path("src.mkv"),
        target=Path("dst.mkv"),
        media_file=mf,
    )
    assert fa.action == "move"
    assert fa.status == "pending"
    assert fa.error == ""
    assert fa.generate_nfo == False
    assert fa.extract_art == False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_models.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Create package init and models**

```python
# festival_organizer/__init__.py
"""Festival Set Organizer — library manager for DJ sets and concert recordings."""
__version__ = "0.1.0"
```

```python
# festival_organizer/models.py
"""Data models for the festival organizer pipeline."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MediaFile:
    """All known information about a single media file."""
    source_path: Path

    # Content metadata
    artist: str = ""
    festival: str = ""
    year: str = ""
    date: str = ""
    set_title: str = ""
    title: str = ""          # For concert films: the concert/show title
    stage: str = ""
    location: str = ""
    content_type: str = ""   # "festival_set" | "concert_film" | "unknown"
    metadata_source: str = "" # "1001tracklists" | "metadata" | "filename"

    # Identifiers
    youtube_id: str = ""
    tracklists_url: str = ""

    # Technical metadata
    extension: str = ""
    file_type: str = ""      # "video" | "audio"
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    video_format: str = ""
    audio_format: str = ""
    audio_bitrate: str = ""
    overall_bitrate: str = ""
    has_cover: bool = False

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return ""

    @property
    def duration_formatted(self) -> str:
        if self.duration_seconds is not None:
            total = int(self.duration_seconds)
            mins = total // 60
            secs = total % 60
            return f"{mins}m{secs:02d}s"
        return ""


@dataclass
class FileAction:
    """A planned move/copy/rename operation."""
    source: Path
    target: Path
    media_file: MediaFile
    action: str = "move"       # "move" | "copy" | "rename"
    status: str = "pending"    # "pending" | "done" | "skipped" | "error"
    error: str = ""
    generate_nfo: bool = False
    extract_art: bool = False
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_models.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git init
git add festival_organizer/__init__.py festival_organizer/models.py tests/__init__.py tests/test_models.py
git commit -m "feat: add MediaFile and FileAction dataclasses"
```

---

### Task 2: Config Schema and Loader

**Files:**
- Create: `config.json`
- Create: `festival_organizer/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write tests for config loading**

```python
# tests/test_config.py
import json
import tempfile
from pathlib import Path
from festival_organizer.config import Config, load_config, DEFAULT_CONFIG


def test_default_config_has_required_keys():
    cfg = Config(DEFAULT_CONFIG)
    assert cfg.default_layout == "artist_first"
    assert "artist_first" in cfg.layouts
    assert "festival_first" in cfg.layouts
    assert "festival_set" in cfg.filename_templates
    assert "concert_film" in cfg.filename_templates


def test_config_festival_aliases():
    cfg = Config(DEFAULT_CONFIG)
    assert cfg.resolve_festival_alias("Amsterdam Music Festival") == "AMF"
    assert cfg.resolve_festival_alias("amf") == "AMF"
    assert cfg.resolve_festival_alias("EDC Las Vegas") == "EDC Las Vegas"
    assert cfg.resolve_festival_alias("Unknown Thing") == "Unknown Thing"


def test_config_festival_location():
    cfg = Config(DEFAULT_CONFIG)
    # Tomorrowland has location_in_name: true
    assert cfg.get_festival_display("Tomorrowland", "Belgium") == "Tomorrowland Belgium"
    assert cfg.get_festival_display("Tomorrowland", "") == "Tomorrowland"
    # AMF does not have location_in_name
    assert cfg.get_festival_display("AMF", "Netherlands") == "AMF"


def test_config_layout_templates():
    cfg = Config(DEFAULT_CONFIG)
    fs = cfg.get_layout_template("festival_set")
    assert "{artist}" in fs
    assert "{festival}" in fs
    cf = cfg.get_layout_template("concert_film")
    assert "{artist}" in cf


def test_config_skip_patterns():
    cfg = Config(DEFAULT_CONFIG)
    assert cfg.should_skip("Dolby.UHD/BDMV/STREAM/00001.m2ts")
    assert cfg.should_skip("anything/BDMV/something.m2ts")
    assert not cfg.should_skip("AMF/2024/Martin Garrix.mkv")


def test_config_force_concert_patterns():
    cfg = Config(DEFAULT_CONFIG)
    assert cfg.is_forced_concert("Adele/2011 - Live/file.mkv")
    assert cfg.is_forced_concert("Coldplay/2016/file.mkv")
    assert cfg.is_forced_concert("U2/360/file.mkv")
    assert not cfg.is_forced_concert("AMF/2024/file.mkv")


def test_load_config_from_file():
    data = {
        "default_layout": "festival_first",
        "festival_aliases": {"TML": "Tomorrowland"},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        f.flush()
        cfg = load_config(Path(f.name))
    # Custom value overrides default
    assert cfg.default_layout == "festival_first"
    # Custom alias merged
    assert cfg.resolve_festival_alias("TML") == "Tomorrowland"
    # Default aliases still present
    assert cfg.resolve_festival_alias("AMF") == "AMF"


def test_config_media_extensions():
    cfg = Config(DEFAULT_CONFIG)
    assert ".mkv" in cfg.media_extensions
    assert ".mp4" in cfg.media_extensions
    assert ".mp3" in cfg.media_extensions
    assert ".txt" not in cfg.media_extensions


def test_config_known_festivals():
    cfg = Config(DEFAULT_CONFIG)
    festivals = cfg.known_festivals
    assert "AMF" in festivals
    assert "Tomorrowland" in festivals
    assert "EDC Las Vegas" in festivals
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_config.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Create config.json**

```json
{
    "default_layout": "artist_first",

    "layouts": {
        "artist_first": {
            "festival_set": "{artist}/{festival}/{year}",
            "concert_film": "{artist}/{year} - {title}"
        },
        "festival_first": {
            "festival_set": "{festival}/{year}/{artist}",
            "concert_film": "{artist}/{year} - {title}"
        }
    },

    "filename_templates": {
        "festival_set": "{year} - {festival} - {artist}",
        "concert_film": "{artist} - {title}"
    },

    "festival_aliases": {
        "AMF": "AMF",
        "Amsterdam Music Festival": "AMF",
        "EDC": "EDC Las Vegas",
        "EDC Las Vegas": "EDC Las Vegas",
        "Electric Daisy Carnival": "EDC Las Vegas",
        "Ultra": "Ultra Music Festival",
        "Ultra Music Festival": "Ultra Music Festival",
        "Ultra Music Festival Miami": "Ultra Music Festival",
        "Tomorrowland": "Tomorrowland",
        "Tomorrowland Weekend 1": "Tomorrowland",
        "Tomorrowland Weekend 2": "Tomorrowland",
        "Mysteryland": "Mysteryland",
        "Glastonbury": "Glastonbury",
        "Red Rocks": "Red Rocks",
        "Red Rocks Amphitheatre": "Red Rocks",
        "Dreamstate": "Dreamstate",
        "We Belong Here": "We Belong Here",
        "We Belong Here Miami": "We Belong Here",
        "Defqon.1": "Defqon.1",
        "Creamfields": "Creamfields",
        "Lollapalooza": "Lollapalooza",
        "Untold": "Untold"
    },

    "festival_config": {
        "Tomorrowland": {
            "location_in_name": true,
            "known_locations": ["Belgium", "Brasil", "Brazil"]
        },
        "EDC": {
            "location_in_name": true,
            "known_locations": ["Las Vegas", "Mexico", "Orlando"]
        }
    },

    "content_type_rules": {
        "force_concert": [
            "Adele/*",
            "Buena Vista Social Club/*",
            "Coldplay/*",
            "Ed Sheeran*",
            "Michael Buble*",
            "Robbie Williams/*",
            "U2/*"
        ],
        "force_festival": []
    },

    "skip_patterns": [
        "*/BDMV/*",
        "Dolby*"
    ],

    "media_extensions": {
        "video": [".mp4", ".mkv", ".webm", ".avi", ".mov", ".m2ts", ".ts"],
        "audio": [".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg", ".opus"]
    },

    "fallback_values": {
        "unknown_artist": "Unknown Artist",
        "unknown_festival": "_Needs Review",
        "unknown_year": "Unknown Year",
        "unknown_title": "Unknown Title"
    },

    "nfo_settings": {
        "genre_festival": "Electronic",
        "genre_concert": "Live"
    }
}
```

- [ ] **Step 4: Implement config.py**

```python
# festival_organizer/config.py
"""Configuration loading and access."""
import json
from copy import deepcopy
from fnmatch import fnmatch
from pathlib import Path


# Default config embedded so the tool works without a config file
DEFAULT_CONFIG = {
    "default_layout": "artist_first",
    "layouts": {
        "artist_first": {
            "festival_set": "{artist}/{festival}/{year}",
            "concert_film": "{artist}/{year} - {title}",
        },
        "festival_first": {
            "festival_set": "{festival}/{year}/{artist}",
            "concert_film": "{artist}/{year} - {title}",
        },
    },
    "filename_templates": {
        "festival_set": "{year} - {festival} - {artist}",
        "concert_film": "{artist} - {title}",
    },
    "festival_aliases": {
        "AMF": "AMF",
        "Amsterdam Music Festival": "AMF",
        "EDC": "EDC Las Vegas",
        "EDC Las Vegas": "EDC Las Vegas",
        "Electric Daisy Carnival": "EDC Las Vegas",
        "Ultra": "Ultra Music Festival",
        "Ultra Music Festival": "Ultra Music Festival",
        "Ultra Music Festival Miami": "Ultra Music Festival",
        "Tomorrowland": "Tomorrowland",
        "Tomorrowland Weekend 1": "Tomorrowland",
        "Tomorrowland Weekend 2": "Tomorrowland",
        "Mysteryland": "Mysteryland",
        "Glastonbury": "Glastonbury",
        "Red Rocks": "Red Rocks",
        "Red Rocks Amphitheatre": "Red Rocks",
        "Dreamstate": "Dreamstate",
        "We Belong Here": "We Belong Here",
        "We Belong Here Miami": "We Belong Here",
        "Defqon.1": "Defqon.1",
        "Creamfields": "Creamfields",
        "Lollapalooza": "Lollapalooza",
        "Untold": "Untold",
    },
    "festival_config": {
        "Tomorrowland": {
            "location_in_name": True,
            "known_locations": ["Belgium", "Brasil", "Brazil"],
        },
        "EDC": {
            "location_in_name": True,
            "known_locations": ["Las Vegas", "Mexico", "Orlando"],
        },
    },
    "content_type_rules": {
        "force_concert": [
            "Adele/*",
            "Buena Vista Social Club/*",
            "Coldplay/*",
            "Ed Sheeran*",
            "Michael Buble*",
            "Robbie Williams/*",
            "U2/*",
        ],
        "force_festival": [],
    },
    "skip_patterns": ["*/BDMV/*", "Dolby*"],
    "media_extensions": {
        "video": [".mp4", ".mkv", ".webm", ".avi", ".mov", ".m2ts", ".ts"],
        "audio": [".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg", ".opus"],
    },
    "fallback_values": {
        "unknown_artist": "Unknown Artist",
        "unknown_festival": "_Needs Review",
        "unknown_year": "Unknown Year",
        "unknown_title": "Unknown Title",
    },
    "nfo_settings": {
        "genre_festival": "Electronic",
        "genre_concert": "Live",
    },
}


class Config:
    """Typed access to the configuration."""

    def __init__(self, data: dict):
        self._data = data

    @property
    def default_layout(self) -> str:
        return self._data.get("default_layout", "artist_first")

    @property
    def layouts(self) -> dict:
        return self._data.get("layouts", {})

    @property
    def filename_templates(self) -> dict:
        return self._data.get("filename_templates", {})

    @property
    def festival_aliases(self) -> dict:
        return self._data.get("festival_aliases", {})

    @property
    def festival_config(self) -> dict:
        return self._data.get("festival_config", {})

    @property
    def skip_patterns(self) -> list[str]:
        return self._data.get("skip_patterns", [])

    @property
    def fallback_values(self) -> dict:
        return self._data.get("fallback_values", {})

    @property
    def nfo_settings(self) -> dict:
        return self._data.get("nfo_settings", {})

    @property
    def media_extensions(self) -> set[str]:
        exts = self._data.get("media_extensions", {})
        result = set()
        for group in exts.values():
            result.update(group)
        return result

    @property
    def video_extensions(self) -> set[str]:
        return set(self._data.get("media_extensions", {}).get("video", []))

    @property
    def known_festivals(self) -> set[str]:
        """All canonical festival names (the values of the alias map)."""
        return set(self.festival_aliases.values())

    def resolve_festival_alias(self, name: str) -> str:
        """Map a festival name/abbreviation to its canonical form."""
        # Try exact match first, then case-insensitive
        if name in self.festival_aliases:
            return self.festival_aliases[name]
        lower_map = {k.lower(): v for k, v in self.festival_aliases.items()}
        return lower_map.get(name.lower(), name)

    def get_festival_display(self, canonical_festival: str, location: str) -> str:
        """Get display name for a festival, optionally including location."""
        fc = self.festival_config.get(canonical_festival, {})
        if fc.get("location_in_name") and location:
            # Normalize Brasil/Brazil
            known = fc.get("known_locations", [])
            for k in known:
                if k.lower() == location.lower():
                    location = k
                    break
            return f"{canonical_festival} {location}"
        return canonical_festival

    def get_layout_template(self, content_type: str, layout_name: str | None = None) -> str:
        """Get the folder layout template for a content type."""
        layout = layout_name or self.default_layout
        layouts = self.layouts.get(layout, {})
        return layouts.get(content_type, layouts.get("festival_set", "{artist}/{year}"))

    def get_filename_template(self, content_type: str) -> str:
        """Get the filename template for a content type."""
        return self.filename_templates.get(content_type, "{artist} - {title}")

    def should_skip(self, relative_path: str) -> bool:
        """Check if a relative path matches any skip pattern."""
        # Normalize to forward slashes for matching
        normalized = relative_path.replace("\\", "/")
        for pattern in self.skip_patterns:
            if fnmatch(normalized, pattern):
                return True
        return False

    def is_forced_concert(self, relative_path: str) -> bool:
        """Check if a relative path is force-classified as concert_film."""
        normalized = relative_path.replace("\\", "/")
        rules = self._data.get("content_type_rules", {})
        for pattern in rules.get("force_concert", []):
            if fnmatch(normalized, pattern):
                return True
        return False

    def is_forced_festival(self, relative_path: str) -> bool:
        """Check if a relative path is force-classified as festival_set."""
        normalized = relative_path.replace("\\", "/")
        rules = self._data.get("content_type_rules", {})
        for pattern in rules.get("force_festival", []):
            if fnmatch(normalized, pattern):
                return True
        return False


def load_config(config_path: Path | None = None) -> Config:
    """Load config from file, merging with defaults."""
    merged = deepcopy(DEFAULT_CONFIG)
    if config_path and config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_data = json.load(f)
        _deep_merge(merged, user_data)
    return Config(merged)


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base (mutates base)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_config.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
cd /c/GitHub/CrateDigger
git add config.json festival_organizer/config.py tests/test_config.py
git commit -m "feat: add config loading with festival aliases and layout templates"
```

---

### Task 3: Normalization

**Files:**
- Create: `festival_organizer/normalization.py`
- Create: `tests/test_normalization.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_normalization.py
from festival_organizer.normalization import (
    safe_filename,
    normalise_name,
    strip_scene_tags,
    strip_noise_words,
    extract_youtube_id,
    scene_dots_to_spaces,
)
from festival_organizer.config import Config, DEFAULT_CONFIG


def test_safe_filename_removes_illegal_chars():
    assert safe_filename('Artist: The "Best" <Live>') == "Artist The Best Live"
    assert safe_filename("KI⧸KI") == "KIKI"  # fraction slash U+2044


def test_safe_filename_collapses_whitespace():
    assert safe_filename("Artist   Name") == "Artist Name"


def test_safe_filename_strips_trailing_dots():
    assert safe_filename("Name...") == "Name"


def test_safe_filename_truncates_long_names():
    long_name = "A" * 250
    assert len(safe_filename(long_name)) <= 200


def test_normalise_name_trims_separators():
    assert normalise_name("  - Artist Name - ") == "Artist Name"
    assert normalise_name("") == ""


def test_strip_scene_tags():
    assert strip_scene_tags("Coldplay A Head Full of Dreams 2018 1080p AMZN WEB-DL DDP5 1 H 264-NTG") == "Coldplay A Head Full of Dreams 2018"
    assert strip_scene_tags("glastonbury 2016 coldplay 720p hdtv x264-verum") == "glastonbury 2016 coldplay"


def test_strip_scene_tags_preserves_content():
    assert strip_scene_tags("Martin Garrix LIVE @ AMF 2024") == "Martin Garrix LIVE @ AMF 2024"


def test_strip_noise_words():
    assert "Full Set" not in strip_noise_words("Martin Garrix Full Set")
    assert "Live Set" not in strip_noise_words("Tiësto Live Set")
    assert "DJ Set" not in strip_noise_words("Artist Full DJ Set")
    assert "Official" not in strip_noise_words("Official Stream")


def test_extract_youtube_id():
    stem, yt_id = extract_youtube_id("Armin van Buuren live at EDC Las Vegas 2025 [Dp7AwrAKckQ]")
    assert yt_id == "Dp7AwrAKckQ"
    assert "[Dp7AwrAKckQ]" not in stem
    assert stem.strip() == "Armin van Buuren live at EDC Las Vegas 2025"

    stem2, yt_id2 = extract_youtube_id("No ID here")
    assert yt_id2 == ""
    assert stem2 == "No ID here"


def test_scene_dots_to_spaces():
    assert scene_dots_to_spaces("glastonbury.2016.coldplay.1080p.hdtv.x264-verum") == "glastonbury 2016 coldplay 1080p hdtv x264-verum"
    # Should NOT convert when there are few dots (not scene-style)
    assert scene_dots_to_spaces("Defqon.1") == "Defqon.1"
    # Should NOT convert when there are already spaces
    assert scene_dots_to_spaces("Artist Name - Festival 2024") == "Artist Name - Festival 2024"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_normalization.py -v`
Expected: FAIL

- [ ] **Step 3: Implement normalization.py**

```python
# festival_organizer/normalization.py
"""Text normalization: filename safety, scene tag stripping, alias resolution."""
import re

# Characters illegal in Windows filenames
ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Unicode characters that look like slashes but aren't (e.g. KI⧸KI)
UNICODE_SLASHES = re.compile(r'[\u2044\u2215\u29F8\u29F9\uFF0F]')

# Scene-release technical tags
SCENE_TAGS = re.compile(
    r"\b("
    r"1080[pi]|720[pi]|2160[pi]|4K|UHD|"
    r"HDTV|PDTV|WEB-?DL|WEBRip|BluRay|Blu-?Ray|BDRip|DVDRip|"
    r"x264|x265|H\.?264|H\.?265|HEVC|AVC|VP9|AV1|"
    r"AAC|AC3|EAC3|E-AC-3|DTS|TrueHD|Atmos|DDP?\d?\.\d|FLAC|Opus|"
    r"AMZN|NF|PROPER|REPACK|REMUX|"
    r"[A-Z0-9]+-[A-Z]{2,}[A-Z0-9]*"
    r")\b",
    re.IGNORECASE,
)

# YouTube video ID: [xCvaCI5GN1g]
YT_ID_PATTERN = re.compile(r"\s*\[([A-Za-z0-9_-]{11})\]\s*")

# Noise words to strip from filenames
NOISE_WORDS = re.compile(
    r"\b(Full\s+Set|Live\s+Set|Full\s+DJ\s+Set|DJ\s+Set|Official|"
    r"HD|HQ|4K\s+HD|Preview|US\s+Debut|Hardstyle\s+Exclusive)\b",
    re.IGNORECASE,
)


def safe_filename(name: str) -> str:
    """Make a string safe for use as a Windows filename component."""
    name = UNICODE_SLASHES.sub("", name)
    name = ILLEGAL_CHARS.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")
    if len(name) > 200:
        name = name[:200].rstrip(". ")
    return name


def normalise_name(name: str) -> str:
    """Clean up a name: trim, collapse spaces, remove illegal chars."""
    if not name:
        return ""
    name = UNICODE_SLASHES.sub("", name)
    name = ILLEGAL_CHARS.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.strip(" -\u2013\u2014.,")
    return name


def strip_scene_tags(text: str) -> str:
    """Remove scene-release technical tags and clean up residue."""
    result = SCENE_TAGS.sub("", text)
    # Clean up leftover separators and whitespace
    result = re.sub(r"[\s\-]+$", "", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def strip_noise_words(text: str) -> str:
    """Remove noise words like 'Full Set', 'Live Set', etc."""
    result = NOISE_WORDS.sub("", text)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def extract_youtube_id(stem: str) -> tuple[str, str]:
    """Extract and remove YouTube video ID from a filename stem.
    Returns (cleaned_stem, youtube_id). youtube_id is "" if not found."""
    match = YT_ID_PATTERN.search(stem)
    if match:
        yt_id = match.group(1)
        cleaned = YT_ID_PATTERN.sub("", stem)
        return cleaned, yt_id
    return stem, ""


def scene_dots_to_spaces(stem: str) -> str:
    """Convert scene-style dot-separated names to spaces.
    Only converts if there are many dots and few spaces (heuristic)."""
    if stem.count(".") > 3 and stem.count(" ") < 2:
        return stem.replace(".", " ")
    return stem
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_normalization.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/normalization.py tests/test_normalization.py
git commit -m "feat: add normalization — safe filenames, scene tag stripping, YT ID extraction"
```

---

### Task 4: Parsers

**Files:**
- Create: `festival_organizer/parsers.py`
- Create: `tests/test_parsers.py`

- [ ] **Step 1: Write tests for 1001TL parser**

```python
# tests/test_parsers.py
from pathlib import Path
from festival_organizer.parsers import (
    parse_1001tracklists_title,
    parse_filename,
    parse_parent_dirs,
)
from festival_organizer.config import Config, DEFAULT_CONFIG


CFG = Config(DEFAULT_CONFIG)


# --- 1001Tracklists title parser ---

def test_1001tl_basic_festival():
    result = parse_1001tracklists_title(
        "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, "
        "Amsterdam Dance Event, Netherlands 2024-10-19",
        CFG,
    )
    assert result["artist"] == "Martin Garrix"
    assert result["festival"] == "AMF"  # Alias resolved
    assert result["date"] == "2024-10-19"
    assert result["year"] == "2024"
    assert "Johan Cruijff ArenA" in result.get("stage", "")


def test_1001tl_tomorrowland_with_stage():
    result = parse_1001tracklists_title(
        "Hardwell @ The Great Library Stage, Tomorrowland Weekend 1, Belgium 2025-07-18",
        CFG,
    )
    assert result["artist"] == "Hardwell"
    assert result["festival"] == "Tomorrowland"
    assert result["location"] == "Belgium"
    assert result["year"] == "2025"
    assert result["stage"] == "The Great Library Stage"


def test_1001tl_ultra_with_parenthetical_artist():
    result = parse_1001tracklists_title(
        "Everything Always (Dom Dolla & John Summit) @ Mainstage, "
        "Ultra Music Festival Miami, United States 2025-03-28",
        CFG,
    )
    assert result["artist"] == "Everything Always (Dom Dolla & John Summit)"
    assert result["festival"] == "Ultra Music Festival"
    assert result["year"] == "2025"


def test_1001tl_b2b_at_venue():
    result = parse_1001tracklists_title(
        "Martin Garrix & Alesso @ Red Rocks Amphitheatre, United States 2025-10-24",
        CFG,
    )
    assert result["artist"] == "Martin Garrix & Alesso"
    assert result["festival"] == "Red Rocks"
    assert result["year"] == "2025"


def test_1001tl_edc():
    result = parse_1001tracklists_title(
        "Armin van Buuren @ kineticFIELD, EDC Las Vegas, United States 2025-05-18",
        CFG,
    )
    assert result["artist"] == "Armin van Buuren"
    assert result["festival"] == "EDC Las Vegas"
    assert result["stage"] == "kineticFIELD"


def test_1001tl_empty():
    assert parse_1001tracklists_title("", CFG) == {}
    assert parse_1001tracklists_title(None, CFG) == {}


# --- Filename parser ---

def test_filename_yyyy_festival_artist():
    result = parse_filename(Path("2025 - AMF - Armin van Buuren.mkv"), CFG)
    assert result["year"] == "2025"
    assert result["festival"] == "AMF"
    assert result["artist"] == "Armin van Buuren"


def test_filename_yyyy_festival_artist_weekend():
    result = parse_filename(Path("2025 - Belgium - Hardwell WE1.mkv"), CFG)
    assert result["year"] == "2025"
    assert result["artist"] == "Hardwell"
    assert result["set_title"] == "WE1"


def test_filename_artist_live_at_festival():
    result = parse_filename(Path("MARTIN GARRIX LIVE @ AMF 2024.mkv"), CFG)
    assert result["artist"] == "MARTIN GARRIX"
    assert result["year"] == "2024"


def test_filename_artist_at_festival():
    result = parse_filename(
        Path("Armin van Buuren live at EDC Las Vegas 2025 [Dp7AwrAKckQ].mkv"), CFG
    )
    assert result["artist"] == "Armin van Buuren"
    assert result["year"] == "2025"
    assert result["youtube_id"] == "Dp7AwrAKckQ"


def test_filename_artist_dash_title():
    result = parse_filename(Path("Tiësto - AMF 2024 (Live Set) [fgipozjOI10].mkv"), CFG)
    assert result["youtube_id"] == "fgipozjOI10"
    assert "Tiësto" in result.get("artist", "")


def test_filename_scene_style():
    result = parse_filename(
        Path("glastonbury.2016.coldplay.1080p.hdtv.x264-verum.mkv"), CFG
    )
    assert result["year"] == "2016"
    # Should detect glastonbury as festival
    assert "glastonbury" in result.get("festival", "").lower() or "Glastonbury" in result.get("festival", "")


def test_filename_concert_style():
    result = parse_filename(Path("Adele - Live At The Royal Albert Hall-concert.mkv"), CFG)
    assert "Adele" in result.get("artist", "")


def test_filename_complex_youtube():
    result = parse_filename(
        Path("Everything Always (Dom Dolla & John Summit) Live @ Ultra Music Festival 2025 [9ZqJPIbTme4].mkv"),
        CFG,
    )
    assert result["youtube_id"] == "9ZqJPIbTme4"
    assert result["year"] == "2025"


# --- Parent directory parser ---

def test_parent_dirs_festival_year():
    result = parse_parent_dirs(
        Path("//hyperv/Data/Concerts/AMF/2024 - AMF/file.mkv"),
        Path("//hyperv/Data/Concerts"),
        CFG,
    )
    assert result.get("year") == "2024"
    assert result.get("festival") == "AMF"


def test_parent_dirs_tomorrowland_location():
    result = parse_parent_dirs(
        Path("//hyperv/Data/Concerts/Tomorrowland/2025 - Belgium/file.mkv"),
        Path("//hyperv/Data/Concerts"),
        CFG,
    )
    assert result.get("festival") == "Tomorrowland"
    assert result.get("location") == "Belgium"
    assert result.get("year") == "2025"


def test_parent_dirs_no_info():
    result = parse_parent_dirs(
        Path("C:/Downloads/random.mkv"),
        Path("C:/Downloads"),
        CFG,
    )
    assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_parsers.py -v`
Expected: FAIL

- [ ] **Step 3: Implement parsers.py**

```python
# festival_organizer/parsers.py
"""Parsers for extracting content information from various sources."""
import re
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.normalization import (
    extract_youtube_id,
    scene_dots_to_spaces,
    strip_noise_words,
    strip_scene_tags,
)

# Known location names for parent directory parsing
KNOWN_LOCATIONS = [
    "Belgium", "Brazil", "Brasil", "Las Vegas", "Miami",
    "Netherlands", "United States", "Mexico", "Orlando",
]


def parse_1001tracklists_title(title: str | None, config: Config) -> dict:
    """Parse the 1001TRACKLISTS_TITLE metadata tag.

    Format: "Artist @ Stage, Festival, Location YYYY-MM-DD"

    Returns dict with keys: artist, festival, stage, location, date, year.
    """
    if not title:
        return {}

    result = {}

    if "@" not in title:
        return {}

    artist_part, venue_part = title.split("@", 1)
    result["artist"] = artist_part.strip()

    # Extract date from the end
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})\s*$", venue_part)
    if date_match:
        result["date"] = date_match.group(1)
        result["year"] = date_match.group(1)[:4]
        venue_part = venue_part[:date_match.start()].strip().rstrip(",")

    # Split venue into comma-separated segments
    segments = [s.strip() for s in venue_part.split(",") if s.strip()]

    # Find which segment contains a known festival
    known = config.known_festivals
    festival_idx = None
    for i, seg in enumerate(segments):
        seg_lower = seg.lower()
        for fest in known:
            if fest.lower() in seg_lower:
                # Resolve alias to canonical name
                result["festival"] = config.resolve_festival_alias(seg.strip())
                festival_idx = i
                break
        if festival_idx is not None:
            break

    if festival_idx is not None:
        if festival_idx > 0:
            result["stage"] = ", ".join(segments[:festival_idx])
        if festival_idx < len(segments) - 1:
            result["location"] = ", ".join(segments[festival_idx + 1:])
    elif len(segments) >= 2:
        # No known festival — first segment is venue/festival, rest is location
        result["festival"] = config.resolve_festival_alias(segments[0])
        result["location"] = ", ".join(segments[1:])
    elif len(segments) == 1:
        result["festival"] = config.resolve_festival_alias(segments[0])

    return result


def parse_filename(filepath: Path, config: Config) -> dict:
    """Parse artist, festival, year, set title from a filename.

    Handles patterns:
        YYYY - Festival - Artist [WE1]
        ARTIST LIVE @ FESTIVAL YYYY
        ARTIST @ FESTIVAL YYYY
        ARTIST live at FESTIVAL YYYY
        ARTIST at FESTIVAL YYYY
        Artist - Title [YYYY]
        scene.style.name.YYYY.tech.tags
    """
    stem = filepath.stem
    result = {}

    # Extract YouTube ID
    stem, yt_id = extract_youtube_id(stem)
    if yt_id:
        result["youtube_id"] = yt_id

    # Convert scene-style dots to spaces
    stem = scene_dots_to_spaces(stem)

    # Strip scene tags and noise words
    stem = strip_scene_tags(stem)
    stem = strip_noise_words(stem)

    # Clean up
    stem = re.sub(r"\s+", " ", stem).strip(" -\u2013\u2014")

    # Remove "-concert" suffix (Plex convention)
    stem = re.sub(r"-concert\s*$", "", stem, flags=re.IGNORECASE).strip()

    known_festivals = config.known_festivals

    # --- Pattern: YYYY - Part2 - Part3 [WE1/WE2] ---
    m = re.match(r"^(\d{4})\s*[-\u2013]\s*(.+?)\s*[-\u2013]\s*(.+?)(?:\s+(WE\d))?\s*$", stem)
    if m:
        result.setdefault("year", m.group(1))
        part2 = m.group(2).strip()
        part3 = m.group(3).strip()
        weekend = m.group(4)
        # Part2 could be festival or location; Part3 is artist
        if _is_known_festival(part2, known_festivals):
            result.setdefault("festival", part2)
        else:
            # Could be location like "Belgium" — store both
            result.setdefault("festival", part2)
            # Check if it's actually a location for a known parent-dir festival
            for loc in KNOWN_LOCATIONS:
                if loc.lower() == part2.lower():
                    result["location"] = part2
                    result.pop("festival", None)
                    break
        result.setdefault("artist", part3)
        if weekend:
            result["set_title"] = weekend
        return result

    # --- Pattern: ARTIST LIVE @ FESTIVAL YYYY ---
    m = re.match(r"^(.+?)\s+(?:LIVE|live|Live)\s*@\s*(.+?)\s+(\d{4})\s*(.*)$", stem)
    if m:
        result.setdefault("artist", m.group(1).strip())
        result.setdefault("festival", m.group(2).strip())
        result.setdefault("year", m.group(3))
        leftover = m.group(4).strip(" -\u2013\u2014")
        if leftover:
            result.setdefault("set_title", leftover)
        return result

    # --- Pattern: ARTIST @ FESTIVAL YYYY ---
    m = re.match(r"^(.+?)\s*@\s*(.+?)\s+(\d{4})\s*(.*)$", stem)
    if m:
        result.setdefault("artist", m.group(1).strip())
        result.setdefault("festival", m.group(2).strip())
        result.setdefault("year", m.group(3))
        leftover = m.group(4).strip(" -\u2013\u2014")
        if leftover:
            result.setdefault("set_title", leftover)
        return result

    # --- Pattern: ARTIST live at FESTIVAL YYYY ---
    m = re.match(r"^(.+?)\s+(?:[Ll]ive\s+at)\s+(.+?)\s+(\d{4})\s*(.*)$", stem)
    if m:
        result.setdefault("artist", m.group(1).strip())
        result.setdefault("festival", m.group(2).strip())
        result.setdefault("year", m.group(3))
        leftover = m.group(4).strip(" -\u2013\u2014,")
        if leftover:
            result.setdefault("set_title", leftover)
        return result

    # --- Pattern: ARTIST at FESTIVAL YYYY ---
    m = re.match(r"^(.+?)\s+at\s+(.+?)\s+(\d{4})\s*(.*)$", stem)
    if m:
        result.setdefault("artist", m.group(1).strip())
        result.setdefault("festival", m.group(2).strip())
        result.setdefault("year", m.group(3))
        leftover = m.group(4).strip(" -\u2013\u2014,")
        if leftover:
            result.setdefault("set_title", leftover)
        return result

    # --- Pattern: Artist - Title [YYYY] ---
    m = re.match(r"^(.+?)\s*[-\u2013\u2014]\s*(.+?)(?:\s+(\d{4}))?\s*$", stem)
    if m:
        part1 = m.group(1).strip()
        part2 = m.group(2).strip()
        year = m.group(3)
        if _is_known_festival(part1, known_festivals):
            result.setdefault("festival", part1)
            result.setdefault("artist", part2)
        elif _is_known_festival(part2, known_festivals):
            result.setdefault("artist", part1)
            result.setdefault("festival", part2)
        else:
            result.setdefault("artist", part1)
            result.setdefault("title", part2)
        if year:
            result.setdefault("year", year)
        return result

    # --- Fallback: extract year, rest is artist ---
    year_match = re.search(r"\b((?:19|20)\d{2})\b", stem)
    if year_match:
        result.setdefault("year", year_match.group(1))
        remainder = (stem[:year_match.start()] + stem[year_match.end():]).strip(" -\u2013\u2014")
        # Check if remainder contains a known festival
        for fest in known_festivals:
            if fest.lower() in remainder.lower():
                result.setdefault("festival", fest)
                # Remove the festival name to get the artist
                cleaned = re.sub(re.escape(fest), "", remainder, flags=re.IGNORECASE).strip(" -\u2013\u2014")
                if cleaned:
                    result.setdefault("artist", cleaned)
                break
        else:
            if remainder:
                result.setdefault("artist", remainder)
    elif stem:
        result.setdefault("artist", stem)

    return result


def parse_parent_dirs(filepath: Path, root: Path, config: Config) -> dict:
    """Extract metadata from parent directory names relative to root."""
    result = {}

    try:
        relative = filepath.relative_to(root)
    except ValueError:
        return {}

    # Check each directory component (not the filename itself)
    for part in relative.parts[:-1]:
        # Year
        year_match = re.search(r"\b((?:19|20)\d{2})\b", part)
        if year_match:
            result.setdefault("year", year_match.group(1))

        # Known festival
        for fest in config.known_festivals:
            if fest.lower() in part.lower():
                result.setdefault("festival", fest)
                break

        # Known location
        for loc in KNOWN_LOCATIONS:
            if loc.lower() in part.lower():
                result.setdefault("location", loc)
                break

    return result


def _is_known_festival(name: str, known: set[str]) -> bool:
    """Check if name matches a known festival."""
    name_lower = name.lower()
    return any(f.lower() in name_lower for f in known)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_parsers.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/parsers.py tests/test_parsers.py
git commit -m "feat: add parsers for 1001TL titles, filenames, and parent directories"
```

---

### Task 5: Metadata Extraction

**Files:**
- Create: `festival_organizer/metadata.py`
- Create: `tests/test_metadata.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_metadata.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from festival_organizer.metadata import (
    find_tool,
    parse_mediainfo_json,
    extract_metadata,
)


def test_parse_mediainfo_json_full():
    """Test parsing a real MediaInfo JSON structure."""
    raw = {
        "media": {
            "track": [
                {
                    "@type": "General",
                    "Title": "MARTIN GARRIX LIVE @ AMF 2024",
                    "Duration": "7200.000",
                    "OverallBitRate": "13500000",
                    "Format": "Matroska",
                    "Encoded_Date": "2025-03-15 09:20:31 UTC",
                    "ARTIST": "",
                    "DATE": "",
                    "Description": "",
                    "Comment": "",
                    "PURL": "",
                    "Attachments": "cover.png",
                    "extra": {
                        "_1001TRACKLISTS_TITLE": "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands 2024-10-19",
                        "_1001TRACKLISTS_URL": "https://www.1001tracklists.com/tracklist/qv6kl89/",
                    },
                },
                {
                    "@type": "Video",
                    "Format": "VP9",
                    "Width": "3840",
                    "Height": "2160",
                    "BitRate": "13400000",
                    "FrameRate": "25.000",
                },
                {
                    "@type": "Audio",
                    "Format": "Opus",
                    "BitRate": "125000",
                    "Channels": "2",
                    "SamplingRate": "48000",
                },
            ]
        }
    }
    meta = parse_mediainfo_json(raw)
    assert meta["title"] == "MARTIN GARRIX LIVE @ AMF 2024"
    assert meta["duration_seconds"] == 7200.0
    assert meta["tracklists_title"] == "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands 2024-10-19"
    assert meta["tracklists_url"] == "https://www.1001tracklists.com/tracklist/qv6kl89/"
    assert meta["width"] == 3840
    assert meta["height"] == 2160
    assert meta["video_format"] == "VP9"
    assert meta["audio_format"] == "Opus"
    assert meta["has_cover"] == True


def test_parse_mediainfo_json_minimal():
    """Test parsing MediaInfo JSON with minimal data (no extra tags)."""
    raw = {
        "media": {
            "track": [
                {
                    "@type": "General",
                    "Duration": "3600.0",
                    "Format": "Matroska",
                },
            ]
        }
    }
    meta = parse_mediainfo_json(raw)
    assert meta["title"] == ""
    assert meta["tracklists_title"] == ""
    assert meta["has_cover"] == False
    assert meta["duration_seconds"] == 3600.0


def test_parse_mediainfo_json_empty():
    meta = parse_mediainfo_json({})
    assert meta == {}
    meta2 = parse_mediainfo_json({"media": {"track": []}})
    assert meta2 == {}


def test_find_tool_in_path():
    with patch("shutil.which", return_value="/usr/bin/mediainfo"):
        assert find_tool("mediainfo", []) == "/usr/bin/mediainfo"


def test_find_tool_fallback_paths():
    with patch("shutil.which", return_value=None):
        with patch("os.path.isfile", side_effect=lambda p: p == "/opt/mediainfo"):
            assert find_tool("mediainfo", ["/opt/mediainfo"]) == "/opt/mediainfo"


def test_find_tool_not_found():
    with patch("shutil.which", return_value=None):
        with patch("os.path.isfile", return_value=False):
            assert find_tool("mediainfo", []) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_metadata.py -v`
Expected: FAIL

- [ ] **Step 3: Implement metadata.py**

```python
# festival_organizer/metadata.py
"""Metadata extraction via MediaInfo CLI and ffprobe fallback."""
import json
import os
import shutil
import subprocess
from pathlib import Path


def find_tool(name: str, fallback_paths: list[str]) -> str | None:
    """Find a CLI tool by name in PATH or at known locations."""
    found = shutil.which(name)
    if found:
        return found
    for path in fallback_paths:
        if os.path.isfile(path):
            return path
    return None


# Locate tools at import time
MEDIAINFO_PATH = find_tool("mediainfo", [
    r"C:\Program Files\MediaInfo\MediaInfo.exe",
    r"C:\Program Files (x86)\MediaInfo\MediaInfo.exe",
    r"C:\Program Files\WinGet\Links\mediainfo.exe",
])

FFPROBE_PATH = find_tool("ffprobe", [
    r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
    r"C:\ffmpeg\bin\ffprobe.exe",
])


def parse_mediainfo_json(data: dict) -> dict:
    """Parse MediaInfo JSON output into a flat metadata dict."""
    tracks = data.get("media", {}).get("track", [])
    if not tracks:
        return {}

    general = tracks[0]
    video = next((t for t in tracks if t.get("@type") == "Video"), {})
    audio = next((t for t in tracks if t.get("@type") == "Audio"), {})
    extra = general.get("extra", {})

    return {
        "title": general.get("Title", ""),
        "duration_seconds": _parse_duration(general.get("Duration", "")),
        "overall_bitrate": general.get("OverallBitRate", ""),
        "format": general.get("Format", ""),
        "encoded_date": general.get("Encoded_Date", ""),
        # yt-dlp / custom tags
        "artist_tag": general.get("ARTIST", "") or extra.get("ARTIST", ""),
        "date_tag": general.get("DATE", "") or extra.get("DATE", ""),
        "description": general.get("Description", ""),
        "comment": general.get("Comment", ""),
        "purl": general.get("PURL", "") or extra.get("PURL", ""),
        # 1001Tracklists
        "tracklists_title": (
            general.get("1001TRACKLISTS_TITLE", "")
            or extra.get("_1001TRACKLISTS_TITLE", "")
        ),
        "tracklists_url": (
            general.get("1001TRACKLISTS_URL", "")
            or extra.get("_1001TRACKLISTS_URL", "")
        ),
        # Video
        "video_format": video.get("Format", ""),
        "width": _int_or_none(video.get("Width", "")),
        "height": _int_or_none(video.get("Height", "")),
        "video_bitrate": video.get("BitRate", ""),
        "framerate": video.get("FrameRate", ""),
        # Audio
        "audio_format": audio.get("Format", ""),
        "audio_bitrate": audio.get("BitRate", ""),
        "audio_channels": audio.get("Channels", ""),
        "audio_sampling_rate": audio.get("SamplingRate", ""),
        # Cover art
        "has_cover": bool(general.get("Attachments", "")),
    }


def _extract_mediainfo(filepath: Path) -> dict:
    """Run MediaInfo CLI and return parsed metadata."""
    if not MEDIAINFO_PATH:
        return {}
    try:
        result = subprocess.run(
            [MEDIAINFO_PATH, "--Output=JSON", str(filepath)],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        return parse_mediainfo_json(data)
    except Exception:
        return {}


def _extract_ffprobe(filepath: Path) -> dict:
    """Run ffprobe as fallback and return parsed metadata."""
    if not FFPROBE_PATH:
        return {}
    try:
        result = subprocess.run(
            [FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(filepath)],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        tags = fmt.get("tags", {})
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        return {
            "title": tags.get("title", "") or tags.get("TITLE", ""),
            "duration_seconds": _parse_duration(fmt.get("duration", "")),
            "overall_bitrate": fmt.get("bit_rate", ""),
            "format": fmt.get("format_long_name", ""),
            "artist_tag": tags.get("artist", "") or tags.get("ARTIST", ""),
            "date_tag": tags.get("date", "") or tags.get("DATE", ""),
            "description": tags.get("description", "") or tags.get("DESCRIPTION", ""),
            "comment": tags.get("comment", "") or tags.get("COMMENT", ""),
            "purl": tags.get("purl", "") or tags.get("PURL", ""),
            "tracklists_title": tags.get("1001TRACKLISTS_TITLE", ""),
            "tracklists_url": tags.get("1001TRACKLISTS_URL", ""),
            "video_format": video.get("codec_name", ""),
            "width": _int_or_none(video.get("width", "")),
            "height": _int_or_none(video.get("height", "")),
            "video_bitrate": video.get("bit_rate", ""),
            "framerate": video.get("r_frame_rate", ""),
            "audio_format": audio.get("codec_name", ""),
            "audio_bitrate": audio.get("bit_rate", ""),
            "audio_channels": audio.get("channels", ""),
            "audio_sampling_rate": audio.get("sample_rate", ""),
            "has_cover": False,  # ffprobe doesn't easily report attachments
        }
    except Exception:
        return {}


def extract_metadata(filepath: Path) -> dict:
    """Extract metadata from a file. Tries MediaInfo first, ffprobe fallback."""
    meta = _extract_mediainfo(filepath)
    if not meta:
        meta = _extract_ffprobe(filepath)
    return meta


def _parse_duration(value) -> float | None:
    """Parse a duration value to seconds."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    m = re.match(r"(\d+):(\d+):(\d+)", str(value))
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return None


def _int_or_none(value) -> int | None:
    """Parse an integer, handling MediaInfo's space-formatted numbers."""
    if not value:
        return None
    try:
        return int(str(value).replace(" ", "").replace("\u202f", ""))
    except (ValueError, TypeError):
        return None


# Need re for _parse_duration
import re
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_metadata.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/metadata.py tests/test_metadata.py
git commit -m "feat: add metadata extraction via MediaInfo and ffprobe"
```

---

### Task 6: Analyzer (Priority Cascade)

**Files:**
- Create: `festival_organizer/analyzer.py`
- Create: `tests/test_analyzer.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_analyzer.py
from pathlib import Path
from unittest.mock import patch
from festival_organizer.analyzer import analyse_file
from festival_organizer.config import Config, DEFAULT_CONFIG
from festival_organizer.models import MediaFile

CFG = Config(DEFAULT_CONFIG)


def test_analyse_with_1001tl_overrides_filename():
    """1001TL data should take priority over filename parsing."""
    fake_meta = {
        "title": "MARTIN GARRIX LIVE @ AMF 2024",
        "tracklists_title": "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands 2024-10-19",
        "tracklists_url": "https://www.1001tracklists.com/tracklist/qv6kl89/",
        "duration_seconds": 7200.0,
        "width": 3840,
        "height": 2160,
        "video_format": "VP9",
        "audio_format": "Opus",
        "audio_bitrate": "125000",
        "overall_bitrate": "13500000",
        "has_cover": True,
        "artist_tag": "",
        "date_tag": "",
        "description": "",
        "comment": "",
        "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("//hyperv/Data/Concerts/AMF/2024 - AMF/MARTIN GARRIX LIVE @ AMF 2024.mkv"),
            Path("//hyperv/Data/Concerts"),
            CFG,
        )
    assert isinstance(mf, MediaFile)
    assert mf.artist == "Martin Garrix"
    assert mf.festival == "AMF"
    assert mf.year == "2024"
    assert mf.date == "2024-10-19"
    assert mf.metadata_source == "1001tracklists"
    assert mf.has_cover == True


def test_analyse_filename_only():
    """When no metadata is available, filename parsing should work."""
    with patch("festival_organizer.analyzer.extract_metadata", return_value={}):
        mf = analyse_file(
            Path("//hyperv/Data/Concerts/AMF/2025 - AMF/2025 - AMF - Armin van Buuren.mkv"),
            Path("//hyperv/Data/Concerts"),
            CFG,
        )
    assert mf.artist == "Armin van Buuren"
    assert mf.festival == "AMF"
    assert mf.year == "2025"
    assert mf.metadata_source == "filename"


def test_analyse_concert_film():
    """Concert films with minimal metadata."""
    with patch("festival_organizer.analyzer.extract_metadata", return_value={}):
        mf = analyse_file(
            Path("//hyperv/Data/Concerts/Adele/2011 - Live/Adele - Live At The Royal Albert Hall-concert.mkv"),
            Path("//hyperv/Data/Concerts"),
            CFG,
        )
    assert "Adele" in mf.artist
    assert mf.year == "2011"


def test_analyse_embedded_artist_tag():
    """ARTIST metadata tag should fill in if filename doesn't provide it."""
    fake_meta = {
        "title": "",
        "tracklists_title": "",
        "tracklists_url": "",
        "artist_tag": "Michael Bublé",
        "date_tag": "20171215",
        "duration_seconds": 3900.0,
        "width": 3840,
        "height": 2160,
        "video_format": "VP9",
        "audio_format": "Opus",
        "audio_bitrate": "",
        "overall_bitrate": "",
        "has_cover": True,
        "description": "",
        "comment": "",
        "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("//hyperv/Data/Concerts/Michael Buble/some file.mkv"),
            Path("//hyperv/Data/Concerts"),
            CFG,
        )
    assert mf.artist == "Michael Bublé"
    assert mf.year == "2017"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_analyzer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement analyzer.py**

```python
# festival_organizer/analyzer.py
"""Analyzer: combines metadata and parsing into a single MediaFile."""
import re
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.metadata import extract_metadata
from festival_organizer.models import MediaFile
from festival_organizer.normalization import normalise_name, safe_filename
from festival_organizer.parsers import (
    parse_1001tracklists_title,
    parse_filename,
    parse_parent_dirs,
)

# Extensions
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m2ts", ".ts"}


def analyse_file(filepath: Path, root: Path, config: Config) -> MediaFile:
    """Analyse a single file, combining all metadata sources.

    Priority (highest first):
    1. 1001Tracklists title tag
    2. Embedded metadata tags (ARTIST, DATE, Title)
    3. Filename parsing
    4. Parent directory names
    """
    meta = extract_metadata(filepath)
    filename_info = parse_filename(filepath, config)
    parent_info = parse_parent_dirs(filepath, root, config)
    tracklists_info = parse_1001tracklists_title(
        meta.get("tracklists_title", ""), config
    )

    # Start with empty info dict
    info: dict[str, str] = {
        "artist": "",
        "festival": "",
        "year": "",
        "date": "",
        "set_title": "",
        "title": "",
        "stage": "",
        "location": "",
        "youtube_id": "",
    }

    # Layer 1 (lowest priority): parent directory info
    _merge_missing(info, parent_info)

    # Layer 2: filename parsing
    _merge_missing(info, filename_info)

    # Layer 3: embedded metadata tags
    embedded = {}
    if meta.get("artist_tag"):
        embedded["artist"] = meta["artist_tag"]
    if meta.get("date_tag"):
        dt = meta["date_tag"].replace("-", "")
        if len(dt) >= 4:
            embedded["year"] = dt[:4]
        if len(dt) == 8:
            embedded["date"] = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}"
    if meta.get("title"):
        # Parse the Title tag with the same filename heuristics
        title_info = parse_filename(Path(meta["title"] + filepath.suffix), config)
        _merge_missing(embedded, title_info)
    _merge_missing(info, embedded)

    # Layer 4 (highest priority): 1001Tracklists overwrites
    metadata_source = "filename"
    if tracklists_info:
        for key in ["artist", "festival", "date", "year", "stage", "location"]:
            if tracklists_info.get(key):
                info[key] = tracklists_info[key]
        metadata_source = "1001tracklists"
    elif embedded:
        metadata_source = "metadata+filename"

    # Normalise
    artist = normalise_name(info.get("artist", ""))
    festival = info.get("festival", "")
    # Resolve festival alias
    if festival:
        festival = config.resolve_festival_alias(festival)

    ext = filepath.suffix.lower()
    file_type = "video" if ext in VIDEO_EXTS else "audio"

    return MediaFile(
        source_path=filepath,
        artist=artist,
        festival=festival,
        year=info.get("year", "").strip(),
        date=info.get("date", ""),
        set_title=normalise_name(info.get("set_title", "")),
        title=normalise_name(info.get("title", "")),
        stage=info.get("stage", ""),
        location=info.get("location", ""),
        youtube_id=info.get("youtube_id", ""),
        tracklists_url=meta.get("tracklists_url", ""),
        metadata_source=metadata_source,
        content_type="",  # Set by classifier
        extension=ext,
        file_type=file_type,
        duration_seconds=meta.get("duration_seconds"),
        width=meta.get("width"),
        height=meta.get("height"),
        video_format=meta.get("video_format", ""),
        audio_format=meta.get("audio_format", ""),
        audio_bitrate=meta.get("audio_bitrate", ""),
        overall_bitrate=meta.get("overall_bitrate", ""),
        has_cover=meta.get("has_cover", False),
    )


def _merge_missing(target: dict, source: dict) -> None:
    """Copy values from source to target only where target is empty."""
    for key, value in source.items():
        if key in target and not target[key] and value:
            target[key] = value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_analyzer.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/analyzer.py tests/test_analyzer.py
git commit -m "feat: add analyzer with priority cascade (1001TL > tags > filename > dirs)"
```

---

### Task 7: Classifier

**Files:**
- Create: `festival_organizer/classifier.py`
- Create: `tests/test_classifier.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_classifier.py
from pathlib import Path
from festival_organizer.classifier import classify
from festival_organizer.config import Config, DEFAULT_CONFIG
from festival_organizer.models import MediaFile

CFG = Config(DEFAULT_CONFIG)
ROOT = Path("//hyperv/Data/Concerts")


def test_classify_force_concert():
    mf = MediaFile(source_path=ROOT / "Adele/2011/file.mkv", artist="Adele")
    assert classify(mf, ROOT, CFG) == "concert_film"

    mf2 = MediaFile(source_path=ROOT / "U2/360/file.mkv", artist="U2")
    assert classify(mf2, ROOT, CFG) == "concert_film"

    mf3 = MediaFile(source_path=ROOT / "Coldplay/2016/file.mkv", artist="Coldplay")
    assert classify(mf3, ROOT, CFG) == "concert_film"


def test_classify_1001tl_is_festival():
    mf = MediaFile(
        source_path=ROOT / "AMF/2024/file.mkv",
        artist="Martin Garrix",
        festival="AMF",
        metadata_source="1001tracklists",
    )
    assert classify(mf, ROOT, CFG) == "festival_set"


def test_classify_known_festival():
    mf = MediaFile(
        source_path=ROOT / "EDC/2025/file.mkv",
        artist="Armin van Buuren",
        festival="EDC Las Vegas",
        metadata_source="filename",
    )
    assert classify(mf, ROOT, CFG) == "festival_set"


def test_classify_unknown():
    mf = MediaFile(
        source_path=ROOT / "random/file.mkv",
        artist="Some Artist",
    )
    assert classify(mf, ROOT, CFG) == "unknown"


def test_classify_festival_overrides_no_force_concert():
    """A file in a concert-forced dir but with 1001TL should still be festival."""
    # This shouldn't happen in practice, but force_concert should win
    mf = MediaFile(
        source_path=ROOT / "Adele/2011/file.mkv",
        artist="Adele",
        festival="Glastonbury",
        metadata_source="1001tracklists",
    )
    # force_concert takes precedence — it's an explicit user override
    assert classify(mf, ROOT, CFG) == "concert_film"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_classifier.py -v`
Expected: FAIL

- [ ] **Step 3: Implement classifier.py**

```python
# festival_organizer/classifier.py
"""Content type classification: festival_set vs concert_film."""
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.models import MediaFile


def classify(media_file: MediaFile, root: Path, config: Config) -> str:
    """Determine the content type of a media file.

    Returns: "festival_set", "concert_film", or "unknown".

    Priority:
    1. Config force_concert / force_festival patterns (explicit user override)
    2. Has 1001TRACKLISTS_TITLE → festival_set
    3. Known festival detected → festival_set
    4. Fallback → unknown
    """
    # Compute relative path for pattern matching
    try:
        rel = str(media_file.source_path.relative_to(root)).replace("\\", "/")
    except ValueError:
        rel = media_file.source_path.name

    # 1. Explicit user overrides
    if config.is_forced_concert(rel):
        return "concert_film"
    if config.is_forced_festival(rel):
        return "festival_set"

    # 2. Has 1001TL metadata → festival
    if media_file.metadata_source == "1001tracklists":
        return "festival_set"

    # 3. Has a known festival name → festival
    if media_file.festival and media_file.festival in config.known_festivals:
        return "festival_set"

    # 4. Fallback
    return "unknown"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_classifier.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/classifier.py tests/test_classifier.py
git commit -m "feat: add content type classifier (festival_set / concert_film / unknown)"
```

---

### Task 8: Template Engine

**Files:**
- Create: `festival_organizer/templates.py`
- Create: `tests/test_templates.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_templates.py
from pathlib import Path
from festival_organizer.templates import render_folder, render_filename
from festival_organizer.config import Config, DEFAULT_CONFIG
from festival_organizer.models import MediaFile

CFG = Config(DEFAULT_CONFIG)


def test_render_folder_artist_first_festival():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG)
    assert result == "Martin Garrix/AMF/2024"


def test_render_folder_artist_first_concert():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Coldplay",
        title="A Head Full of Dreams",
        year="2018",
        content_type="concert_film",
    )
    result = render_folder(mf, CFG)
    assert result == "Coldplay/2018 - A Head Full of Dreams"


def test_render_folder_festival_first():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Hardwell",
        festival="Tomorrowland",
        year="2025",
        location="Belgium",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="festival_first")
    # Tomorrowland has location_in_name, so becomes "Tomorrowland Belgium"
    assert result == "Tomorrowland Belgium/2025/Hardwell"


def test_render_folder_with_location_in_festival_name():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Alok",
        festival="Tomorrowland",
        year="2025",
        location="Brasil",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG)
    assert result == "Alok/Tomorrowland Brasil/2025"


def test_render_folder_missing_artist():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        festival="AMF",
        year="2024",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG)
    assert "Unknown Artist" in result


def test_render_folder_unknown_content():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Someone",
        content_type="unknown",
    )
    result = render_folder(mf, CFG)
    assert "_Needs Review" in result


def test_render_filename_festival_set():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2024 - AMF - Martin Garrix.mkv"


def test_render_filename_with_set_title():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Hardwell",
        festival="Tomorrowland",
        year="2025",
        set_title="WE1",
        location="Belgium",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2025 - Tomorrowland Belgium - Hardwell - WE1.mkv"


def test_render_filename_concert_film():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Coldplay",
        title="A Head Full of Dreams",
        year="2018",
        extension=".mkv",
        content_type="concert_film",
    )
    result = render_filename(mf, CFG)
    assert result == "Coldplay - A Head Full of Dreams.mkv"


def test_render_filename_missing_values_uses_fallbacks():
    mf = MediaFile(
        source_path=Path("mystery.mkv"),
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    # Should fall back to original filename when too much is missing
    assert result == "mystery.mkv"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_templates.py -v`
Expected: FAIL

- [ ] **Step 3: Implement templates.py**

```python
# festival_organizer/templates.py
"""Template engine for folder paths and filenames."""
import re
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.models import MediaFile
from festival_organizer.normalization import safe_filename


def render_folder(media_file: MediaFile, config: Config, layout_name: str | None = None) -> str:
    """Render the folder path for a media file using the configured layout template.

    Returns a relative path string like "Artist/Festival/2024".
    """
    ct = media_file.content_type

    # Unknown content goes to _Needs Review
    if ct == "unknown" or ct == "":
        return "_Needs Review"

    template = config.get_layout_template(ct, layout_name)
    values = _build_values(media_file, config)
    return _render(template, values, config.fallback_values)


def render_filename(media_file: MediaFile, config: Config) -> str:
    """Render the filename for a media file using the configured template.

    Returns a filename string like "2024 - AMF - Martin Garrix.mkv".
    """
    ct = media_file.content_type
    ext = media_file.extension

    # For unknown content or when we have too little info, keep original name
    if ct == "unknown" or ct == "":
        return media_file.source_path.name

    template = config.get_filename_template(ct)
    values = _build_values(media_file, config)

    rendered = _render(template, values, config.fallback_values)

    # If the rendered name is mostly fallback values, keep the original
    fallbacks_used = sum(
        1 for v in config.fallback_values.values()
        if v in rendered
    )
    if fallbacks_used >= 2:
        return media_file.source_path.name

    # Clean up and append extension
    rendered = safe_filename(rendered)
    if not rendered:
        return media_file.source_path.name

    # Append set_title if present (not in template but we add it)
    if media_file.set_title and media_file.set_title not in rendered:
        rendered = f"{rendered} - {safe_filename(media_file.set_title)}"

    return rendered + ext


def _build_values(media_file: MediaFile, config: Config) -> dict[str, str]:
    """Build the substitution values dict for a media file."""
    # Resolve festival display name (with location if configured)
    festival = media_file.festival
    if festival:
        festival = config.get_festival_display(festival, media_file.location)

    return {
        "artist": safe_filename(media_file.artist),
        "festival": safe_filename(festival),
        "year": media_file.year,
        "date": media_file.date,
        "location": safe_filename(media_file.location),
        "stage": safe_filename(media_file.stage),
        "set_title": safe_filename(media_file.set_title),
        "title": safe_filename(media_file.title or media_file.set_title),
    }


def _render(template: str, values: dict[str, str], fallbacks: dict[str, str]) -> str:
    """Substitute {placeholders} in a template string.

    Empty values are replaced with fallback values from config.
    Path separators in the template are preserved.
    """
    result = template
    for key, value in values.items():
        placeholder = "{" + key + "}"
        if placeholder in result:
            if value:
                result = result.replace(placeholder, value)
            else:
                # Use fallback
                fallback_key = f"unknown_{key}"
                fallback = fallbacks.get(fallback_key, "")
                if fallback:
                    result = result.replace(placeholder, fallback)
                else:
                    result = result.replace(placeholder, "Unknown")

    # Clean up double separators from empty values
    result = re.sub(r"/ +/", "/", result)
    result = re.sub(r" +- +- +", " - ", result)
    result = result.strip("/ -")

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_templates.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/templates.py tests/test_templates.py
git commit -m "feat: add template engine for configurable folder and filename rendering"
```

---

### Task 9: Scanner

**Files:**
- Create: `festival_organizer/scanner.py`
- Create: `tests/test_scanner.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_scanner.py
import tempfile
from pathlib import Path
from festival_organizer.scanner import scan_folder
from festival_organizer.config import Config, DEFAULT_CONFIG

CFG = Config(DEFAULT_CONFIG)


def test_scan_finds_media_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "video.mkv").touch()
        (root / "audio.mp3").touch()
        (root / "readme.txt").touch()
        (root / "image.jpg").touch()
        files = scan_folder(root, CFG)
        names = {f.name for f in files}
        assert "video.mkv" in names
        assert "audio.mp3" in names
        assert "readme.txt" not in names
        assert "image.jpg" not in names


def test_scan_recursive():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sub = root / "sub" / "deep"
        sub.mkdir(parents=True)
        (sub / "nested.mkv").touch()
        files = scan_folder(root, CFG)
        assert len(files) == 1
        assert files[0].name == "nested.mkv"


def test_scan_skips_bdmv():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bdmv = root / "Dolby" / "BDMV" / "STREAM"
        bdmv.mkdir(parents=True)
        (bdmv / "00001.m2ts").touch()
        (root / "good.mkv").touch()
        files = scan_folder(root, CFG)
        names = {f.name for f in files}
        assert "good.mkv" in names
        assert "00001.m2ts" not in names


def test_scan_skips_dolby_pattern():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dolby = root / "Dolby.UHD.Demo"
        dolby.mkdir()
        (dolby / "demo.mkv").touch()
        (root / "good.mkv").touch()
        files = scan_folder(root, CFG)
        names = {f.name for f in files}
        assert "good.mkv" in names
        assert "demo.mkv" not in names


def test_scan_empty_folder():
    with tempfile.TemporaryDirectory() as tmp:
        assert scan_folder(Path(tmp), CFG) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_scanner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement scanner.py**

```python
# festival_organizer/scanner.py
"""Recursive media file scanner with skip-pattern filtering."""
from pathlib import Path

from festival_organizer.config import Config


def scan_folder(root: Path, config: Config) -> list[Path]:
    """Recursively find all media files under root, respecting skip patterns.

    Returns sorted list of Path objects.
    """
    media_exts = config.media_extensions
    files = []

    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        if item.suffix.lower() not in media_exts:
            continue

        # Check skip patterns against relative path
        try:
            rel = str(item.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = item.name

        if config.should_skip(rel):
            continue

        files.append(item)

    return files
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_scanner.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/scanner.py tests/test_scanner.py
git commit -m "feat: add scanner with skip-pattern filtering"
```

---

### Task 10: Planner

**Files:**
- Create: `festival_organizer/planner.py`
- Create: `tests/test_planner.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_planner.py
from pathlib import Path
from festival_organizer.planner import plan_actions
from festival_organizer.config import Config, DEFAULT_CONFIG
from festival_organizer.models import MediaFile, FileAction

CFG = Config(DEFAULT_CONFIG)
OUTPUT = Path("C:/Output")


def test_plan_festival_set_artist_first():
    mf = MediaFile(
        source_path=Path("C:/Input/file.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        content_type="festival_set",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG)
    assert len(actions) == 1
    a = actions[0]
    assert a.target == OUTPUT / "Martin Garrix" / "AMF" / "2024" / "2024 - AMF - Martin Garrix.mkv"
    assert a.action == "move"


def test_plan_concert_film():
    mf = MediaFile(
        source_path=Path("C:/Input/file.mkv"),
        artist="Coldplay",
        title="A Head Full of Dreams",
        year="2018",
        content_type="concert_film",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG)
    a = actions[0]
    assert a.target == OUTPUT / "Coldplay" / "2018 - A Head Full of Dreams" / "Coldplay - A Head Full of Dreams.mkv"


def test_plan_unknown_goes_to_needs_review():
    mf = MediaFile(
        source_path=Path("C:/Input/mystery.mkv"),
        content_type="unknown",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG)
    a = actions[0]
    assert "_Needs Review" in str(a.target)


def test_plan_with_set_title():
    mf = MediaFile(
        source_path=Path("C:/Input/file.mkv"),
        artist="Hardwell",
        festival="Tomorrowland",
        year="2025",
        location="Belgium",
        set_title="WE1",
        content_type="festival_set",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG)
    a = actions[0]
    assert "WE1" in a.target.name
    assert "Tomorrowland Belgium" in str(a.target)


def test_plan_action_type_copy():
    mf = MediaFile(
        source_path=Path("C:/Input/file.mkv"),
        artist="Test",
        festival="AMF",
        year="2024",
        content_type="festival_set",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG, action="copy")
    assert actions[0].action == "copy"


def test_plan_action_type_rename():
    mf = MediaFile(
        source_path=Path("C:/Input/file.mkv"),
        artist="Test",
        festival="AMF",
        year="2024",
        content_type="festival_set",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG, action="rename")
    a = actions[0]
    assert a.action == "rename"
    # Rename keeps the file in its original directory
    assert a.target.parent == Path("C:/Input")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_planner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement planner.py**

```python
# festival_organizer/planner.py
"""Plan builder: creates FileAction list from analysed MediaFiles."""
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.models import FileAction, MediaFile
from festival_organizer.templates import render_filename, render_folder


def plan_actions(
    files: list[MediaFile],
    output_root: Path,
    config: Config,
    action: str = "move",
    layout_name: str | None = None,
    generate_nfo: bool = False,
    extract_art: bool = False,
) -> list[FileAction]:
    """Build a list of FileActions for all files.

    Args:
        files: Analysed MediaFile objects
        output_root: Target root directory
        config: Configuration
        action: "move", "copy", or "rename"
        layout_name: Override layout (default uses config.default_layout)
        generate_nfo: Whether to generate Kodi NFO files
        extract_art: Whether to extract cover art
    """
    actions = []

    for mf in files:
        folder_rel = render_folder(mf, config, layout_name)
        filename = render_filename(mf, config)

        if action == "rename":
            # Rename in place — keep original directory
            target = mf.source_path.parent / filename
        else:
            target = output_root / folder_rel / filename

        actions.append(FileAction(
            source=mf.source_path,
            target=target,
            media_file=mf,
            action=action,
            generate_nfo=generate_nfo,
            extract_art=extract_art,
        ))

    return actions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_planner.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/planner.py tests/test_planner.py
git commit -m "feat: add planner to build FileAction list from analysed files"
```

---

### Task 11: Executor

**Files:**
- Create: `festival_organizer/executor.py`
- Create: `tests/test_executor.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_executor.py
import tempfile
from pathlib import Path
from festival_organizer.executor import execute_actions, resolve_collision
from festival_organizer.models import FileAction, MediaFile


def _make_action(source: Path, target: Path, action: str = "move") -> FileAction:
    mf = MediaFile(source_path=source)
    return FileAction(source=source, target=target, media_file=mf, action=action)


def test_execute_move():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "source.mkv"
        src.write_text("video data")
        target = root / "dest" / "output.mkv"

        action = _make_action(src, target, "move")
        results = execute_actions([action])

        assert results[0].status == "done"
        assert target.exists()
        assert not src.exists()


def test_execute_copy():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "source.mkv"
        src.write_text("video data")
        target = root / "dest" / "output.mkv"

        action = _make_action(src, target, "copy")
        results = execute_actions([action])

        assert results[0].status == "done"
        assert target.exists()
        assert src.exists()  # Original still present


def test_execute_rename():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "old_name.mkv"
        src.write_text("video data")
        target = root / "new_name.mkv"

        action = _make_action(src, target, "rename")
        results = execute_actions([action])

        assert results[0].status == "done"
        assert target.exists()
        assert not src.exists()


def test_execute_skip_same_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "same.mkv"
        src.write_text("data")

        action = _make_action(src, src)
        results = execute_actions([action])

        assert results[0].status == "skipped"
        assert src.exists()


def test_resolve_collision():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        existing = root / "file.mkv"
        existing.write_text("existing")

        resolved = resolve_collision(existing)
        assert resolved == root / "file (1).mkv"

        # Create the (1) too
        resolved.write_text("collision 1")
        resolved2 = resolve_collision(existing)
        assert resolved2 == root / "file (2).mkv"


def test_resolve_collision_no_conflict():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "new.mkv"
        assert resolve_collision(target) == target


def test_execute_handles_collision():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "source.mkv"
        src.write_text("new data")
        target = root / "dest" / "output.mkv"
        target.parent.mkdir()
        target.write_text("existing data")

        action = _make_action(src, target, "move")
        results = execute_actions([action])

        assert results[0].status == "done"
        # Should have been moved to output (1).mkv
        assert "output (1).mkv" in results[0].target.name


def test_execute_error_handling():
    """Non-existent source should produce error status."""
    action = _make_action(Path("C:/nonexistent.mkv"), Path("C:/out.mkv"))
    results = execute_actions([action])
    assert results[0].status == "error"
    assert results[0].error != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_executor.py -v`
Expected: FAIL

- [ ] **Step 3: Implement executor.py**

```python
# festival_organizer/executor.py
"""File executor: moves, copies, or renames files with collision handling."""
import shutil
from pathlib import Path

from festival_organizer.models import FileAction


def resolve_collision(target: Path) -> Path:
    """If target exists, append (1), (2), etc. until a free name is found."""
    if not target.exists():
        return target
    stem = target.stem
    ext = target.suffix
    parent = target.parent
    counter = 1
    while counter < 1000:
        candidate = parent / f"{stem} ({counter}){ext}"
        if not candidate.exists():
            return candidate
        counter += 1
    raise RuntimeError(f"Too many collisions for: {target}")


def execute_actions(actions: list[FileAction]) -> list[FileAction]:
    """Execute a list of file actions. Returns the same list with updated status.

    Never overwrites existing files — uses collision resolution.
    """
    for action in actions:
        try:
            # Skip if source and target are the same path
            if action.source.resolve() == action.target.resolve():
                action.status = "skipped"
                action.error = "Already at target location"
                continue

            # Resolve collisions
            final_target = resolve_collision(action.target)
            action.target = final_target

            # Create target directory
            final_target.parent.mkdir(parents=True, exist_ok=True)

            # Execute
            if action.action == "copy":
                shutil.copy2(str(action.source), str(final_target))
            else:
                # Both "move" and "rename" use shutil.move
                shutil.move(str(action.source), str(final_target))

            action.status = "done"

        except Exception as e:
            action.status = "error"
            action.error = str(e)

    return actions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_executor.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/executor.py tests/test_executor.py
git commit -m "feat: add executor with collision handling (move/copy/rename)"
```

---

### Task 12: Kodi NFO Generation

**Files:**
- Create: `festival_organizer/nfo.py`
- Create: `tests/test_nfo.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_nfo.py
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from festival_organizer.nfo import generate_nfo
from festival_organizer.config import Config, DEFAULT_CONFIG
from festival_organizer.models import MediaFile

CFG = Config(DEFAULT_CONFIG)


def test_generate_nfo_festival_set():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "2024 - AMF - Martin Garrix.mkv"
        video_path.touch()

        mf = MediaFile(
            source_path=video_path,
            artist="Martin Garrix",
            festival="AMF",
            year="2024",
            date="2024-10-19",
            content_type="festival_set",
            stage="Johan Cruijff ArenA",
            tracklists_url="https://www.1001tracklists.com/tracklist/qv6kl89/",
            duration_seconds=7200.0,
            width=3840,
            height=2160,
            video_format="VP9",
            audio_format="Opus",
            extension=".mkv",
        )

        nfo_path = generate_nfo(mf, video_path, CFG)

        assert nfo_path.exists()
        assert nfo_path.suffix == ".nfo"
        assert nfo_path.stem == video_path.stem

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        assert root.tag == "musicvideo"
        assert root.find("title").text == "2024 - AMF - Martin Garrix"
        assert root.find("artist").text == "Martin Garrix"
        assert root.find("album").text == "AMF"
        assert root.find("year").text == "2024"
        assert root.find("genre").text == "Electronic"
        assert root.find("premiered").text == "2024-10-19"
        assert "1001tracklists" in root.find("plot").text


def test_generate_nfo_concert_film():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "Coldplay - A Head Full of Dreams.mkv"
        video_path.touch()

        mf = MediaFile(
            source_path=video_path,
            artist="Coldplay",
            title="A Head Full of Dreams",
            year="2018",
            content_type="concert_film",
            duration_seconds=6240.0,
            width=1920,
            height=1080,
            video_format="AVC",
            audio_format="E-AC-3",
            extension=".mkv",
        )

        nfo_path = generate_nfo(mf, video_path, CFG)

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        assert root.find("artist").text == "Coldplay"
        assert root.find("album").text == "A Head Full of Dreams"
        assert root.find("genre").text == "Live"


def test_generate_nfo_with_streamdetails():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "test.mkv"
        video_path.touch()

        mf = MediaFile(
            source_path=video_path,
            artist="Test",
            festival="AMF",
            year="2024",
            content_type="festival_set",
            width=3840,
            height=2160,
            video_format="VP9",
            audio_format="Opus",
            extension=".mkv",
        )

        nfo_path = generate_nfo(mf, video_path, CFG)

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        vstream = root.find(".//fileinfo/streamdetails/video")
        assert vstream is not None
        assert vstream.find("codec").text == "VP9"
        assert vstream.find("width").text == "3840"
        assert vstream.find("height").text == "2160"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_nfo.py -v`
Expected: FAIL

- [ ] **Step 3: Implement nfo.py**

```python
# festival_organizer/nfo.py
"""Kodi musicvideo NFO XML generation."""
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

from festival_organizer.config import Config
from festival_organizer.models import MediaFile


def generate_nfo(media_file: MediaFile, video_path: Path, config: Config) -> Path:
    """Generate a Kodi-compatible NFO XML file alongside a video file.

    Returns the path to the generated .nfo file.
    """
    nfo_path = video_path.with_suffix(".nfo")
    nfo_settings = config.nfo_settings

    root = ET.Element("musicvideo")

    # Title — use the rendered filename stem
    _add_element(root, "title", video_path.stem)

    # Artist
    _add_element(root, "artist", media_file.artist or "Unknown Artist")

    # Album — festival name for sets, title for concerts
    if media_file.content_type == "festival_set":
        album = media_file.festival or media_file.title or ""
        if media_file.location:
            display = config.get_festival_display(media_file.festival, media_file.location)
            if display != media_file.festival:
                album = display
    else:
        album = media_file.title or media_file.festival or ""
    _add_element(root, "album", album)

    # Year
    if media_file.year:
        _add_element(root, "year", media_file.year)

    # Genre
    if media_file.content_type == "festival_set":
        _add_element(root, "genre", nfo_settings.get("genre_festival", "Electronic"))
    else:
        _add_element(root, "genre", nfo_settings.get("genre_concert", "Live"))

    # Premiered (date)
    if media_file.date:
        _add_element(root, "premiered", media_file.date)

    # Plot — tracklist URL or description
    plot_parts = []
    if media_file.stage:
        plot_parts.append(f"Stage: {media_file.stage}")
    if media_file.location:
        plot_parts.append(f"Location: {media_file.location}")
    if media_file.tracklists_url:
        plot_parts.append(f"Tracklist: {media_file.tracklists_url}")
    if plot_parts:
        _add_element(root, "plot", "\n".join(plot_parts))

    # Runtime (minutes)
    if media_file.duration_seconds:
        runtime_min = int(media_file.duration_seconds) // 60
        _add_element(root, "runtime", str(runtime_min))

    # Poster reference (if cover art will be extracted)
    if media_file.has_cover:
        thumb = ET.SubElement(root, "thumb", aspect="poster")
        thumb.text = "poster.png"

    # Stream details
    if media_file.video_format or media_file.audio_format:
        fileinfo = ET.SubElement(root, "fileinfo")
        streamdetails = ET.SubElement(fileinfo, "streamdetails")

        if media_file.video_format:
            video = ET.SubElement(streamdetails, "video")
            _add_element(video, "codec", media_file.video_format)
            if media_file.width:
                _add_element(video, "width", str(media_file.width))
            if media_file.height:
                _add_element(video, "height", str(media_file.height))

        if media_file.audio_format:
            audio = ET.SubElement(streamdetails, "audio")
            _add_element(audio, "codec", media_file.audio_format)

    # Write with pretty-printing
    xml_str = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    # Remove the XML declaration that minidom adds (Kodi prefers without)
    lines = xml_str.split("\n")
    if lines[0].startswith("<?xml"):
        xml_str = "\n".join(lines[1:])

    nfo_path.write_text(xml_str.strip() + "\n", encoding="utf-8")
    return nfo_path


def _add_element(parent: ET.Element, tag: str, text: str) -> ET.Element:
    """Add a child element with text content."""
    elem = ET.SubElement(parent, tag)
    elem.text = text
    return elem
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_nfo.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/nfo.py tests/test_nfo.py
git commit -m "feat: add Kodi musicvideo NFO XML generation"
```

---

### Task 13: Artwork Extraction

**UPDATE:** Save extracted cover art as `videoname-thumb.jpg` (not `cover.png`). This is the Kodi video thumbnail, referenced in NFO via `<thumb>videoname-thumb.jpg</thumb>`. Save at original resolution — Kodi/Plex cache their own scaled versions. When no embedded cover exists, fall back to `frame_sampler.py` (Task 19).

**Files:**
- Create: `festival_organizer/artwork.py`
- Create: `tests/test_artwork.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_artwork.py
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from festival_organizer.artwork import extract_cover, find_mkvextract


def test_find_mkvextract():
    with patch("os.path.isfile", side_effect=lambda p: "MKVToolNix" in p):
        result = find_mkvextract()
        assert result is not None
        assert "mkvextract" in result.lower()


def test_find_mkvextract_not_installed():
    with patch("shutil.which", return_value=None):
        with patch("os.path.isfile", return_value=False):
            assert find_mkvextract() is None


def test_extract_cover_no_tool(tmp_path):
    """Should return None if mkvextract is not available."""
    with patch("festival_organizer.artwork.MKVEXTRACT_PATH", None):
        result = extract_cover(Path("test.mkv"), tmp_path)
        assert result is None


def test_extract_cover_success(tmp_path):
    """Should call mkvextract and return poster path on success."""
    source = tmp_path / "source.mkv"
    source.touch()
    target_dir = tmp_path / "output"
    target_dir.mkdir()

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("festival_organizer.artwork.MKVEXTRACT_PATH", "mkvextract"):
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            # Simulate that the file was created by mkvextract
            poster = target_dir / "poster.png"
            poster.touch()

            result = extract_cover(source, target_dir)
            assert result == poster
            mock_run.assert_called_once()


def test_extract_cover_no_attachment(tmp_path):
    """Should return None if mkvextract produces no file."""
    source = tmp_path / "source.mkv"
    source.touch()
    target_dir = tmp_path / "output"
    target_dir.mkdir()

    mock_result = MagicMock()
    mock_result.returncode = 1

    with patch("festival_organizer.artwork.MKVEXTRACT_PATH", "mkvextract"):
        with patch("subprocess.run", return_value=mock_result):
            result = extract_cover(source, target_dir)
            assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_artwork.py -v`
Expected: FAIL

- [ ] **Step 3: Implement artwork.py**

```python
# festival_organizer/artwork.py
"""Cover art extraction from MKV attachments via mkvextract."""
import os
import shutil
import subprocess
from pathlib import Path


def find_mkvextract() -> str | None:
    """Locate mkvextract executable."""
    found = shutil.which("mkvextract")
    if found:
        return found
    for candidate in [
        r"C:\Program Files\MKVToolNix\mkvextract.exe",
        r"C:\Program Files (x86)\MKVToolNix\mkvextract.exe",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


MKVEXTRACT_PATH = find_mkvextract()


def extract_cover(source: Path, target_dir: Path) -> Path | None:
    """Extract the first attachment (cover art) from an MKV file.

    Saves as poster.png in the target directory.
    Returns the path to the extracted file, or None on failure.
    """
    if not MKVEXTRACT_PATH:
        return None

    poster_path = target_dir / "poster.png"

    try:
        # mkvextract attachments <file> <attachment_id>:<output_path>
        # Attachment ID 1 is typically the cover image
        result = subprocess.run(
            [MKVEXTRACT_PATH, str(source), "attachments", f"1:{poster_path}"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0 and poster_path.exists():
            return poster_path
        return None
    except Exception:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_artwork.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/artwork.py tests/test_artwork.py
git commit -m "feat: add MKV cover art extraction via mkvextract"
```

---

### Task 14: Logging Utility

**Files:**
- Create: `festival_organizer/logging_util.py`
- Create: `tests/test_logging_util.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_logging_util.py
import csv
import io
import tempfile
from pathlib import Path
from festival_organizer.logging_util import ActionLogger
from festival_organizer.models import FileAction, MediaFile


def test_logger_records_actions():
    logger = ActionLogger(verbose=False)
    mf = MediaFile(source_path=Path("src.mkv"), artist="Test", festival="AMF", year="2024")
    fa = FileAction(source=Path("src.mkv"), target=Path("dst.mkv"), media_file=mf, status="done")
    logger.log_action(fa)
    assert len(logger.rows) == 1
    assert logger.rows[0]["status"] == "done"


def test_logger_stats():
    logger = ActionLogger(verbose=False)
    mf = MediaFile(source_path=Path("a.mkv"))
    logger.log_action(FileAction(source=Path("a"), target=Path("b"), media_file=mf, status="done"))
    logger.log_action(FileAction(source=Path("c"), target=Path("d"), media_file=mf, status="error", error="oops"))
    logger.log_action(FileAction(source=Path("e"), target=Path("f"), media_file=mf, status="done"))
    stats = logger.stats
    assert stats["done"] == 2
    assert stats["error"] == 1


def test_logger_save_csv():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "test.csv"
        logger = ActionLogger(verbose=False)
        mf = MediaFile(source_path=Path("src.mkv"), artist="Martin Garrix", festival="AMF", year="2024")
        fa = FileAction(source=Path("src.mkv"), target=Path("dst.mkv"), media_file=mf, status="done")
        logger.log_action(fa)
        logger.save_csv(log_path)

        assert log_path.exists()
        with open(log_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["artist"] == "Martin Garrix"
        assert rows[0]["status"] == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_logging_util.py -v`
Expected: FAIL

- [ ] **Step 3: Implement logging_util.py**

```python
# festival_organizer/logging_util.py
"""Logging: console output and CSV export."""
import csv
import io
import sys
from pathlib import Path

from festival_organizer.models import FileAction

# Force UTF-8 on Windows console
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


CSV_FIELDS = [
    "status", "source", "target",
    "artist", "festival", "year", "date", "set_title",
    "stage", "location", "content_type", "file_type",
    "resolution", "duration", "video_format", "audio_format",
    "metadata_source", "tracklists_url", "error",
]


class ActionLogger:
    """Collects action results for display and CSV export."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.rows: list[dict] = []

    def log_action(self, action: FileAction) -> None:
        """Record and optionally print a file action."""
        mf = action.media_file
        row = {
            "status": action.status,
            "source": str(action.source),
            "target": str(action.target),
            "artist": mf.artist,
            "festival": mf.festival,
            "year": mf.year,
            "date": mf.date,
            "set_title": mf.set_title,
            "stage": mf.stage,
            "location": mf.location,
            "content_type": mf.content_type,
            "file_type": mf.file_type,
            "resolution": mf.resolution,
            "duration": mf.duration_formatted,
            "video_format": mf.video_format,
            "audio_format": mf.audio_format,
            "metadata_source": mf.metadata_source,
            "tracklists_url": mf.tracklists_url,
            "error": action.error,
        }
        self.rows.append(row)

        if self.verbose:
            self._print_action(action)

    def _print_action(self, action: FileAction) -> None:
        status_labels = {
            "pending": "DRY",
            "done": " OK",
            "skipped": "SKIP",
            "error": "ERR",
        }
        label = status_labels.get(action.status, action.status.upper())
        ct = action.media_file.content_type or "?"
        print(f"  [{label:>4}] [{ct:<12}] {action.source}")
        if action.status in ("pending", "done"):
            print(f"         --> {action.target}")
        if action.error:
            print(f"         !!! {action.error}")

    def save_csv(self, path: Path) -> None:
        """Write all recorded actions to a CSV file."""
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.rows)

    @property
    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.rows:
            s = row.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        return counts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_logging_util.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/logging_util.py tests/test_logging_util.py
git commit -m "feat: add action logger with console output and CSV export"
```

---

### Task 15: CLI and Pipeline Orchestration

**Files:**
- Create: `festival_organizer/cli.py`
- Rewrite: `organize.py`

- [ ] **Step 1: Implement cli.py**

```python
# festival_organizer/cli.py
"""Command-line interface with subcommands."""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from festival_organizer.analyzer import analyse_file
from festival_organizer.artwork import extract_cover
from festival_organizer.classifier import classify
from festival_organizer.config import load_config
from festival_organizer.executor import execute_actions
from festival_organizer.logging_util import ActionLogger
from festival_organizer.metadata import MEDIAINFO_PATH, FFPROBE_PATH
from festival_organizer.nfo import generate_nfo
from festival_organizer.planner import plan_actions
from festival_organizer.scanner import scan_folder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="organize",
        description="Festival Set Organizer — scan, rename, and sort media files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # Common arguments
    def add_common(p):
        p.add_argument("root", type=str, help="Root folder to scan")
        p.add_argument("--output", "-o", type=str, help="Output folder (default: same as root)")
        p.add_argument("--layout", choices=["artist_first", "festival_first"], help="Folder layout")
        p.add_argument("--config", type=str, help="Path to config.json")
        p.add_argument("--quiet", "-q", action="store_true", help="Suppress per-file output")

    # scan (dry-run)
    scan_p = sub.add_parser("scan", help="Dry-run: show what would be changed")
    add_common(scan_p)

    # execute
    exec_p = sub.add_parser("execute", help="Move/rename files")
    add_common(exec_p)
    exec_p.add_argument("--copy", action="store_true", help="Copy instead of move")
    exec_p.add_argument("--rename-only", action="store_true", help="Rename in place only")
    exec_p.add_argument("--generate-nfo", action="store_true", help="Generate Kodi NFO files")
    exec_p.add_argument("--extract-art", action="store_true", help="Extract cover art from MKV")

    # nfo (generate NFOs only)
    nfo_p = sub.add_parser("nfo", help="Generate Kodi NFO files without moving")
    add_common(nfo_p)

    # extract-art (extract cover art only)
    art_p = sub.add_parser("extract-art", help="Extract cover art without moving")
    add_common(art_p)

    return parser


def run(argv: list[str] | None = None) -> int:
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    root = Path(args.root)
    if not root.exists():
        print(f"Error: folder does not exist: {root}", file=sys.stderr)
        return 1

    # Load config
    config_path = Path(args.config) if args.config else Path("config.json")
    config = load_config(config_path if config_path.exists() else None)

    # Override layout if specified
    if args.layout:
        config._data["default_layout"] = args.layout

    output = Path(args.output) if args.output else root
    verbose = not args.quiet

    # Header
    dry_run = args.command == "scan"
    mode = "DRY-RUN" if dry_run else args.command.upper()
    print(f"Festival Set Organizer")
    print(f"{'=' * 60}")
    print(f"Source:  {root}")
    print(f"Output:  {output}")
    print(f"Mode:    {mode}")
    print(f"Layout:  {config.default_layout}")
    if MEDIAINFO_PATH:
        print(f"Tool:    MediaInfo ({MEDIAINFO_PATH})")
    elif FFPROBE_PATH:
        print(f"Tool:    ffprobe ({FFPROBE_PATH})")
    else:
        print(f"Tool:    NONE (filename parsing only)")
    print(f"{'=' * 60}\n")

    # Scan
    print("Scanning...")
    files = scan_folder(root, config)
    print(f"Found {len(files)} media file(s).\n")
    if not files:
        print("Nothing to do.")
        return 0

    # Analyse + classify
    media_files = []
    for fp in files:
        mf = analyse_file(fp, root, config)
        mf.content_type = classify(mf, root, config)
        media_files.append(mf)

    # Determine action type
    action_type = "move"
    if hasattr(args, "copy") and args.copy:
        action_type = "copy"
    elif hasattr(args, "rename_only") and args.rename_only:
        action_type = "rename"

    gen_nfo = hasattr(args, "generate_nfo") and args.generate_nfo
    ext_art = hasattr(args, "extract_art") and args.extract_art

    # Handle nfo/extract-art subcommands
    if args.command == "nfo":
        return _run_nfo_only(media_files, output, config, verbose)
    if args.command == "extract-art":
        return _run_extract_art_only(media_files, output, config, verbose)

    # Plan
    actions = plan_actions(
        media_files, output, config,
        action=action_type,
        layout_name=args.layout,
        generate_nfo=gen_nfo,
        extract_art=ext_art,
    )

    # Log
    logger = ActionLogger(verbose=verbose)

    if dry_run:
        for a in actions:
            a.status = "pending"
            logger.log_action(a)
    else:
        # Execute
        execute_actions(actions)
        for a in actions:
            logger.log_action(a)

            # Post-move tasks
            if a.status == "done":
                if a.generate_nfo:
                    generate_nfo(a.media_file, a.target, config)
                if a.extract_art and a.media_file.has_cover:
                    extract_cover(a.source, a.target.parent)

    # Save log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = output if not dry_run else Path(".")
    log_path = log_dir / f"organizer_log_{timestamp}.csv"
    try:
        logger.save_csv(log_path)
    except PermissionError:
        # Fall back to current directory
        log_path = Path(f"organizer_log_{timestamp}.csv")
        logger.save_csv(log_path)

    # Summary
    stats = logger.stats
    print(f"\n{'=' * 60}")
    print("Summary:")
    for status, count in sorted(stats.items()):
        print(f"  {status}: {count}")
    print(f"Log: {log_path}")
    print(f"{'=' * 60}")

    return 0


def _run_nfo_only(media_files, output, config, verbose):
    """Generate NFO files for all files without moving them."""
    count = 0
    for mf in media_files:
        nfo_path = generate_nfo(mf, mf.source_path, config)
        if verbose:
            print(f"  [NFO] {nfo_path}")
        count += 1
    print(f"\nGenerated {count} NFO file(s).")
    return 0


def _run_extract_art_only(media_files, output, config, verbose):
    """Extract cover art from all files without moving them."""
    count = 0
    for mf in media_files:
        if mf.has_cover:
            result = extract_cover(mf.source_path, mf.source_path.parent)
            if result and verbose:
                print(f"  [ART] {result}")
                count += 1
    print(f"\nExtracted {count} cover art file(s).")
    return 0
```

- [ ] **Step 2: Rewrite organize.py as thin wrapper**

```python
#!/usr/bin/env python3
"""Festival Set Organizer — CLI entry point."""
import sys
from festival_organizer.cli import run

sys.exit(run())
```

- [ ] **Step 3: Run all tests to verify nothing is broken**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 4: Smoke test dry-run against real collection**

Run: `cd /c/GitHub/CrateDigger && python organize.py scan "\\\\hyperv\\Data\\Concerts" 2>&1 | head -40`
Expected: Shows header, file count, and dry-run output with `[DRY]` tags. No errors.

- [ ] **Step 5: Commit**

```bash
cd /c/GitHub/CrateDigger
git add festival_organizer/cli.py organize.py
git commit -m "feat: add CLI with scan/execute/nfo/extract-art subcommands"
```

---

### Task 16: Integration Test Against Real Collection

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""Integration test: dry-run against the real \\hyperv\Data\Concerts collection.

Skip if the network share is not accessible.
"""
import pytest
from pathlib import Path

from festival_organizer.analyzer import analyse_file
from festival_organizer.classifier import classify
from festival_organizer.config import Config, DEFAULT_CONFIG, load_config
from festival_organizer.planner import plan_actions
from festival_organizer.scanner import scan_folder

CONCERTS_ROOT = Path("//hyperv/Data/Concerts")
SKIP_REASON = "Network share not accessible"


@pytest.fixture
def config():
    config_path = Path("config.json")
    return load_config(config_path if config_path.exists() else None)


@pytest.mark.skipif(not CONCERTS_ROOT.exists(), reason=SKIP_REASON)
class TestRealCollection:

    def test_scan_finds_files(self, config):
        files = scan_folder(CONCERTS_ROOT, config)
        assert len(files) >= 60  # We know there are 72+
        # Should not include BDMV files
        for f in files:
            assert "BDMV" not in str(f)

    def test_all_files_analyse_without_error(self, config):
        files = scan_folder(CONCERTS_ROOT, config)
        for fp in files:
            mf = analyse_file(fp, CONCERTS_ROOT, config)
            assert mf.source_path == fp
            # Every file should have at least extension set
            assert mf.extension != ""

    def test_all_files_classify(self, config):
        files = scan_folder(CONCERTS_ROOT, config)
        types = {"festival_set": 0, "concert_film": 0, "unknown": 0}
        for fp in files:
            mf = analyse_file(fp, CONCERTS_ROOT, config)
            ct = classify(mf, CONCERTS_ROOT, config)
            assert ct in types
            types[ct] += 1
        # We expect at least some festival sets and some concert films
        assert types["festival_set"] > 0
        assert types["concert_film"] > 0

    def test_amf_2024_martin_garrix(self, config):
        """Specific file: AMF 2024 Martin Garrix — should have 1001TL metadata."""
        files = scan_folder(CONCERTS_ROOT, config)
        target = [f for f in files if "MARTIN GARRIX" in f.name.upper() and "AMF" in str(f).upper() and "2024" in str(f)]
        assert len(target) >= 1
        mf = analyse_file(target[0], CONCERTS_ROOT, config)
        assert mf.artist == "Martin Garrix"
        assert mf.festival == "AMF"
        assert mf.year == "2024"
        assert mf.metadata_source == "1001tracklists"

    def test_tomorrowland_belgium_hardwell(self, config):
        """Specific: Tomorrowland Belgium Hardwell WE1."""
        files = scan_folder(CONCERTS_ROOT, config)
        target = [f for f in files if "Hardwell WE1" in f.name]
        assert len(target) >= 1
        mf = analyse_file(target[0], CONCERTS_ROOT, config)
        assert mf.artist == "Hardwell"
        assert mf.festival == "Tomorrowland"
        assert mf.location == "Belgium"
        assert mf.set_title == "WE1"

    def test_adele_classified_as_concert(self, config):
        """Adele files should be concert_film."""
        files = scan_folder(CONCERTS_ROOT, config)
        adele = [f for f in files if "Adele" in str(f)]
        assert len(adele) >= 1
        for fp in adele:
            mf = analyse_file(fp, CONCERTS_ROOT, config)
            ct = classify(mf, CONCERTS_ROOT, config)
            assert ct == "concert_film"

    def test_plan_produces_no_duplicate_targets(self, config):
        """No two files should map to the same target path."""
        files = scan_folder(CONCERTS_ROOT, config)
        media_files = []
        for fp in files:
            mf = analyse_file(fp, CONCERTS_ROOT, config)
            mf.content_type = classify(mf, CONCERTS_ROOT, config)
            media_files.append(mf)
        actions = plan_actions(media_files, Path("C:/Test/Output"), config)
        targets = [str(a.target) for a in actions]
        # Allow soft check — some may collide but shouldn't be many
        unique = set(targets)
        collision_count = len(targets) - len(unique)
        assert collision_count < 5, f"Too many target collisions: {collision_count}"
```

- [ ] **Step 2: Run integration tests**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/test_integration.py -v --timeout=120`
Expected: all passed (or skipped if network share not accessible)

- [ ] **Step 3: Commit**

```bash
cd /c/GitHub/CrateDigger
git add tests/test_integration.py
git commit -m "test: add integration tests against real concert collection"
```

---

### Task 17: Full Dry-Run Verification and Cleanup

- [ ] **Step 1: Run all tests**

Run: `cd /c/GitHub/CrateDigger && python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 2: Run full dry-run and inspect output**

Run: `cd /c/GitHub/CrateDigger && python organize.py scan "\\\\hyperv\\Data\\Concerts" 2>&1`

Verify:
- AMF files → `Martin Garrix/AMF/2024/2024 - AMF - Martin Garrix.mkv`
- Tomorrowland Belgium → `Hardwell/Tomorrowland Belgium/2025/2025 - Tomorrowland Belgium - Hardwell - WE1.mkv`
- Tomorrowland Brasil → `Alok/Tomorrowland Brasil/2025/2025 - Tomorrowland Brasil - Alok.mkv`
- EDC files → `Armin van Buuren/EDC Las Vegas/2025/...`
- Adele → `Adele/2011 - Live At The Royal Albert Hall/...`
- U2 → `U2/Unknown Year - Go Home - Live From Slane Castle/...`
- Dolby BDMV files → NOT in output
- WE1/WE2 → in filename as set_title

- [ ] **Step 3: Fix any parsing issues found in verification**

If specific files produce wrong results, update the relevant parser/analyzer test and fix.

- [ ] **Step 4: Delete old monolith organize.py draft**

The old monolith has been fully replaced by the package. The new `organize.py` is the 3-line entry point.

- [ ] **Step 5: Final commit**

```bash
cd /c/GitHub/CrateDigger
git add -A
git commit -m "feat: complete festival set organizer v0.1.0"
```

---

### Task 18: Poster Generation Module

**Files:**
- Create: `festival_organizer/poster.py`
- Create: `tests/test_poster.py`

**IMPORTANT:** The poster layout was extensively prototyped and approved. The reference implementations are at `C:\TEMP\poster-test\text_v5b.py` (set posters) and `C:\TEMP\poster-test\album_poster_v3.py` (album posters). Follow the code structure closely — every constant and calculation was tuned through ~15 iterations.

- [ ] **Step 1: Write tests for poster generation**

Tests should verify:
- Poster output is 1000x1500
- Artist name splitting: parenthetical `"Act (A & B)"` → `("Act", "A & B")`, connectors `"A & B"` → `("A", "& B")`, no split on word count `"Swedish House Mafia"` → `("Swedish House Mafia", None)`
- Accent color extraction produces valid RGB tuple
- Font auto-sizing: long names get smaller font, short names get larger
- `generate_set_poster()` creates a file
- `generate_album_poster()` creates a file

- [ ] **Step 2: Implement poster.py**

The module must include:

**Constants (line-anchored layout):**
```python
POSTER_W, POSTER_H = 1000, 1500
LINE_Y = int(POSTER_H * 0.67)  # accent line at 2/3
LINE_H = 4
PAD_LINE_TO_ARTIST = 28
PAD_ARTIST_LINES = 6
PAD_LINE_TO_FEST = 30
PAD_FEST_TO_YEAR = 22
PAD_YEAR_TO_DETAIL = 22
```

**Artist name splitting (order matters):**
```python
import re

def split_artist(name):
    # 1. Parenthetical: "Act Name (Artist & Artist)" → ("Act Name", "Artist & Artist")
    paren_match = re.match(r'^(.+?)\s*\((.+)\)\s*$', name)
    if paren_match:
        return paren_match.group(1).strip(), paren_match.group(2).strip()
    # 2. Connectors: & B2B vs x
    upper = name.upper()
    for sep in [" & ", " B2B ", " VS ", " X "]:
        if sep in upper:
            idx = upper.index(sep)
            return name[:idx].strip(), name[idx:].strip()
    # 3. No split
    return name, None
```

**Set poster layout (generate_set_poster):**
- Source image flush to top (img_y = 0)
- Blurred + darkened copy as full background
- Sharp image with fade mask (starts at 60% of image height)
- Dark gradient from 40% down
- Text positioning uses `font.getmetrics()` ascent+descent (NOT `getbbox` height — that varies per glyph)
- Artist builds UP from LINE_Y, festival/date/detail build DOWN
- Accent color from image mean HSV
- Festival name + accent line have glow effects (Pillow GaussianBlur on RGBA layer)
- Letter spacing on artist name
- Drop shadow on all text (2-3px offset, black alpha 160)

**Album poster layout (generate_album_poster):**
- No image — clean editorial gradient background
- Color derived from thumbnails mean HSV, or config override
- Gradient: lighter at top-center (radial highlight), darker at bottom
- Subtle noise grain for texture
- Festival name is the hero (above line, larger font 130pt start)
- Date/venue below line
- No set count
- Accent color: brighter derivative of base color

**Key details that took many iterations to get right:**
- `img_y = 0` (flush top, no black bar)
- Font sizing uses `font_visual_height()` = `ascent + descent` for consistent baselines
- Letter spacing calculated as: `max(2, min(8, remaining_space // char_count))`
- Glow = draw text 3x at decreasing opacity on RGBA layer → GaussianBlur → composite
- Date line shows `"28 March 2025"` when full date available, else just `"2025"`

- [ ] **Step 3: Run tests**
- [ ] **Step 4: Commit**

---

### Task 19: Frame Sampler (Fallback for Missing Embedded Art)

**Files:**
- Create: `festival_organizer/frame_sampler.py`

- [ ] **Step 1: Implement frame_sampler.py**

```python
def sample_best_frame(video_path: str, num_samples: int = 50) -> Path | None:
```

Logic:
- Open video with OpenCV `cv2.VideoCapture`
- Get total frames, skip first/last 5%
- Sample `num_samples` evenly-spaced frames
- Score each by vibrancy: `mean_saturation * mean_brightness` (HSV channels)
- Soft sharpness bonus: `log1p(laplacian_variance) / 15`
- Exposure quality: gaussian around 0.45 brightness
- Skip near-black frames (brightness < 0.08)
- Save winning frame as PNG, return path

**Performance:** ~12 sec for 1080p 1.9GB file, ~8 min for 4K 6.2GB (seek-bound). Acceptable.

- [ ] **Step 2: Integrate with artwork.py** — call frame_sampler when no embedded cover found
- [ ] **Step 3: Commit**

---

### Task 20: Album NFO Generation

**Files:**
- Create: `festival_organizer/album_nfo.py`

- [ ] **Step 1: Implement album_nfo.py**

Generate `album.nfo` with `<album>` root element containing `<title>`, `<year>`, `<genre>`, `<plot>`.

For `festival_first` layout: title = "AMF 2024", plot includes venue/location.
For `artist_first` layout: title = "Martin Garrix — AMF 2024".

- [ ] **Step 2: Integrate with planner.py** — generate album.nfo + poster.jpg + folder.jpg per output folder
- [ ] **Step 3: Commit**

---

### Task 21: Plex Tag Embedding (opt-in)

**Files:**
- Create: `festival_organizer/embed_tags.py`

- [ ] **Step 1: Implement embed_tags.py**

Use `mkvpropedit` to embed tags into MKV files:
- Artist, title, date via MKV tag XML
- Only runs on DESTINATION files (never source)
- Gated by `--embed-tags` CLI flag

- [ ] **Step 2: Add --embed-tags flag to CLI**
- [ ] **Step 3: Commit**

---

## Self-Review Checklist

**1. Spec coverage:**
- [x] Recursive scan — Task 9 (scanner)
- [x] Video/audio extensions — Task 2 (config)
- [x] MediaInfo/ffprobe metadata — Task 5 (metadata)
- [x] Artist/festival/year/date parsing — Tasks 3-4 (normalization, parsers)
- [x] 1001TL title parsing — Task 4 (parsers)
- [x] Filename patterns — Task 4 (parsers, 6 patterns + fallback)
- [x] Name normalization — Task 3 (normalization)
- [x] Consistent rename format — Task 8 (templates)
- [x] Configurable folder structure — Tasks 2, 8 (config, templates)
- [x] Dry-run mode — Task 15 (CLI, default behavior)
- [x] CSV log — Task 14 (logging_util)
- [x] Collision handling — Task 11 (executor)
- [x] Skip non-media — Task 9 (scanner)
- [x] Robust against missing metadata — Task 6 (analyzer fallbacks)
- [x] CLI with flags — Task 15
- [x] Two content types — Task 7 (classifier)
- [x] Kodi NFO generation — Task 12
- [x] Cover art extraction — Task 13
- [x] Set poster generation (v5b layout) — Task 18
- [x] Album poster generation (editorial gradient) — Task 18
- [x] Frame sampling fallback — Task 19
- [x] Album NFO generation — Task 20
- [x] Plex tag embedding — Task 21
- [x] Video thumbnails as videoname-thumb.jpg — Task 13
- [x] Festival location variants — Task 2, 8 (config festival_config, template rendering)
- [x] WE1/WE2 in filenames — Task 4, 8 (parsers, templates)
- [x] Configurable everything — Task 2 (config.json)
- [x] Artist-first default — Task 2 (config default_layout)

**2. Placeholder scan:** No TBD/TODO/placeholders found.

**3. Type consistency:**
- `MediaFile` used consistently across all modules
- `FileAction` used consistently in planner, executor, logger
- `Config` passed to all modules that need it
- `parse_1001tracklists_title(title, config)` — consistent 2-arg signature
- `parse_filename(filepath, config)` — consistent 2-arg signature
- `analyse_file(filepath, root, config)` — consistent 3-arg signature
- `classify(media_file, root, config)` — consistent 3-arg signature
