# CrateDigger Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor CrateDigger from a Windows-only all-or-nothing tool into a composable, cross-platform library manager with workflow-oriented commands, smart gap detection, live progress, and richer Kodi metadata.

**Architecture:** Pipeline of composable operations (organize, nfo, art, poster, tags, chapters) driven by a Runner that handles gap detection and live progress. Three-layer config system (built-in < user < library). Library root detection via `.cratedigger/` marker directory.

**Tech Stack:** Python 3.10+, argparse, Pillow, OpenCV, requests, pytest. External tools: MediaInfo, ffprobe, MKVToolNix (mkvextract, mkvpropedit).

**Spec:** `docs/superpowers/specs/2026-03-27-cratedigger-refinement-design.md`

---

## File Structure

### New files
- `festival_organizer/operations.py` — Operation base class and all operation implementations (gap detection + execution)
- `festival_organizer/runner.py` — Runner that executes operations per file with live progress
- `festival_organizer/progress.py` — Live progress output formatting
- `festival_organizer/library.py` — Library root detection and marker management
- `festival_organizer/fonts/` — Directory for bundled fonts
- `festival_organizer/fonts/__init__.py` — Font path resolution (bundled or config override)
- `tests/test_operations.py` — Tests for all operations and gap detection
- `tests/test_runner.py` — Tests for runner and progress
- `tests/test_library.py` — Tests for library root detection

### Modified files
- `festival_organizer/config.py` — Three-layer config loading, new layout definitions
- `festival_organizer/metadata.py` — Remove hardcoded Windows paths, cross-platform tool discovery
- `festival_organizer/poster.py` — Use font resolver instead of hardcoded Windows paths
- `festival_organizer/nfo.py` — Full Kodi spec: premiered, album grouping, tags, studio, richer fields
- `festival_organizer/cli.py` — New command structure (scan, organize, enrich, chapters)
- `festival_organizer/templates.py` — Support new flat layouts
- `festival_organizer/models.py` — Remove post-processing booleans from FileAction
- `tests/test_config.py` — Tests for layered config, new layouts
- `tests/test_nfo.py` — Tests for new NFO fields
- `tests/test_templates.py` — Tests for flat layouts
- `tests/test_poster.py` — Tests for font resolver
- `tests/test_metadata.py` — Tests for cross-platform tool discovery

---

## Task 1: Layered Configuration System

Refactor config loading from single-file to three-layer merge (built-in < user < library). Add new layouts. This is the foundation everything else depends on.

**Files:**
- Modify: `festival_organizer/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for three-layer config merge**

```python
# tests/test_config.py — add these tests

def test_load_config_builtin_defaults():
    """Built-in defaults load when no files exist."""
    config = load_config()
    assert config.default_layout == "artist_flat"
    assert "artist_flat" in config.layouts
    assert "festival_flat" in config.layouts
    assert "artist_nested" in config.layouts
    assert "festival_nested" in config.layouts


def test_load_config_user_layer(tmp_path):
    """User config at ~/.cratedigger/config.json merges over built-in."""
    user_dir = tmp_path / ".cratedigger"
    user_dir.mkdir()
    user_config = user_dir / "config.json"
    user_config.write_text(json.dumps({
        "festival_aliases": {"My Fest": "My Festival"},
        "tracklists": {"email": "me@example.com", "password": "secret"},
    }))
    config = load_config(user_config_dir=user_dir)
    # User alias merged in
    assert config.resolve_festival_alias("My Fest") == "My Festival"
    # Built-in aliases still present
    assert config.resolve_festival_alias("EDC") == "EDC Las Vegas"
    # Credentials accessible
    assert config.tracklists_credentials == ("me@example.com", "secret")


def test_load_config_library_layer(tmp_path):
    """Library config merges over user config."""
    lib_dir = tmp_path / ".cratedigger"
    lib_dir.mkdir()
    lib_config = lib_dir / "config.json"
    lib_config.write_text(json.dumps({"default_layout": "festival_flat"}))
    config = load_config(library_config_dir=lib_dir)
    assert config.default_layout == "festival_flat"


def test_load_config_merge_order(tmp_path):
    """Library overrides user overrides built-in."""
    user_dir = tmp_path / "user" / ".cratedigger"
    user_dir.mkdir(parents=True)
    (user_dir / "config.json").write_text(json.dumps({
        "default_layout": "artist_nested",
    }))
    lib_dir = tmp_path / "lib" / ".cratedigger"
    lib_dir.mkdir(parents=True)
    (lib_dir / "config.json").write_text(json.dumps({
        "default_layout": "festival_nested",
    }))
    config = load_config(user_config_dir=user_dir, library_config_dir=lib_dir)
    assert config.default_layout == "festival_nested"


def test_new_flat_layouts():
    """Built-in defaults include flat layout templates."""
    config = load_config()
    # artist_flat
    tpl = config.get_layout_template("festival_set", "artist_flat")
    assert tpl == "{artist}"
    # festival_flat
    tpl = config.get_layout_template("festival_set", "festival_flat")
    assert tpl == "{festival}"
    # Concerts in flat layouts fall back to {artist}
    tpl = config.get_layout_template("concert_film", "artist_flat")
    assert tpl == "{artist}"
    tpl = config.get_layout_template("concert_film", "festival_flat")
    assert tpl == "{artist}"


def test_renamed_nested_layouts():
    """Old layout names renamed: artist_first -> artist_nested, etc."""
    config = load_config()
    tpl = config.get_layout_template("festival_set", "artist_nested")
    assert tpl == "{artist}/{festival}/{year}"
    tpl = config.get_layout_template("festival_set", "festival_nested")
    assert tpl == "{festival}/{year}/{artist}"


def test_tracklists_credentials_from_config():
    """Credentials loaded from tracklists section."""
    config = Config({
        "tracklists": {"email": "a@b.com", "password": "pw123"}
    })
    assert config.tracklists_credentials == ("a@b.com", "pw123")


def test_tracklists_credentials_env_override(monkeypatch):
    """Environment variables override config credentials."""
    monkeypatch.setenv("TRACKLISTS_EMAIL", "env@b.com")
    monkeypatch.setenv("TRACKLISTS_PASSWORD", "envpw")
    config = Config({
        "tracklists": {"email": "config@b.com", "password": "configpw"}
    })
    assert config.tracklists_credentials == ("env@b.com", "envpw")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v -k "test_load_config_builtin or test_load_config_user or test_load_config_library or test_load_config_merge or test_new_flat or test_renamed_nested or test_tracklists_credentials"`
Expected: Multiple failures — new function signatures and layout names don't exist yet.

- [ ] **Step 3: Update config.py with new layout definitions and layered loading**

Update `DEFAULT_CONFIG` in `festival_organizer/config.py`:
- Change `default_layout` to `"artist_flat"`
- Rename `artist_first` to `artist_nested`, `festival_first` to `festival_nested`
- Add `artist_flat` layout: `{"festival_set": "{artist}", "concert_film": "{artist}"}`
- Add `festival_flat` layout: `{"festival_set": "{festival}", "concert_film": "{artist}"}`
- Add `tracklists` section with `email`, `password`, `delay_seconds`, `chapter_language` (move from `tracklists_settings`)

Update `load_config()` signature:

```python
def load_config(
    config_path: Path | None = None,  # legacy single-file support
    user_config_dir: Path | None = None,
    library_config_dir: Path | None = None,
) -> Config:
    """Load config with three-layer merge: built-in < user < library.

    If config_path is provided (legacy), loads from that file as user layer.
    Otherwise:
      - user_config_dir defaults to ~/.cratedigger/
      - library_config_dir is typically .cratedigger/ at library root
    """
    data = dict(DEFAULT_CONFIG)  # deep copy built-in

    # Legacy path support
    if config_path and config_path.exists():
        with open(config_path) as f:
            _deep_merge(data, json.load(f))
        return Config(data)

    # Layer 2: User config
    if user_config_dir is None:
        user_config_dir = Path.home() / ".cratedigger"
    user_file = user_config_dir / "config.json"
    if user_file.exists():
        with open(user_file) as f:
            _deep_merge(data, json.load(f))

    # Layer 3: Library config
    if library_config_dir is not None:
        lib_file = library_config_dir / "config.json"
        if lib_file.exists():
            with open(lib_file) as f:
                _deep_merge(data, json.load(f))

    return Config(data)
