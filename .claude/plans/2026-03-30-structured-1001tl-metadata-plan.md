# Structured 1001TL Metadata — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Parse structured data from 1001TL page HTML to extract stage, venue, and source types — improving NFO titles, poster layout, and MKV tags.

**Architecture:** Add a source cache module that auto-populates from `/source/` pages. Parse the `<h1>` in `export_tracklist()` to extract structured fields. Thread new `stage_text` and `venue` through the tag pipeline, metadata reader, analyzer, NFO writer, and poster generator.

**Tech Stack:** Python, requests (existing session), PIL/Pillow (existing poster), xml.etree (existing NFO), JSON (cache)

**Design doc:** `docs/plans/2026-03-30-structured-1001tl-metadata-design.md`

---

### Task 1: Source cache module

**Files:**
- Create: `festival_organizer/tracklists/source_cache.py`
- Test: `tests/test_source_cache.py`

**Step 1: Write failing tests**

```python
# tests/test_source_cache.py
import json
from pathlib import Path
from festival_organizer.tracklists.source_cache import SourceCache


def test_cache_miss_returns_none(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "source_cache.json")
    assert cache.get("nonexistent") is None


def test_cache_put_and_get(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "source_cache.json")
    cache.put("abc123", {"name": "Tomorrowland", "slug": "tomorrowland",
                         "type": "Open Air / Festival", "country": "Belgium"})
    entry = cache.get("abc123")
    assert entry["name"] == "Tomorrowland"
    assert entry["type"] == "Open Air / Festival"
    assert entry["country"] == "Belgium"


def test_cache_persists_to_disk(tmp_path):
    path = tmp_path / "source_cache.json"
    cache1 = SourceCache(cache_path=path)
    cache1.put("abc123", {"name": "TML", "slug": "tml", "type": "Open Air / Festival", "country": "Belgium"})
    # New instance reads from disk
    cache2 = SourceCache(cache_path=path)
    assert cache2.get("abc123")["name"] == "TML"


def test_cache_file_auto_created(tmp_path):
    path = tmp_path / "sub" / "source_cache.json"
    cache = SourceCache(cache_path=path)
    cache.put("x", {"name": "X", "slug": "x", "type": "Club", "country": "US"})
    assert path.exists()
    data = json.loads(path.read_text())
    assert "x" in data


def test_find_by_type(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "source_cache.json")
    cache.put("a", {"name": "AMF", "slug": "amf", "type": "Open Air / Festival", "country": "Netherlands"})
    cache.put("b", {"name": "Johan Cruijff ArenA Amsterdam", "slug": "johan-cruijff-arena-amsterdam", "type": "Event Location", "country": "Netherlands"})
    cache.put("c", {"name": "ADE", "slug": "ade", "type": "Conference", "country": "Netherlands"})
    venues = cache.find_by_type(["a", "b", "c"], "Event Location")
    assert len(venues) == 1
    assert venues[0]["name"] == "Johan Cruijff ArenA Amsterdam"


def test_group_by_type(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "source_cache.json")
    cache.put("a", {"name": "AMF", "slug": "amf", "type": "Open Air / Festival", "country": "Netherlands"})
    cache.put("b", {"name": "Johan Cruijff ArenA Amsterdam", "slug": "johan-cruijff-arena-amsterdam", "type": "Event Location", "country": "Netherlands"})
    cache.put("c", {"name": "ADE", "slug": "ade", "type": "Conference", "country": "Netherlands"})
    grouped = cache.group_by_type(["a", "b", "c"])
    assert grouped["Open Air / Festival"] == ["AMF"]
    assert grouped["Event Location"] == ["Johan Cruijff ArenA Amsterdam"]
    assert grouped["Conference"] == ["ADE"]
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_source_cache.py -v`
Expected: ImportError — module doesn't exist yet

**Step 3: Implement source cache**