```

Add to Config class:

```python
@property
def tracklists_credentials(self) -> tuple[str, str]:
    """Return (email, password) — env vars override config."""
    import os
    tl = self._data.get("tracklists", {})
    email = os.environ.get("TRACKLISTS_EMAIL") or tl.get("email", "")
    password = os.environ.get("TRACKLISTS_PASSWORD") or tl.get("password", "")
    return (email, password)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: All new and existing tests pass. Existing tests may need minor updates for renamed layouts (artist_first → artist_nested).

- [ ] **Step 5: Fix any existing tests broken by layout rename**

Update any test that references `artist_first` or `festival_first` to use `artist_nested` / `festival_nested`. Search for these strings across all test files.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add festival_organizer/config.py tests/test_config.py
git commit -m "feat: layered config system with flat layouts and renamed nested layouts"
```

---

## Task 2: Library Root Detection

Add `.cratedigger/` marker directory support for library root detection and library-level config.

**Files:**
- Create: `festival_organizer/library.py`
- Create: `tests/test_library.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_library.py
import json
from pathlib import Path
from festival_organizer.library import find_library_root, init_library


def test_find_library_root_at_path(tmp_path):
    """Find .cratedigger/ marker at the given path."""
    marker = tmp_path / ".cratedigger"
    marker.mkdir()
    assert find_library_root(tmp_path) == tmp_path


def test_find_library_root_walks_up(tmp_path):
    """Walk up from subfolder to find .cratedigger/ marker."""
    marker = tmp_path / ".cratedigger"
    marker.mkdir()
    sub = tmp_path / "Artist" / "Festival"
    sub.mkdir(parents=True)
    assert find_library_root(sub) == tmp_path


def test_find_library_root_returns_none(tmp_path):
    """Return None when no marker found."""
    sub = tmp_path / "some" / "deep" / "path"
    sub.mkdir(parents=True)
    assert find_library_root(sub) is None


def test_find_library_root_stops_at_filesystem_root(tmp_path):
    """Don't walk above filesystem boundaries."""
    result = find_library_root(tmp_path)
    assert result is None


def test_init_library_creates_marker(tmp_path):
    """init_library creates .cratedigger/ directory."""
    init_library(tmp_path)
    assert (tmp_path / ".cratedigger").is_dir()


def test_init_library_creates_config(tmp_path):
    """init_library creates config.json with layout."""
    init_library(tmp_path, layout="festival_flat")
    cfg = json.loads((tmp_path / ".cratedigger" / "config.json").read_text())
    assert cfg["default_layout"] == "festival_flat"


def test_init_library_idempotent(tmp_path):
    """Running init_library twice doesn't overwrite existing config."""
    init_library(tmp_path, layout="festival_flat")
    # Manually add a custom setting
    cfg_path = tmp_path / ".cratedigger" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["custom_key"] = "custom_value"
    cfg_path.write_text(json.dumps(cfg))
    # Re-init should not clobber
    init_library(tmp_path, layout="artist_flat")
    cfg = json.loads(cfg_path.read_text())
    assert cfg["custom_key"] == "custom_value"


def test_find_library_root_config_dir(tmp_path):
    """find_library_root returns path, config at .cratedigger/."""
    init_library(tmp_path, layout="artist_nested")
    root = find_library_root(tmp_path / "subfolder")
    # subfolder doesn't exist but we're searching up
    assert root is None  # subfolder doesn't exist on disk
    # But from a real subfolder:
    sub = tmp_path / "Artist"
    sub.mkdir()
    root = find_library_root(sub)
    assert root == tmp_path
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_library.py -v`
Expected: ImportError — `festival_organizer.library` doesn't exist.

- [ ] **Step 3: Implement library.py**

```python
# festival_organizer/library.py
"""Library root detection and marker management."""
import json
from pathlib import Path

MARKER_DIR = ".cratedigger"


def find_library_root(start_path: Path) -> Path | None:
    """Walk up from start_path looking for .cratedigger/ marker.

    Returns the directory containing the marker, or None if not found.
    Stops at filesystem root to avoid infinite loops.
    """
    current = start_path.resolve()
    while True:
        if (current / MARKER_DIR).is_dir():
            return current
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            return None
        current = parent


def init_library(root: Path, layout: str | None = None) -> Path:
    """Initialize a library at root by creating .cratedigger/ marker.

    If .cratedigger/config.json already exists, merges layout setting
    without overwriting existing user settings.

    Returns path to the .cratedigger/ directory.
    """
    marker = root / MARKER_DIR
    marker.mkdir(exist_ok=True)

    config_path = marker / "config.json"
    if config_path.exists():
        # Merge — don't overwrite
        existing = json.loads(config_path.read_text(encoding="utf-8"))
        if layout and "default_layout" not in existing:
            existing["default_layout"] = layout
            config_path.write_text(
                json.dumps(existing, indent=2) + "\n", encoding="utf-8"
            )
    else:
        # Create new
        config = {}
        if layout:
            config["default_layout"] = layout
        config_path.write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

    return marker
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_library.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add festival_organizer/library.py tests/test_library.py
git commit -m "feat: library root detection via .cratedigger/ marker"
```

---

## Task 3: Cross-Platform Tool Discovery

Remove hardcoded Windows paths from `metadata.py`. Use PATH-first discovery with config overrides and platform-specific install hints.

**Files:**
- Modify: `festival_organizer/metadata.py`
- Modify: `tests/test_metadata.py`

- [ ] **Step 1: Write failing tests for new tool discovery**

```python
# tests/test_metadata.py — add these tests

import platform
from unittest.mock import patch
from festival_organizer.metadata import find_tool, get_install_hint


def test_find_tool_on_path(tmp_path):
    """Find tool on system PATH."""
    tool = tmp_path / "mediainfo"
    tool.write_text("fake")
    tool.chmod(0o755)
    with patch("shutil.which", return_value=str(tool)):
        result = find_tool("mediainfo")
    assert result == str(tool)


def test_find_tool_config_override(tmp_path):
    """Config-provided path takes priority over PATH."""
    custom = tmp_path / "custom_mediainfo"
    custom.write_text("fake")
    with patch("shutil.which", return_value="/usr/bin/mediainfo"):
        result = find_tool("mediainfo", configured_path=str(custom))
    assert result == str(custom)


def test_find_tool_config_override_missing(tmp_path):
    """Config path that doesn't exist falls back to PATH."""
    with patch("shutil.which", return_value="/usr/bin/mediainfo"):
        result = find_tool("mediainfo", configured_path="/nonexistent/mediainfo")
    assert result == "/usr/bin/mediainfo"


def test_find_tool_not_found():
    """Return None when tool not found anywhere."""
    with patch("shutil.which", return_value=None):
        result = find_tool("mediainfo")
    assert result is None


def test_get_install_hint_macos():
    """macOS install hint uses brew."""
    with patch("platform.system", return_value="Darwin"):
        hint = get_install_hint("mediainfo")
    assert "brew install" in hint


def test_get_install_hint_linux():
    """Linux install hint uses apt."""
    with patch("platform.system", return_value="Linux"):
        hint = get_install_hint("mediainfo")
    assert "apt install" in hint


def test_get_install_hint_windows():
    """Windows install hint uses winget."""
    with patch("platform.system", return_value="Windows"):
        hint = get_install_hint("mediainfo")
    assert "winget install" in hint
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_metadata.py -v -k "test_find_tool or test_get_install_hint"`
Expected: Failures — `get_install_hint` doesn't exist, `find_tool` has different signature.

- [ ] **Step 3: Update metadata.py**

Replace the current `find_tool` function and remove all hardcoded `WINDOWS_FALLBACK` paths:

```python
import platform
import shutil
from pathlib import Path


# Package → tool names for install hints
_INSTALL_PACKAGES = {
    "mediainfo": {"brew": "mediainfo", "apt": "mediainfo", "winget": "MediaArea.MediaInfo.CLI"},
    "ffprobe": {"brew": "ffmpeg", "apt": "ffmpeg", "winget": "Gyan.FFmpeg"},
    "mkvextract": {"brew": "mkvtoolnix", "apt": "mkvtoolnix", "winget": "MKVToolNix.MKVToolNix"},
    "mkvpropedit": {"brew": "mkvtoolnix", "apt": "mkvtoolnix", "winget": "MKVToolNix.MKVToolNix"},
    "mkvmerge": {"brew": "mkvtoolnix", "apt": "mkvtoolnix", "winget": "MKVToolNix.MKVToolNix"},
}


def find_tool(name: str, configured_path: str | None = None) -> str | None:
    """Find an external tool by name.

    Priority:
    1. configured_path (from user config) — if file exists
    2. System PATH via shutil.which

    Returns the resolved path string, or None if not found.
    """
    # Config override
    if configured_path and Path(configured_path).is_file():
        return configured_path

    # System PATH
    found = shutil.which(name)
    if found:
        return found

    return None


def get_install_hint(tool_name: str) -> str:
    """Return a platform-specific install command hint."""
    system = platform.system()
    pkg = _INSTALL_PACKAGES.get(tool_name, {})

    if system == "Darwin":
        return f"Install with: brew install {pkg.get('brew', tool_name)}"
    elif system == "Linux":
        return f"Install with: apt install {pkg.get('apt', tool_name)}"
    else:
        return f"Install with: winget install {pkg.get('winget', tool_name)}"
```

Remove the old `MEDIAINFO_FALLBACKS`, `FFPROBE_FALLBACKS`, and `MKVTOOLNIX_DIRS` lists. Update `configure_tools()` to use the new `find_tool` signature.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_metadata.py -v`
Expected: All pass.

- [ ] **Step 5: Run full test suite to check nothing broke**

Run: `python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add festival_organizer/metadata.py tests/test_metadata.py
git commit -m "feat: cross-platform tool discovery, remove hardcoded Windows paths"
```

---

## Task 4: Bundled Font Support

Replace hardcoded Windows font paths with a font resolver that uses bundled fonts with config override.

**Files:**
- Create: `festival_organizer/fonts/__init__.py`
- Modify: `festival_organizer/poster.py`
- Modify: `tests/test_poster.py`

- [ ] **Step 1: Write failing tests for font resolution**

```python
# tests/test_poster.py — add these tests

from festival_organizer.fonts import get_font_path


def test_get_font_path_returns_bundled():
    """Bundled font path exists and is a real file."""
    path = get_font_path("bold")
    assert Path(path).is_file()


def test_get_font_path_all_weights():
    """All four font weights resolve to existing files."""
    for weight in ("bold", "light", "semilight", "regular"):
        path = get_font_path(weight)
        assert Path(path).is_file(), f"Missing font for weight: {weight}"


def test_get_font_path_config_override(tmp_path):
    """Config override takes priority over bundled fonts."""
    fake_font = tmp_path / "custom.ttf"
    fake_font.write_bytes(b"fake")
    overrides = {"bold": str(fake_font)}
    path = get_font_path("bold", overrides=overrides)
    assert path == str(fake_font)


def test_get_font_path_config_override_missing_falls_back(tmp_path):
    """Missing config override file falls back to bundled."""
    overrides = {"bold": "/nonexistent/font.ttf"}
    path = get_font_path("bold", overrides=overrides)
    # Falls back to bundled — must be a real file
    assert Path(path).is_file()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_poster.py -v -k "test_get_font_path"`
Expected: ImportError — `festival_organizer.fonts` doesn't exist.

- [ ] **Step 3: Download and bundle Inter font**

Download Inter font (SIL Open Font License) and place in `festival_organizer/fonts/`:
- `Inter-Bold.ttf`
- `Inter-Light.ttf`
- `Inter-Regular.ttf`
- `Inter-SemiBold.ttf` (as semilight equivalent — Inter doesn't have SemiLight, SemiBold is the closest mappable weight)

Run:
```bash
mkdir -p festival_organizer/fonts
# Download Inter font files from GitHub releases
curl -L "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip" -o /tmp/inter.zip
unzip -j /tmp/inter.zip "Inter-4.1/Inter-Desktop/Inter-Bold.ttf" -d festival_organizer/fonts/
unzip -j /tmp/inter.zip "Inter-4.1/Inter-Desktop/Inter-Light.ttf" -d festival_organizer/fonts/
unzip -j /tmp/inter.zip "Inter-4.1/Inter-Desktop/Inter-Regular.ttf" -d festival_organizer/fonts/
unzip -j /tmp/inter.zip "Inter-4.1/Inter-Desktop/Inter-SemiBold.ttf" -d festival_organizer/fonts/
```

If the download URL doesn't work, download Inter manually from https://rsms.me/inter/ and place the 4 TTF files.

- [ ] **Step 4: Implement font resolver**

```python
# festival_organizer/fonts/__init__.py
"""Font resolution: bundled fonts with config override."""
from pathlib import Path

_FONT_DIR = Path(__file__).parent

_BUNDLED_FONTS = {
    "bold": _FONT_DIR / "Inter-Bold.ttf",
    "light": _FONT_DIR / "Inter-Light.ttf",
    "semilight": _FONT_DIR / "Inter-SemiBold.ttf",
    "regular": _FONT_DIR / "Inter-Regular.ttf",
}


def get_font_path(
    weight: str,
    overrides: dict[str, str] | None = None,
) -> str:
    """Resolve font path for a given weight.

    Priority:
    1. overrides dict (from user config font_paths)
    2. Bundled font

    Returns path string to the font file.
    """
    # Config override
    if overrides and weight in overrides:
        override_path = Path(overrides[weight])
        if override_path.is_file():
            return str(override_path)

    # Bundled font
    bundled = _BUNDLED_FONTS.get(weight)
    if bundled and bundled.is_file():
        return str(bundled)

    raise FileNotFoundError(f"No font found for weight '{weight}'")
```

- [ ] **Step 5: Update poster.py to use font resolver**

Replace the hardcoded `FONT_PATHS` dict and `get_font` function in `festival_organizer/poster.py`:

```python
# Replace this:
FONT_PATHS = {
    "bold": "C:/Windows/Fonts/segoeuib.ttf",
    "light": "C:/Windows/Fonts/segoeuil.ttf",
    "semilight": "C:/Windows/Fonts/segoeuisl.ttf",
    "regular": "C:/Windows/Fonts/segoeui.ttf",
}

def get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATHS[name], size)

# With this:
from festival_organizer.fonts import get_font_path

_font_overrides: dict[str, str] | None = None

def configure_fonts(overrides: dict[str, str] | None = None) -> None:
    """Set font path overrides from user config."""
    global _font_overrides
    _font_overrides = overrides

def get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = get_font_path(name, overrides=_font_overrides)
    return ImageFont.truetype(path, size)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_poster.py -v`
Expected: All pass.

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add festival_organizer/fonts/ festival_organizer/poster.py tests/test_poster.py
git commit -m "feat: bundled Inter fonts for cross-platform poster generation"
```

---

## Task 5: Update Templates for New Layouts

Add flat layout support to the template engine and update existing tests.

**Files:**
- Modify: `festival_organizer/templates.py`
- Modify: `tests/test_templates.py`

- [ ] **Step 1: Write failing tests for flat layouts**

```python
# tests/test_templates.py — add these tests

def test_render_folder_artist_flat_festival_set():
    """artist_flat layout: festival sets go into {artist}/."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="Tomorrowland",
        year="2024",
        content_type="festival_set",
    )
    config = load_config()
    result = render_folder(mf, config, layout_name="artist_flat")
    assert result == "Martin Garrix"


def test_render_folder_festival_flat_festival_set():
    """festival_flat layout: festival sets go into {festival}/."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="Tomorrowland",
        year="2024",
        content_type="festival_set",
    )
    config = load_config()
    result = render_folder(mf, config, layout_name="festival_flat")
    assert result == "Tomorrowland"