```python
# festival_organizer/tracklists/source_cache.py
"""Local cache for 1001Tracklists /source/ page metadata (type, country)."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path.home() / ".cratedigger" / "source_cache.json"


class SourceCache:
    """Read-through cache for 1001TL source page metadata.

    Keyed by source ID (e.g. "5tb5n3"). Each entry stores name, slug, type, country.
    Persists to ~/.cratedigger/source_cache.json.
    """

    def __init__(self, cache_path: Path | None = None):
        self._path = cache_path or DEFAULT_PATH
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.debug("Could not load source cache: %s", e)
                self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get(self, source_id: str) -> dict | None:
        return self._data.get(source_id)

    def put(self, source_id: str, entry: dict) -> None:
        self._data[source_id] = entry
        self._save()

    def find_by_type(self, source_ids: list[str], source_type: str) -> list[dict]:
        """Return cached entries matching the given type from a list of source IDs."""
        return [
            self._data[sid]
            for sid in source_ids
            if sid in self._data and self._data[sid].get("type") == source_type
        ]

    def group_by_type(self, source_ids: list[str]) -> dict[str, list[str]]:
        """Group source names by their type. Returns {type: [name, ...]}."""
        groups: dict[str, list[str]] = {}
        for sid in source_ids:
            entry = self._data.get(sid)
            if entry:
                groups.setdefault(entry["type"], []).append(entry["name"])
        return groups
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_source_cache.py -v`
Expected: all PASS

**Step 5: Commit**

```
feat: add source cache for 1001TL source page metadata
```

---

### Task 2: Parse `<h1>` and fetch source metadata in `api.py`

**Files:**
- Modify: `festival_organizer/tracklists/api.py` — `TracklistExport` dataclass, `export_tracklist()`, new helpers
- Test: `tests/test_tracklists_api.py` (add tests)

**Step 1: Write failing tests for h1 parsing**

Add to existing test file or create new:

```python
# tests/test_h1_parsing.py
from festival_organizer.tracklists.api import _parse_h1_structure


def test_simple_stage():
    """Afrojack @ kineticFIELD, EDC Las Vegas"""
    h1 = '<a href="/dj/afrojack/index.html" class="notranslate ">AFROJACK</a> @ kineticFIELD, <a href="/source/unkguv/edc-las-vegas/index.html">EDC Las Vegas</a>, United States 2025-05-17'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "kineticFIELD"
    assert ("unkguv", "edc-las-vegas", "EDC Las Vegas") in result["sources"]


def test_set_name_and_stage():
    """Tiesto @ In Search Of Sunrise, kineticFIELD, EDC Las Vegas"""
    h1 = '<a href="/dj/tiesto/index.html" class="notranslate ">Ti&euml;sto</a> @ In Search Of Sunrise, kineticFIELD, <a href="/source/unkguv/edc-las-vegas/index.html">EDC Las Vegas</a>, United States 2025-05-18'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "In Search Of Sunrise, kineticFIELD"
    assert len(result["sources"]) == 1


def test_no_stage():
    """Hardwell @ AMF, Johan Cruijff ArenA, ADE"""
    h1 = '<a href="/dj/hardwell/index.html" class="notranslate ">Hardwell</a> @ <a href="/source/5tb5n3/amsterdam-music-festival/index.html">Amsterdam Music Festival</a>, <a href="/source/hdfr2c/johan-cruijff-arena-amsterdam/index.html">Johan Cruijff ArenA</a>, <a href="/source/f4lzj3/amsterdam-dance-event/index.html">Amsterdam Dance Event</a>, Netherlands 2025-10-25'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == ""
    assert len(result["sources"]) == 3


def test_complex_set_and_venue():
    """Armin @ 25 Years Celebration Set, Area One, ASOT Festival, Ahoy Rotterdam"""
    h1 = '<a href="/dj/arminvanbuuren/index.html" class="notranslate ">Armin van Buuren</a> @ 25 Years Celebration Set, Area One, <a href="/source/rch80m/a-state-of-trance-festival/index.html">A State Of Trance Festival</a>, <a href="/source/tslp1m/ahoy-rotterdam/index.html">Ahoy Rotterdam</a>, Netherlands 2026-02-27'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "25 Years Celebration Set, Area One"
    assert len(result["sources"]) == 2
    ids = [s[0] for s in result["sources"]]
    assert "rch80m" in ids
    assert "tslp1m" in ids


def test_no_at_sign():
    """Mysteryland - Aftermovie (no @)"""
    h1 = 'Mysteryland - Aftermovie 2025-09-15'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == ""
    assert result["sources"] == []
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_h1_parsing.py -v`
Expected: ImportError — `_parse_h1_structure` doesn't exist

**Step 3: Implement `_parse_h1_structure` and source page fetching**

In `api.py`, add the helper function:

```python
def _parse_h1_structure(h1_html: str) -> dict:
    """Parse the structured <h1> content from a tracklist page.

    Returns dict with:
        stage_text: str — plain text between @ and first /source/ link
        sources: list of (id, slug, display_name) tuples from /source/ links
    """
    result = {"stage_text": "", "sources": []}

    if "@" not in h1_html:
        return result

    # Split on @ — take everything after the first @
    after_at = h1_html.split("@", 1)[1]

    # Find all /source/ links: href="/source/{id}/{slug}/...">{name}</a>
    source_pattern = re.compile(
        r'<a[^>]*href="/source/([^/]+)/([^/]+)/[^"]*"[^>]*>([^<]+)</a>'
    )
    sources = [(m.group(1), m.group(2), _html_decode(m.group(3).strip()))
               for m in source_pattern.finditer(after_at)]
    result["sources"] = sources

    # Stage text = plain text between @ and first /source/ link
    first_source = source_pattern.search(after_at)
    if first_source:
        plain = after_at[:first_source.start()]
    else:
        plain = after_at

    # Strip HTML tags, trailing commas, whitespace
    plain = re.sub(r"<[^>]+>", "", plain).strip().rstrip(",").strip()
    result["stage_text"] = _html_decode(plain)

    return result
```

Add source page fetching method to `TracklistSession`:

```python
def fetch_source_info(self, source_id: str, slug: str) -> dict:
    """Fetch metadata from a /source/ page. Returns {name, slug, type, country}."""
    url = f"{BASE_URL}/source/{source_id}/{slug}/index.html"
    resp = self._request("GET", url, max_retries=2)

    # Type from <div class="cRow"><div class="mtb5">...</div>
    type_match = re.search(
        r'<div class="cRow">\s*<div class="mtb5">([^<]+)</div>', resp.text
    )
    source_type = type_match.group(1).strip() if type_match else ""

    # Country from flag alt attribute
    flag_match = re.search(
        r'<img[^>]*flags/[^.]+\.png[^>]*alt="([^"]+)"', resp.text
    )
    country = flag_match.group(1).strip() if flag_match else ""

    # Name from <div class="h"> (first text node)
    name_match = re.search(r'<div class="h">\s*([^<]+)', resp.text)
    name = name_match.group(1).strip() if name_match else slug.replace("-", " ").title()

    return {"name": name, "slug": slug, "type": source_type, "country": country}
```

Add `stage_text` and `sources_by_type` fields to `TracklistExport`:

```python
@dataclass
class TracklistExport:
    """Exported tracklist data."""
    lines: list[str]
    url: str
    title: str
    genres: list[str] = field(default_factory=list)
    dj_artwork_url: str = ""
    stage_text: str = ""
    sources_by_type: dict[str, list[str]] = field(default_factory=dict)
```

Update `export_tracklist()` to parse h1 and resolve sources:

After extracting genres/dj_artwork, add:

```python
# Parse structured h1 for stage and source metadata
h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", page_resp.text, re.DOTALL)
stage_text = ""
sources_by_type: dict[str, list[str]] = {}
if h1_match:
    h1_info = _parse_h1_structure(h1_match.group(1))
    stage_text = h1_info["stage_text"]

    # Resolve sources via cache
    if h1_info["sources"] and self._source_cache:
        for sid, slug, display_name in h1_info["sources"]:
            if not self._source_cache.get(sid):
                time.sleep(self._delay)
                info = self.fetch_source_info(sid, slug)
                self._source_cache.put(sid, info)
                logger.info("Cached source: %s = %s (%s)", display_name, info["type"], info["country"])

        sources_by_type = self._source_cache.group_by_type(
            [s[0] for s in h1_info["sources"]]
        )
```

Update `TracklistSession.__init__` to accept source cache and delay:

```python
def __init__(self, cookie_cache_path: Path | None = None,
             source_cache: SourceCache | None = None,
             delay: float = 5):
    self._cookie_path = cookie_cache_path or DEFAULT_COOKIE_PATH
    self._source_cache = source_cache
    self._delay = delay
    self._session = requests.Session()
    # ... rest unchanged
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_h1_parsing.py -v`
Expected: all PASS

**Step 5: Commit**

```
feat: parse structured h1 from 1001TL pages for stage and venue
```

---

### Task 3: Wire source cache and delay into CLI handler

**Files:**
- Modify: `festival_organizer/tracklists/cli_handler.py` — pass source cache and delay to session

**Step 1: Update session creation in `cli_handler.py`**

Where `TracklistSession` is instantiated, pass the source cache and delay:

```python
from festival_organizer.tracklists.source_cache import SourceCache

# Near the top of the handler function, after delay is resolved:
source_cache = SourceCache()
session = TracklistSession(source_cache=source_cache, delay=delay)
```

**Step 2: Add new tags to the embed pipeline**

In `cli_handler.py`, where `CRATEDIGGER_1001TL_*` tags are built, add:

```python
if export.stage_text:
    tags["CRATEDIGGER_1001TL_STAGE"] = export.stage_text
# Per-type source tags
SOURCE_TYPE_TO_TAG = {
    "Open Air / Festival": "CRATEDIGGER_1001TL_FESTIVAL",
    "Event Location": "CRATEDIGGER_1001TL_VENUE",
    "Conference": "CRATEDIGGER_1001TL_CONFERENCE",
    "Radio Channel": "CRATEDIGGER_1001TL_RADIO",
}
for source_type, names in export.sources_by_type.items():
    tag_name = SOURCE_TYPE_TO_TAG.get(source_type)
    if tag_name and names:
        tags[tag_name] = "|".join(names)
```

This applies in both the "chapters match, update tags" path and the "embed new chapters" path.

**Step 3: Update `chapters.py` tag map and embed function**

In `extract_stored_tracklist_info` tag_map, add:

```python
"CRATEDIGGER_1001TL_STAGE": "stage",
"CRATEDIGGER_1001TL_VENUE": "venue",
```

In `embed_chapters()` function signature and tag writing, add `stage_text` and `venue` parameters:

```python
if stage_text:
    tags["CRATEDIGGER_1001TL_STAGE"] = stage_text
if venue:
    tags["CRATEDIGGER_1001TL_VENUE"] = venue
```

**Step 4: Run existing tests to verify nothing breaks**

Run: `python -m pytest tests/test_tracklists_chapters.py tests/test_tracklists_api.py -v`
Expected: all PASS

**Step 5: Commit**

```
feat: embed CRATEDIGGER_1001TL_STAGE and _VENUE tags in MKV files
```

---

### Task 4: Read new tags in metadata and analyzer

**Files:**
- Modify: `festival_organizer/metadata.py` — read new tags
- Modify: `festival_organizer/models.py` — add `venue` field
- Modify: `festival_organizer/analyzer.py` — populate venue, use new stage tag
- Test: `tests/test_analyzer.py` (add tests)

**Step 1: Add `venue` to `MediaFile`**

In `models.py`, add after `stage`:

```python
venue: str = ""
```

**Step 2: Read new tags in `metadata.py`**

In `extract_metadata` (mediainfo path), add alongside existing 1001TL tag reads:

```python
"tracklists_stage": (
    general.get("CRATEDIGGER_1001TL_STAGE", "")
    or extra.get("CRATEDIGGER_1001TL_STAGE", "")
),
"tracklists_venue": (
    general.get("CRATEDIGGER_1001TL_VENUE", "")
    or extra.get("CRATEDIGGER_1001TL_VENUE", "")
),
```

Do the same in the ffprobe fallback path.

**Step 3: Update analyzer to use new tags**

In `analyzer.py`, Layer 4 (1001TL overwrite section), the `stage` key is already in the overwrite list. Add `venue` population from metadata:

```python
# After building the MediaFile, set venue from metadata
venue=meta.get("tracklists_venue", ""),
```

When `CRATEDIGGER_1001TL_STAGE` is present in metadata, it should take priority over the stage parsed from the flat title. This already happens because metadata tags are read in `extract_metadata()` and the 1001TL title parser fills `stage` — but the new `tracklists_stage` tag is more accurate. Add to Layer 4:

```python
if meta.get("tracklists_stage"):
    info["stage"] = meta["tracklists_stage"]
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_analyzer.py -v`
Expected: all PASS

**Step 5: Commit**

```
feat: read CRATEDIGGER_1001TL_STAGE and _VENUE from metadata into MediaFile
```

---

### Task 5: NFO title and streamdetails changes

**Files:**
- Modify: `festival_organizer/nfo.py`
- Modify: `tests/test_nfo.py`

**Step 1: Write failing test for new title behavior**

```python
def test_nfo_title_is_stage_for_sets(tmp_path):
    """title = stage name for festival sets when available."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Afrojack",
                   stage="kineticFIELD", festival="EDC Las Vegas", year="2025",
                   content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "kineticFIELD"


def test_nfo_title_falls_back_to_artist(tmp_path):
    """title = artist when no stage available."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Martin Garrix",
                   festival="Red Rocks", year="2025",
                   content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix"


def test_nfo_no_streamdetails(tmp_path):
    """fileinfo/streamdetails should not be present (Kodi overwrites on playback)."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   content_type="festival_set", festival="TML", year="2024",
                   video_format="HEVC", audio_format="AAC",
                   width=1920, height=1080, duration_seconds=3600)
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("fileinfo") is None
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_nfo.py::test_nfo_title_is_stage_for_sets tests/test_nfo.py::test_nfo_no_streamdetails -v`
Expected: FAIL