def test_render_folder_festival_flat_concert_film():
    """festival_flat layout: concerts fall back to {artist}/."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Adele",
        title="Live at Hyde Park",
        year="2022",
        content_type="concert_film",
    )
    config = load_config()
    result = render_folder(mf, config, layout_name="festival_flat")
    assert result == "Adele"


def test_render_folder_artist_nested():
    """Renamed artist_nested layout works same as old artist_first."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Armin van Buuren",
        festival="Tomorrowland",
        year="2023",
        content_type="festival_set",
    )
    config = load_config()
    result = render_folder(mf, config, layout_name="artist_nested")
    assert result == "Armin van Buuren/Tomorrowland/2023"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_templates.py -v -k "flat or nested"`
Expected: Failures — new layout names not in config yet (if Task 1 not applied), or templates work but layout names differ.

- [ ] **Step 3: Verify templates.py works with new layouts**

The template engine in `templates.py` is already generic — it reads layout templates from config and substitutes `{placeholders}`. Since Task 1 added the new layout definitions to `DEFAULT_CONFIG`, the templates should just work. Verify by running the tests.

If `render_folder` has hardcoded references to `artist_first` or `festival_first`, update them to use `config.default_layout` (which is now `artist_flat`).

- [ ] **Step 4: Update any existing tests that reference old layout names**

Search `tests/test_templates.py` for `artist_first` and `festival_first` — update to `artist_nested` and `festival_nested`.

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add festival_organizer/templates.py tests/test_templates.py
git commit -m "feat: flat layout support in template engine"
```

---

## Task 6: NFO Overhaul

Rewrite NFO generation to follow the full Kodi musicvideo spec: premiered instead of year, album grouping, tags, studio, richer plot.

**Files:**
- Modify: `festival_organizer/nfo.py`
- Modify: `tests/test_nfo.py`

- [ ] **Step 1: Write failing tests for new NFO fields**

```python
# tests/test_nfo.py — replace or add these tests

import xml.etree.ElementTree as ET
from pathlib import Path
from festival_organizer.models import MediaFile
from festival_organizer.config import load_config
from festival_organizer.nfo import generate_nfo


def _parse_nfo(nfo_path: Path) -> ET.Element:
    return ET.fromstring(nfo_path.read_text(encoding="utf-8"))


def test_nfo_uses_premiered_not_year(tmp_path):
    """premiered field present, year tag absent (deprecated in Kodi v20)."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test", year="2024",
                   date="2024-07-21", content_type="festival_set", festival="TML")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("premiered") is not None
    assert root.find("premiered").text == "2024-07-21"
    assert root.find("year") is None


def test_nfo_album_is_festival_plus_year(tmp_path):
    """album = festival + year for Kodi grouping."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   festival="Tomorrowland", year="2024",
                   content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("album").text == "Tomorrowland 2024"


def test_nfo_title_is_artist_for_sets(tmp_path):
    """title = artist name for festival sets, not the filename."""
    mf = MediaFile(source_path=Path("2024 - TML - Artist.mkv"), artist="Martin Garrix",
                   festival="Tomorrowland", year="2024",
                   content_type="festival_set")
    video = tmp_path / "2024 - TML - Martin Garrix.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix"


def test_nfo_title_is_title_for_concerts(tmp_path):
    """title = descriptive title for concert films."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Adele",
                   title="Live at Hyde Park", content_type="concert_film")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Live at Hyde Park"


def test_nfo_tags_for_smart_playlists(tmp_path):
    """tag elements for content type, festival, location."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   festival="Tomorrowland", location="Belgium",
                   year="2024", content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    tags = [t.text for t in root.findall("tag")]
    assert "festival_set" in tags
    assert "Tomorrowland" in tags
    assert "Belgium" in tags


def test_nfo_studio_is_stage(tmp_path):
    """studio = stage name for festival sets."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   stage="Mainstage", content_type="festival_set",
                   festival="TML", year="2024")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("studio").text == "Mainstage"


def test_nfo_dateadded_present(tmp_path):
    """dateadded element is present with ISO format."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   content_type="festival_set", festival="TML", year="2024")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    dateadded = root.find("dateadded")
    assert dateadded is not None
    assert len(dateadded.text) >= 10  # At least YYYY-MM-DD


def test_nfo_plot_no_tracklist_url(tmp_path):
    """plot should NOT contain 1001Tracklists URL."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   festival="TML", year="2024", content_type="festival_set",
                   stage="Mainstage", location="Belgium",
                   tracklists_url="https://www.1001tracklists.com/tracklist/abc123")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    plot = root.find("plot")
    if plot is not None and plot.text:
        assert "1001tracklists" not in plot.text.lower()


def test_nfo_multiple_thumb_aspects(tmp_path):
    """thumb elements for both thumb and poster images."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   content_type="festival_set", festival="TML", year="2024")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    thumbs = root.findall("thumb")
    aspects = [t.get("aspect") for t in thumbs]
    assert "thumb" in aspects
    assert "poster" in aspects


def test_nfo_fileinfo_durationinseconds(tmp_path):
    """fileinfo includes durationinseconds, aspect ratio, audio channels."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   content_type="festival_set", festival="TML", year="2024",
                   video_format="HEVC", width=1920, height=1080,
                   audio_format="AAC", duration_seconds=3661.5)
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    vid = root.find(".//streamdetails/video")
    assert vid.find("durationinseconds").text == "3661"
    assert vid.find("aspect") is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_nfo.py -v`
Expected: Multiple failures — year still present, album not formatted, tags missing, etc.

- [ ] **Step 3: Rewrite nfo.py**

```python
# festival_organizer/nfo.py
"""Kodi musicvideo NFO XML generation."""
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from xml.dom import minidom

from festival_organizer.config import Config
from festival_organizer.models import MediaFile


def generate_nfo(media_file: MediaFile, video_path: Path, config: Config) -> Path:
    """Generate a Kodi-compatible musicvideo NFO file alongside a video file.

    Follows the Kodi v20+ spec: https://kodi.wiki/view/NFO_files/Music_videos
    Returns the path to the generated .nfo file.
    """
    nfo_path = video_path.with_suffix(".nfo")
    mf = media_file
    nfo_settings = config.nfo_settings

    root = ET.Element("musicvideo")

    # Title — clean descriptor, not the full filename
    if mf.content_type == "festival_set":
        title = mf.artist or "Unknown Artist"
    else:
        title = mf.title or mf.artist or "Unknown"
    _add(root, "title", title)

    # Artist (required)
    _add(root, "artist", mf.artist or "Unknown Artist")

    # Album — grouping key: festival + year
    if mf.content_type == "festival_set":
        album_parts = []
        festival_display = mf.festival
        if mf.location:
            festival_display = config.get_festival_display(mf.festival, mf.location)
        if festival_display:
            album_parts.append(festival_display)
        if mf.year:
            album_parts.append(mf.year)
        album = " ".join(album_parts) if album_parts else ""
    else:
        album = mf.title or mf.festival or ""
    if album:
        _add(root, "album", album)

    # Premiered (replaces deprecated year tag)
    if mf.date:
        _add(root, "premiered", mf.date)
    elif mf.year:
        _add(root, "premiered", f"{mf.year}-01-01")

    # Genre
    if mf.content_type == "festival_set":
        _add(root, "genre", nfo_settings.get("genre_festival", "Electronic"))
    else:
        _add(root, "genre", nfo_settings.get("genre_concert", "Live"))

    # Tags — for Kodi smart playlists
    if mf.content_type:
        _add(root, "tag", mf.content_type)
    if mf.festival:
        _add(root, "tag", mf.festival)
    if mf.location:
        _add(root, "tag", mf.location)

    # Studio — stage name for sets, venue for concerts
    if mf.stage:
        _add(root, "studio", mf.stage)

    # Plot — rich description without 1001TL URL
    plot_parts = []
    if mf.stage:
        plot_parts.append(f"Stage: {mf.stage}")
    if mf.location:
        plot_parts.append(f"Location: {mf.location}")
    if mf.set_title:
        plot_parts.append(f"Edition: {mf.set_title}")
    if plot_parts:
        _add(root, "plot", "\n".join(plot_parts))

    # Runtime (minutes)
    if mf.duration_seconds:
        runtime_min = int(mf.duration_seconds) // 60
        _add(root, "runtime", str(runtime_min))

    # Thumbnails — both thumb and poster references
    thumb = ET.SubElement(root, "thumb", aspect="thumb")
    thumb.text = f"{video_path.stem}-thumb.jpg"
    poster = ET.SubElement(root, "thumb", aspect="poster")
    poster.text = f"{video_path.stem}-poster.jpg"

    # Date added
    _add(root, "dateadded", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Stream details
    if mf.video_format or mf.audio_format:
        fileinfo = ET.SubElement(root, "fileinfo")
        streamdetails = ET.SubElement(fileinfo, "streamdetails")

        if mf.video_format:
            video = ET.SubElement(streamdetails, "video")
            _add(video, "codec", mf.video_format)
            if mf.width and mf.height:
                _add(video, "aspect", f"{mf.width / mf.height:.2f}")
                _add(video, "width", str(mf.width))
                _add(video, "height", str(mf.height))
            if mf.duration_seconds:
                _add(video, "durationinseconds", str(int(mf.duration_seconds)))

        if mf.audio_format:
            audio = ET.SubElement(streamdetails, "audio")
            _add(audio, "codec", mf.audio_format)

    # Pretty-print without XML declaration
    xml_str = minidom.parseString(
        ET.tostring(root, encoding="unicode")
    ).toprettyxml(indent="  ")
    lines = xml_str.split("\n")
    if lines[0].startswith("<?xml"):
        xml_str = "\n".join(lines[1:])

    nfo_path.write_text(xml_str.strip() + "\n", encoding="utf-8")
    return nfo_path


def _add(parent: ET.Element, tag: str, text: str) -> ET.Element:
    """Add a child element with text content."""
    elem = ET.SubElement(parent, tag)
    elem.text = text
    return elem
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_nfo.py -v`
Expected: All pass.

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass (other tests using old NFO may need minor updates if they assert on `year` or old `title` format).

- [ ] **Step 6: Commit**

```bash
git add festival_organizer/nfo.py tests/test_nfo.py
git commit -m "feat: full Kodi v20 NFO spec — premiered, album grouping, tags, studio"
```

---

## Task 7: Operations Architecture

Create the composable operations system with gap detection. Each operation knows how to check if its work is needed and how to execute.

**Files:**
- Create: `festival_organizer/operations.py`
- Create: `tests/test_operations.py`

- [ ] **Step 1: Write failing tests for gap detection**

```python
# tests/test_operations.py
from pathlib import Path
from unittest.mock import patch, MagicMock
from festival_organizer.models import MediaFile
from festival_organizer.operations import (
    NfoOperation, ArtOperation, PosterOperation, TagsOperation,
    OrganizeOperation,
)
from festival_organizer.config import load_config


def _make_mf(**kwargs):
    defaults = dict(source_path=Path("test.mkv"), artist="Test",
                    festival="TML", year="2024", content_type="festival_set")
    defaults.update(kwargs)
    return MediaFile(**defaults)


def test_nfo_op_needed_when_missing(tmp_path):
    """NFO operation needed when .nfo file doesn't exist."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = NfoOperation(load_config())
    assert op.is_needed(video, _make_mf()) is True


def test_nfo_op_not_needed_when_exists(tmp_path):
    """NFO operation not needed when .nfo file exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test.nfo").write_text("<musicvideo/>")
    op = NfoOperation(load_config())
    assert op.is_needed(video, _make_mf()) is False


def test_nfo_op_needed_when_forced(tmp_path):
    """NFO operation needed when forced, even if .nfo exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test.nfo").write_text("<musicvideo/>")
    op = NfoOperation(load_config(), force=True)
    assert op.is_needed(video, _make_mf()) is True


def test_art_op_needed_when_missing(tmp_path):
    """Art operation needed when thumb doesn't exist."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = ArtOperation()
    assert op.is_needed(video, _make_mf()) is True


def test_art_op_not_needed_when_exists(tmp_path):
    """Art operation not needed when thumb exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    op = ArtOperation()
    assert op.is_needed(video, _make_mf()) is False


def test_poster_op_needed_when_thumb_exists_but_poster_missing(tmp_path):
    """Poster operation needed when thumb exists but poster doesn't."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    op = PosterOperation(load_config())
    assert op.is_needed(video, _make_mf()) is True


def test_poster_op_not_needed_when_poster_exists(tmp_path):
    """Poster operation not needed when poster exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "test-thumb.jpg").write_bytes(b"\xff\xd8")
    (tmp_path / "test-poster.jpg").write_bytes(b"\xff\xd8")
    op = PosterOperation(load_config())
    assert op.is_needed(video, _make_mf()) is False


def test_poster_op_not_needed_when_no_thumb(tmp_path):
    """Poster operation not needed when no thumb available."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = PosterOperation(load_config())
    assert op.is_needed(video, _make_mf()) is False


def test_organize_op_needed_when_not_at_target(tmp_path):
    """Organize operation needed when file is not at target location."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    target = tmp_path / "Artist" / "test.mkv"
    op = OrganizeOperation(target=target)
    assert op.is_needed(video, _make_mf()) is True


def test_organize_op_not_needed_when_at_target(tmp_path):
    """Organize operation not needed when file is already at target."""
    target = tmp_path / "Artist" / "test.mkv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")
    op = OrganizeOperation(target=target)
    assert op.is_needed(target, _make_mf()) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_operations.py -v`
Expected: ImportError — `festival_organizer.operations` doesn't exist.

- [ ] **Step 3: Implement operations.py**

```python
# festival_organizer/operations.py
"""Composable operations with gap detection."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.models import MediaFile


@dataclass
class OperationResult:
    """Result of a single operation execution."""
    name: str
    status: str  # "done", "skipped", "error"
    detail: str = ""


class Operation:
    """Base class for operations."""
    name: str = ""

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        """Check if this operation needs to run (gap detection)."""
        raise NotImplementedError

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        """Execute the operation. Returns result."""
        raise NotImplementedError


class OrganizeOperation(Operation):
    name = "organize"

    def __init__(self, target: Path, action: str = "move"):
        self.target = target
        self.action = action  # "move", "copy", "rename"

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        return file_path.resolve() != self.target.resolve()

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.executor import resolve_collision
        import shutil

        target = resolve_collision(self.target)
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            if self.action == "copy":
                shutil.copy2(file_path, target)
            elif self.action == "rename":
                file_path.rename(target)
            else:
                shutil.move(str(file_path), str(target))
            # Update target for downstream operations
            self.target = target
            return OperationResult(self.name, "done")
        except OSError as e:
            return OperationResult(self.name, "error", str(e))


class NfoOperation(Operation):
    name = "nfo"

    def __init__(self, config: Config, force: bool = False):
        self.config = config
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if self.force:
            return True
        return not file_path.with_suffix(".nfo").exists()

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.nfo import generate_nfo
        try:
            generate_nfo(media_file, file_path, self.config)
            return OperationResult(self.name, "done")
        except Exception as e:
            return OperationResult(self.name, "error", str(e))


class ArtOperation(Operation):
    name = "art"

    def __init__(self, force: bool = False):
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if self.force:
            return True
        thumb = file_path.with_name(f"{file_path.stem}-thumb.jpg")
        return not thumb.exists()

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.artwork import extract_cover
        try:
            result = extract_cover(file_path, file_path.parent)
            if result:
                return OperationResult(self.name, "done")
            return OperationResult(self.name, "error", "no embedded art, no frames")
        except Exception as e:
            return OperationResult(self.name, "error", str(e))


class PosterOperation(Operation):
    name = "poster"

    def __init__(self, config: Config, force: bool = False):
        self.config = config
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        thumb = file_path.with_name(f"{file_path.stem}-thumb.jpg")
        if not thumb.exists():
            return False  # Can't generate without thumb
        if self.force:
            return True
        poster = file_path.with_name(f"{file_path.stem}-poster.jpg")
        return not poster.exists()

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.poster import generate_set_poster
        try:
            thumb = file_path.with_name(f"{file_path.stem}-thumb.jpg")
            poster = file_path.with_name(f"{file_path.stem}-poster.jpg")
            mf = media_file
            festival_display = mf.festival
            if mf.location:
                festival_display = self.config.get_festival_display(
                    mf.festival, mf.location
                )
            generate_set_poster(
                source_image_path=thumb,
                output_path=poster,
                artist=mf.artist or "Unknown",
                festival=festival_display or mf.title or "",
                date=mf.date,
                year=mf.year,
                detail=mf.stage or mf.location or "",
            )
            return OperationResult(self.name, "done")
        except Exception as e:
            return OperationResult(self.name, "error", str(e))


class TagsOperation(Operation):
    name = "tags"

    def __init__(self, force: bool = False):
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if self.force:
            return True
        # Only MKV/WEBM support tag embedding
        if file_path.suffix.lower() not in (".mkv", ".webm"):
            return False
        # TODO: Could check if tags already embedded, but mkvpropedit
        # is fast and idempotent, so always run unless forcing skip
        return True

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.embed_tags import embed_tags
        try:
            success = embed_tags(media_file, file_path)
            if success:
                return OperationResult(self.name, "done")
            return OperationResult(self.name, "error", "embed_tags returned False")
        except Exception as e:
            return OperationResult(self.name, "error", str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_operations.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add festival_organizer/operations.py tests/test_operations.py
git commit -m "feat: composable operations with gap detection"
```