**Step 3: Update `nfo.py`**

Change title logic (line 24-25):
```python
if mf.content_type == "festival_set":
    title = mf.stage or mf.artist or "Unknown Artist"
```

Remove the entire streamdetails block (lines 101-118).

**Step 4: Update existing test that asserted artist as title**

Update `test_nfo_title_is_artist_for_sets` — rename to `test_nfo_title_is_stage_for_sets` or update its assertion since the behavior changed. The test at line 35-43 sets no stage, so it should still fall back to artist. Verify this still passes.

Also remove or update `test_nfo_fileinfo_durationinseconds` since streamdetails are gone.

**Step 5: Run all NFO tests**

Run: `python -m pytest tests/test_nfo.py -v`
Expected: all PASS

**Step 6: Commit**

```
feat: NFO title uses stage name, remove streamdetails (Kodi overwrites)
```

---

### Task 6: Poster — split detail/venue on commas, add venue line

**Files:**
- Modify: `festival_organizer/poster.py` — `generate_set_poster()`
- Modify: `festival_organizer/operations.py` — pass `venue` to poster
- Modify: `tests/test_poster.py` (add tests)

**Step 1: Write failing test**

```python
def test_set_poster_with_venue(tmp_path):
    """Poster generates without error when venue is provided."""
    source = _create_test_image(tmp_path)
    output = tmp_path / "poster.jpg"
    generate_set_poster(
        source_image_path=source,
        output_path=output,
        artist="Armin van Buuren",
        festival="A State Of Trance Festival",
        date="2026-02-27",
        detail="25 Years Celebration Set, Area One",
        venue="Ahoy Rotterdam",
    )
    assert output.exists()
    img = Image.open(output)
    assert img.size == (1000, 1500)
```

**Step 2: Run to verify fail**

Run: `python -m pytest tests/test_poster.py::test_set_poster_with_venue -v`
Expected: TypeError — unexpected keyword argument `venue`

**Step 3: Update `generate_set_poster()`**

Add `venue` parameter:

```python
def generate_set_poster(
    source_image_path: Path,
    output_path: Path,
    artist: str,
    festival: str,
    date: str = "",
    year: str = "",
    detail: str = "",
    venue: str = "",
) -> Path:
```

Replace the single detail line rendering (lines 419-421) with comma-split multi-line rendering:

```python
    # Detail lines — split on comma, auto-fit each line
    PAD_DETAIL_LINES = 8
    if detail:
        for part in [p.strip() for p in detail.split(",") if p.strip()]:
            font_d, _ = auto_fit(part, "semilight", max_w, start=44, minimum=28)
            dh = font_visual_height(font_d)
            _draw_centered_no_shadow(draw, ty, part, font_d, "white")
            ty += dh + PAD_DETAIL_LINES

    # Venue lines — split on comma, auto-fit each line
    if venue:
        for part in [p.strip() for p in venue.split(",") if p.strip()]:
            font_v, _ = auto_fit(part, "semilight", max_w, start=38, minimum=24)
            vh = font_visual_height(font_v)
            _draw_centered_no_shadow(draw, ty, part, font_v, (200, 200, 200))
            ty += vh + PAD_DETAIL_LINES
```

Note: venue rendered in light gray `(200, 200, 200)` to visually distinguish from stage/detail text.

**Step 4: Update `operations.py` to pass venue**

In `SetPosterOperation.execute()` (line 195-203), change:

```python
generate_set_poster(
    source_image_path=thumb,
    output_path=poster,
    artist=mf.artist or "Unknown",
    festival=festival_display or mf.title or "",
    date=mf.date,
    year=mf.year,
    detail=mf.stage or "",
    venue=mf.venue or "",
)
```

Remove `mf.location` from the detail fallback — venue now handles location context.

**Step 5: Run all poster tests**

Run: `python -m pytest tests/test_poster.py -v`
Expected: all PASS

**Step 6: Commit**

```
feat: poster splits stage/venue on commas into separate lines
```

---

### Task 7: Integration test and cleanup

**Step 1: Run full test suite**

Run: `python -m pytest -v`
Expected: all PASS

**Step 2: Manual verification with test data**

Use the mediainfo metadata JSON at `/home/user/_temp/cratedigger/data/mediainfo_metadata.json` to verify the parser handles all 52 entries correctly. Write a quick verification script if needed.

**Step 3: Commit design doc**

```
docs: structured 1001TL metadata design and implementation plan
```