---

## Task 8: Runner with Live Progress

Create the Runner that processes files with operations and emits live progress.

**Files:**
- Create: `festival_organizer/progress.py`
- Create: `festival_organizer/runner.py`
- Create: `tests/test_runner.py`

- [ ] **Step 1: Write failing tests for progress formatting**

```python
# tests/test_runner.py
from io import StringIO
from pathlib import Path
from festival_organizer.progress import ProgressPrinter
from festival_organizer.operations import OperationResult


def test_progress_file_header():
    """Print file counter and name."""
    out = StringIO()
    pp = ProgressPrinter(total=5, stream=out)
    pp.file_start(Path("2024 - AMF - Martin Garrix.mkv"), "Martin Garrix/")
    output = out.getvalue()
    assert "[1/5]" in output
    assert "2024 - AMF - Martin Garrix.mkv" in output
    assert "Martin Garrix/" in output


def test_progress_operation_results():
    """Print operation results inline."""
    out = StringIO()
    pp = ProgressPrinter(total=3, stream=out)
    pp.file_start(Path("test.mkv"), "Artist/")
    pp.file_done([
        OperationResult("nfo", "done"),
        OperationResult("art", "done"),
        OperationResult("poster", "skipped", "exists"),
    ])
    output = out.getvalue()
    assert "nfo" in output
    assert "art" in output
    assert "poster" in output
    assert "exists" in output


def test_progress_summary():
    """Print aggregate summary."""
    out = StringIO()
    pp = ProgressPrinter(total=3, stream=out)
    pp.record_results([
        OperationResult("nfo", "done"),
        OperationResult("art", "done"),
    ])
    pp.record_results([
        OperationResult("nfo", "done"),
        OperationResult("art", "skipped", "exists"),
    ])
    pp.print_summary()
    output = out.getvalue()
    assert "NFO: 2" in output or "nfo: 2" in output.lower()


def test_progress_quiet_mode():
    """Quiet mode suppresses per-file output but keeps summary."""
    out = StringIO()
    pp = ProgressPrinter(total=1, stream=out, quiet=True)
    pp.file_start(Path("test.mkv"), "Artist/")
    pp.file_done([OperationResult("nfo", "done")])
    # Per-file output suppressed
    assert "test.mkv" not in out.getvalue()
    # Summary still works
    pp.record_results([OperationResult("nfo", "done")])
    pp.print_summary()
    assert "nfo" in out.getvalue().lower() or "NFO" in out.getvalue()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_runner.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement progress.py**

```python
# festival_organizer/progress.py
"""Live progress output formatting."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from festival_organizer.operations import OperationResult


class ProgressPrinter:
    """Formats and prints live progress during pipeline execution."""

    def __init__(
        self,
        total: int,
        stream=None,
        quiet: bool = False,
        verbose: bool = False,
    ):
        self.total = total
        self.stream = stream or sys.stdout
        self.quiet = quiet
        self.verbose = verbose
        self._file_index = 0
        self._counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def print_header(
        self,
        command: str,
        source: Path,
        output: Path,
        layout: str,
        tools: list[str],
    ) -> None:
        """Print the run header."""
        w = self.stream.write
        w(f"CrateDigger — {command}\n")
        w("=" * 56 + "\n")
        w(f"Source:  {source}\n")
        w(f"Output:  {output}\n")
        w(f"Layout:  {layout}\n")
        if tools:
            w(f"Tools:   {', '.join(tools)}\n")
        else:
            w("Tools:   NONE (filename parsing only)\n")
        w("=" * 56 + "\n\n")

    def file_start(self, filename: Path, target_folder: str) -> None:
        """Print the start of processing a file."""
        self._file_index += 1
        if self.quiet:
            return
        w = self.stream.write
        w(f"\n [{self._file_index}/{self.total}] {filename.name}\n")
        if target_folder:
            w(f"        -> {target_folder}\n")

    def file_done(self, results: list[OperationResult]) -> None:
        """Print operation results for the current file."""
        if self.quiet:
            return
        parts = []
        for r in results:
            if r.status == "done":
                parts.append(f"v {r.name}")
            elif r.status == "skipped":
                detail = f" ({r.detail})" if r.detail else ""
                parts.append(f"skip {r.name}{detail}")
            elif r.status == "error":
                detail = f" ({r.detail})" if r.detail else ""
                parts.append(f"! {r.name}{detail}")
        if parts:
            self.stream.write(f"        {'  '.join(parts)}\n")

    def record_results(self, results: list[OperationResult]) -> None:
        """Record results for summary aggregation."""
        for r in results:
            self._counts[r.name][r.status] += 1

    def print_summary(self, log_path: Path | None = None) -> None:
        """Print the final summary."""
        w = self.stream.write
        w("\n" + "=" * 56 + "\n")
        parts = []
        for op_name, statuses in sorted(self._counts.items()):
            done = statuses.get("done", 0)
            label = op_name.upper()
            parts.append(f"{label}: {done}")
        w(" | ".join(parts) + "\n")
        if log_path:
            w(f"Log:  {log_path}\n")
        w("=" * 56 + "\n")
```

- [ ] **Step 4: Implement runner.py**

```python
# festival_organizer/runner.py
"""Pipeline runner: executes operations per file with live progress."""
from __future__ import annotations

from pathlib import Path

from festival_organizer.models import MediaFile
from festival_organizer.operations import Operation, OperationResult
from festival_organizer.progress import ProgressPrinter


def run_pipeline(
    files: list[tuple[Path, MediaFile, list[Operation]]],
    progress: ProgressPrinter,
) -> list[list[OperationResult]]:
    """Run operations for each file, emitting live progress.

    Args:
        files: List of (file_path, media_file, operations) tuples.
            file_path is the current location of the file.
            Operations are executed in order.
        progress: ProgressPrinter for live output.

    Returns:
        List of result lists, one per file.
    """
    all_results = []

    for file_path, media_file, operations in files:
        # Determine target folder for display
        target_folder = ""
        for op in operations:
            if op.name == "organize" and hasattr(op, "target"):
                target_folder = str(op.target.parent.name) + "/"
                break

        progress.file_start(file_path, target_folder)

        file_results = []
        current_path = file_path

        for op in operations:
            if op.is_needed(current_path, media_file):
                result = op.execute(current_path, media_file)
                # If organize succeeded, update path for downstream ops
                if op.name == "organize" and result.status == "done":
                    current_path = op.target
            else:
                result = OperationResult(op.name, "skipped", "exists")
            file_results.append(result)

        progress.file_done(file_results)
        progress.record_results(file_results)
        all_results.append(file_results)

    return all_results
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_runner.py -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add festival_organizer/progress.py festival_organizer/runner.py tests/test_runner.py
git commit -m "feat: pipeline runner with live progress output"
```

---

## Task 9: New CLI Structure

Rewrite the CLI with the four workflow-oriented commands: scan, organize, enrich, chapters. Wire up operations and runner.

**Files:**
- Modify: `festival_organizer/cli.py`

- [ ] **Step 1: Rewrite cli.py with new command structure**

Replace the entire `build_parser()` function and `run()` function. Key changes:

```python
# festival_organizer/cli.py
"""Command-line interface with workflow-oriented subcommands."""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from festival_organizer.analyzer import analyse_file
from festival_organizer.classifier import classify
from festival_organizer.config import load_config
from festival_organizer.library import find_library_root, init_library
from festival_organizer import metadata
from festival_organizer.metadata import configure_tools
from festival_organizer.operations import (
    OrganizeOperation, NfoOperation, ArtOperation,
    PosterOperation, TagsOperation,
)
from festival_organizer.progress import ProgressPrinter
from festival_organizer.runner import run_pipeline
from festival_organizer.scanner import scan_folder
from festival_organizer.templates import render_folder, render_filename
from festival_organizer.logging_util import ActionLogger
from festival_organizer.normalization import safe_filename


HELP_TEXT = """\
CrateDigger — Festival set & concert library manager

Common workflows:
  organize scan ./downloads          Preview what would happen (dry run)
  organize organize ./downloads      Organize files into library structure
  organize enrich ./library          Add art, posters, tags to existing files
  organize chapters ./file.mkv       Add 1001Tracklists chapters

Run 'organize <command> --help' for details on each command.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="organize",
        description=HELP_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="Command to run")

    def add_common(p):
        p.add_argument("root", type=str, help="File or folder to process")
        p.add_argument("--output", "-o", type=str, help="Output folder")
        p.add_argument("--layout", choices=[
            "artist_flat", "festival_flat", "artist_nested", "festival_nested"
        ], help="Folder layout")
        p.add_argument("--config", type=str, help="Path to config.json")
        p.add_argument("--quiet", "-q", action="store_true", help="Suppress per-file output")
        p.add_argument("--verbose", "-v", action="store_true", help="Show detailed metadata")

    # scan (dry-run)
    scan_p = sub.add_parser("scan", help="Preview what would happen (dry run)")
    add_common(scan_p)

    # organize
    org_p = sub.add_parser("organize", help="Move/copy files into library structure")
    add_common(org_p)
    org_p.add_argument("--copy", action="store_true", help="Copy instead of move")
    org_p.add_argument("--rename-only", action="store_true", help="Rename in place only")
    org_p.add_argument("--enrich", action="store_true",
                       help="Also run enrichment after organizing")

    # enrich
    enr_p = sub.add_parser("enrich", help="Add metadata artifacts to files in place")
    add_common(enr_p)
    enr_p.add_argument("--only", type=str,
                       help="Comma-separated: nfo,art,posters,tags,chapters")
    enr_p.add_argument("--force", action="store_true",
                       help="Regenerate even if artifacts exist")

    # chapters
    chap_p = sub.add_parser("chapters", help="Add 1001Tracklists chapters")
    chap_p.add_argument("root", type=str, help="File or folder to process")
    chap_p.add_argument("--tracklist", "-t", type=str, help="Tracklist URL, ID, or query")
    chap_p.add_argument("--auto", action="store_true", help="Batch mode — no prompts")
    chap_p.add_argument("--preview", action="store_true", help="Show chapters without embedding")
    chap_p.add_argument("--force", action="store_true", help="Ignore stored URLs, fresh search")
    chap_p.add_argument("--delay", type=int, help="Delay between files (seconds)")
    chap_p.add_argument("--config", type=str, help="Path to config.json")
    chap_p.add_argument("--quiet", "-q", action="store_true", help="Suppress per-file output")

    return parser


def run(argv: list[str] | None = None) -> int:
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    # Resolve config layers
    config_path = Path(args.config) if getattr(args, "config", None) else None
    root = Path(args.root)

    # Find library root
    library_root = find_library_root(root)
    library_config_dir = (library_root / ".cratedigger") if library_root else None

    config = load_config(
        config_path=config_path,
        library_config_dir=library_config_dir,
    )
    configure_tools(config)

    # Layout override
    if getattr(args, "layout", None):
        config._data["default_layout"] = args.layout

    # Handle chapters separately
    if args.command == "chapters":
        from festival_organizer.tracklists.cli_handler import run_chapters
        # Map new flag names to what cli_handler expects
        args.auto_select = getattr(args, "auto", False)
        args.ignore_stored_url = getattr(args, "force", False)
        return run_chapters(args, config)

    if not root.exists():
        print(f"Error: path does not exist: {root}", file=sys.stderr)
        return 1

    # Determine output root
    output = Path(args.output) if getattr(args, "output", None) else None
    if output is None:
        output = library_root if library_root else root

    # Initialize library marker on first organize
    if args.command == "organize" and not library_root:
        init_library(output, layout=config.default_layout)

    quiet = args.quiet
    verbose = getattr(args, "verbose", False)

    # Scan
    progress = ProgressPrinter(total=0, quiet=quiet, verbose=verbose)
    tools = []
    if metadata.MEDIAINFO_PATH:
        tools.append("mediainfo")
    if metadata.FFPROBE_PATH:
        tools.append("ffprobe")
    if metadata.MKVEXTRACT_PATH:
        tools.append("mkvextract")
    if metadata.MKVPROPEDIT_PATH:
        tools.append("mkvpropedit")
    progress.print_header(
        command=args.command.capitalize(),
        source=root, output=output,
        layout=config.default_layout, tools=tools,
    )

    print("Scanning...")
    files = scan_folder(root, config)
    print(f"Found {len(files)} media file(s).\n")
    if not files:
        print("Nothing to do.")
        return 0

    progress.total = len(files)

    # Analyze + classify
    media_files = []
    for fp in files:
        mf = analyse_file(fp, root, config)
        mf.content_type = classify(mf, root, config)
        media_files.append((fp, mf))

    # Build operations per file
    force = getattr(args, "force", False)
    pipeline_files = []

    for fp, mf in media_files:
        ops: list = []

        if args.command == "scan":
            # Dry run — no operations, just show plan
            target_folder = render_folder(mf, config)
            target_name = render_filename(mf, config)
            target = output / target_folder / (safe_filename(target_name) + mf.extension)
            progress.file_start(fp, target_folder + "/")
            progress.file_done([])
            continue

        if args.command == "organize":
            target_folder = render_folder(mf, config)
            target_name = render_filename(mf, config)
            target = output / target_folder / (safe_filename(target_name) + mf.extension)
            action = "copy" if getattr(args, "copy", False) else \
                     "rename" if getattr(args, "rename_only", False) else "move"
            ops.append(OrganizeOperation(target=target, action=action))

            if getattr(args, "enrich", False):
                ops.append(NfoOperation(config))
                ops.append(ArtOperation())
                ops.append(PosterOperation(config))
                ops.append(TagsOperation())

        elif args.command == "enrich":
            only = set()
            if getattr(args, "only", None):
                only = set(args.only.split(","))

            if not only or "nfo" in only:
                ops.append(NfoOperation(config, force=force))
            if not only or "art" in only:
                ops.append(ArtOperation(force=force))
            if not only or "posters" in only:
                ops.append(PosterOperation(config, force=force))
            if not only or "tags" in only:
                ops.append(TagsOperation(force=force))

            # Chapters in enrich runs in batch/auto mode
            if "chapters" in only:
                # Delegate to chapters handler in auto mode
                # This is handled separately after the main pipeline
                pass

        pipeline_files.append((fp, mf, ops))

    if args.command == "scan":
        # Already printed in the loop above
        progress.print_summary()
        return 0

    # Run pipeline
    all_results = run_pipeline(pipeline_files, progress)

    # If enrich includes chapters, run chapters handler in auto mode
    if args.command == "enrich" and only and "chapters" in only:
        from festival_organizer.tracklists.cli_handler import run_chapters
        # Build a chapters-compatible args namespace
        import types
        chap_args = types.SimpleNamespace(
            root=str(root),
            tracklist=None,
            auto=True,  # Batch mode for enrich
            preview=False,
            force=force,
            delay=None,
            config=getattr(args, "config", None),
            quiet=quiet,
        )
        run_chapters(chap_args, config)

    progress.print_summary()

    return 0
```

- [ ] **Step 2: Run smoke test**

Run: `python organize.py --help`
Expected: Shows the new help text with scan, organize, enrich, chapters commands.

Run: `python organize.py scan --help`
Expected: Shows scan-specific options.

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass. The `test_cli_postprocess.py` tests may need updates since `FileAction` post-processing booleans are now handled by operations. Update those tests to match the new architecture.

- [ ] **Step 4: Update test_cli_postprocess.py**

The old `_run_post_processing` function is removed. Update or replace these tests to test the operations pipeline instead. The individual operation tests in `test_operations.py` already cover this behavior.

- [ ] **Step 5: Commit**

```bash
git add festival_organizer/cli.py tests/test_cli_postprocess.py
git commit -m "feat: new CLI with scan/organize/enrich/chapters commands"
```

---

## Task 10: Update FileAction Model

Remove post-processing booleans from FileAction since operations handle this now. Keep FileAction for backward compatibility with executor and logging, but simplify it.

**Files:**
- Modify: `festival_organizer/models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Remove post-processing booleans from FileAction**

In `festival_organizer/models.py`, remove these fields from `FileAction`:
- `generate_nfo: bool = False`
- `extract_art: bool = False`
- `generate_posters: bool = False`
- `embed_tags: bool = False`

```python
@dataclass
class FileAction:
    source: Path
    target: Path
    media_file: MediaFile
    action: str = "move"
    status: str = "pending"
    error: str = ""
```

- [ ] **Step 2: Update tests referencing removed fields**

Search all test files for `generate_nfo`, `extract_art`, `generate_posters`, `embed_tags` on FileAction. Remove or update those assertions.

- [ ] **Step 3: Update planner.py**

Remove the `generate_nfo`, `extract_art`, `generate_posters`, `embed_tags` parameters from `plan_actions()`. These are now handled by operations.

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add festival_organizer/models.py festival_organizer/planner.py tests/
git commit -m "refactor: remove post-processing booleans from FileAction"
```

---

## Task 11: Album Poster Integration

Wire the existing `generate_album_poster` into the poster operation for folder-level `folder.jpg` generation.

**Files:**
- Modify: `festival_organizer/operations.py`
- Modify: `tests/test_operations.py`

- [ ] **Step 1: Write failing test for album poster gap detection**

```python
# tests/test_operations.py — add

from festival_organizer.operations import AlbumPosterOperation


def test_album_poster_needed_when_missing(tmp_path):
    """Album poster needed when folder.jpg doesn't exist."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    op = AlbumPosterOperation(config=load_config())
    assert op.is_needed(video, _make_mf()) is True


def test_album_poster_not_needed_when_exists(tmp_path):
    """Album poster not needed when folder.jpg exists."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    (tmp_path / "folder.jpg").write_bytes(b"\xff\xd8")
    op = AlbumPosterOperation(config=load_config())
    assert op.is_needed(video, _make_mf()) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_operations.py -v -k "album_poster"`
Expected: ImportError — `AlbumPosterOperation` doesn't exist.

- [ ] **Step 3: Implement AlbumPosterOperation**

Add to `festival_organizer/operations.py`:

```python
class AlbumPosterOperation(Operation):
    name = "album_poster"

    def __init__(self, config: Config, force: bool = False):
        self.config = config
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        folder_jpg = file_path.parent / "folder.jpg"
        if self.force:
            return not folder_jpg.exists() or True
        return not folder_jpg.exists()

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.poster import generate_album_poster
        try:
            folder_jpg = file_path.parent / "folder.jpg"
            mf = media_file
            festival_display = mf.festival
            if mf.location:
                festival_display = self.config.get_festival_display(
                    mf.festival, mf.location
                )
            date_or_year = mf.date or mf.year or ""

            # Collect existing thumbs in folder for color extraction
            thumb_paths = list(file_path.parent.glob("*-thumb.jpg"))

            generate_album_poster(
                output_path=folder_jpg,
                festival=festival_display or mf.artist or "Unknown",
                date_or_year=date_or_year,
                detail=mf.stage or mf.location or "",
                thumb_paths=thumb_paths if thumb_paths else None,
            )
            return OperationResult(self.name, "done")
        except Exception as e:
            return OperationResult(self.name, "error", str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_operations.py -v -k "album_poster"`
Expected: All pass.

- [ ] **Step 5: Wire album poster into enrich command**

In `festival_organizer/cli.py`, add `AlbumPosterOperation` to the enrich pipeline after `PosterOperation`:

```python
# In the enrich section of run():
if not only or "posters" in only:
    ops.append(PosterOperation(config, force=force))
    ops.append(AlbumPosterOperation(config, force=force))
```

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add festival_organizer/operations.py festival_organizer/cli.py tests/test_operations.py
git commit -m "feat: album poster generation via clean poster in operations pipeline"
```

---

## Task 12: Update config.json and Migration

Update the shipped `config.json` to reflect new layout names and structure. Ensure backward compatibility.

**Files:**
- Modify: `config.json`
- Modify: `festival_organizer/config.py`

- [ ] **Step 1: Update config.json**

Update `config.json` at the project root to match the new structure:
- Change `default_layout` to `"artist_flat"`
- Rename layout keys: `artist_first` → `artist_nested`, `festival_first` → `festival_nested`
- Add `artist_flat` and `festival_flat` layouts
- Add `tracklists` section (move from `tracklists_settings`, add email/password fields)
- Keep backward compatibility by not removing `tracklists_settings` yet

- [ ] **Step 2: Add backward compatibility in Config class**

In `config.py`, ensure the Config class handles both old and new layout names. Add a migration note in `load_config`:

```python
# In load_config, after merging all layers:
# Backward compatibility: map old layout names to new
if data.get("default_layout") == "artist_first":
    data["default_layout"] = "artist_nested"
elif data.get("default_layout") == "festival_first":
    data["default_layout"] = "festival_nested"
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add config.json festival_organizer/config.py
git commit -m "feat: update config with new layouts and backward compatibility"
```

---

## Task 13: Integration Smoke Test

Verify the full pipeline works end-to-end with the new command structure.

**Files:**
- Modify: `tests/test_integration.py` (if needed)

- [ ] **Step 1: Manual smoke test — scan**

Run: `python organize.py scan //hyperv/Data/Concerts` (or a local test folder)
Expected: Live output showing files, classification, and planned target paths. No files moved.

- [ ] **Step 2: Manual smoke test — organize with enrich**

Create a temp folder with a few test MKV files. Run:
```bash
python organize.py organize /tmp/test_input -o /tmp/test_output --enrich
```
Expected: Files moved, NFOs generated, art extracted, posters generated (where possible), tags embedded. Live progress shown.

- [ ] **Step 3: Manual smoke test — enrich**

Run on the output from step 2:
```bash
python organize.py enrich /tmp/test_output
```
Expected: Gap detection kicks in — most operations skipped with "exists". Only missing artifacts generated.

- [ ] **Step 4: Manual smoke test — enrich with force**

```bash
python organize.py enrich /tmp/test_output --force
```
Expected: All artifacts regenerated.

- [ ] **Step 5: Manual smoke test — enrich only specific operations**

```bash
python organize.py enrich /tmp/test_output --only nfo,art
```
Expected: Only NFO and art operations run.

- [ ] **Step 6: Run full automated test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 7: Commit any test fixes**

```bash
git add tests/
git commit -m "test: update integration tests for new CLI structure"
```

---

## Task 14: Final Cleanup

Remove dead code, update imports, ensure everything is clean.

**Files:**
- Various files across the project

- [ ] **Step 1: Remove dead code**

- Remove `_run_post_processing`, `_run_nfo_only`, `_run_extract_art_only`, `_run_posters_only` from `cli.py` (if not already removed)
- Remove `execute` subcommand references
- Remove old `nfo`, `extract-art`, `posters` subcommand handlers (replaced by `enrich --only`)

- [ ] **Step 2: Clean up imports**

Run: `python -m pytest tests/ -v` to verify nothing broke.

- [ ] **Step 3: Update organize.py entry script docstring**

```python
#!/usr/bin/env python3
"""CrateDigger — Festival set & concert library manager.

Usage:
    organize.py scan <path>          Preview what would happen
    organize.py organize <path>      Move/copy files into library
    organize.py enrich <path>        Add metadata artifacts in place
    organize.py chapters <path>      Add 1001Tracklists chapters
"""
import sys
from festival_organizer.cli import run
sys.exit(run())
```

- [ ] **Step 4: Run full test suite one final time**

Run: `python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove dead code and clean up imports"
```
