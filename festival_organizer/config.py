"""Configuration loading and access."""
import json
import logging
import re
import sys
from copy import deepcopy
from fnmatch import fnmatch
from pathlib import Path

logger = logging.getLogger(__name__)


# Defaults for external config files (artists.json, festivals.json)
# Default config embedded so the tool works without a config file
DEFAULT_CONFIG = {
    "default_layout": "artist_flat",
    "layouts": {
        "artist_flat": {
            "festival_set": "{artist}",
            "concert_film": "{artist}",
        },
        "festival_flat": {
            "festival_set": "{festival}{ edition}",
            "concert_film": "{artist}",
        },
        "artist_nested": {
            "festival_set": "{artist}/{festival}{ edition}/{year}",
            "concert_film": "{artist}/{year} - {title}",
        },
        "festival_nested": {
            "festival_set": "{festival}{ edition}/{year}/{artist}",
            "concert_film": "{artist}/{year} - {title}",
        },
    },
    "filename_templates": {
        "festival_set": "{year} - {artist} - {festival}{ edition}{ [stage]}{ - set_title}",
        "concert_film": "{artist} - {title}{ (year)}",
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
    "poster_settings": {
        "artist_background_priority": ["dj_artwork", "fanart_tv", "gradient"],
        "festival_background_priority": ["curated_logo", "thumb_collage", "gradient"],
        "year_background_priority": ["gradient"],
    },
    "nfo_settings": {
        "genre_festival": "Electronic",
        "genre_concert": "Live",
    },
    "tool_paths": {
        "mediainfo": None,
        "ffprobe": None,
        "mkvextract": None,
        "mkvpropedit": None,
        "mkvmerge": None,
    },
"tracklists": {
        "email": "",
        "password": "",
        "delay_seconds": 5,
        "chapter_language": "eng",
        "auto_select": False,
    },
    "fanart": {
        "project_api_key": "9fb9273dbec3739bd0fdb49f10d6a129",
        "personal_api_key": "",
        "enabled": True,
    },
    "kodi": {
        "enabled": False,
        "host": "localhost",
        "port": 8080,
        "username": "kodi",
        "password": "",
        "path_mapping": None,
    },
}


def _invert_alias_map(grouped: dict) -> dict[str, str]:
    """Convert alias map to {alias: canonical} flat lookup.

    Accepts two formats:
    - Grouped: {canonical: [aliases]} — standard format
    - Flat: {alias: canonical} — deprecated, auto-detected per entry
    """
    flat = {}
    for key, value in grouped.items():
        if isinstance(value, list):
            # Grouped format: {canonical: [aliases]}
            flat[key] = key
            for alias in value:
                flat[alias] = key
        elif isinstance(value, str):
            # Flat format: {alias: canonical} — already inverted
            flat[key] = value
        else:
            logger.warning("Skipping alias entry '%s': expected str or list, got %s",
                           key, type(value).__name__)
            continue
    # Detect circular flat references
    for key, value in flat.items():
        if value in flat and flat[value] != value and flat[value] == key:
            logger.warning("Circular alias: '%s' <-> '%s'. "
                           "One should be canonical (pointing to itself).", key, value)
    return flat


class Config:
    """Typed access to the configuration."""

    def __init__(self, data: dict, config_dir: Path | None = None):
        self._data = {**DEFAULT_CONFIG, **data}
        self._config_dir = config_dir
        self._ext_cache: dict[str, dict] = {}

    def _load_external_config(self, filename: str, defaults: dict) -> dict:
        """Load config from external JSON file, with caching."""
        if filename in self._ext_cache:
            return self._ext_cache[filename]

        candidates: list[Path] = []
        if self._config_dir:
            candidates.append(self._config_dir / filename)
        candidates.append(Path.home() / ".cratedigger" / filename)

        for path in candidates:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    self._ext_cache[filename] = data
                    return data
                except (json.JSONDecodeError, OSError):
                    pass

        self._ext_cache[filename] = defaults
        return defaults

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
    def festival_aliases(self) -> dict[str, str]:
        raw = self._load_external_config("festivals.json", {}).get("aliases", {})
        if "festival_aliases" in self._data:
            raw = {**raw, **self._data["festival_aliases"]}
        return _invert_alias_map(raw)

    @property
    def festival_config(self) -> dict:
        defaults = self._load_external_config("festivals.json", {}).get("config", {})
        if "festival_config" in self._data:
            return {**defaults, **self._data["festival_config"]}
        return defaults

    @property
    def all_known_editions(self) -> set[str]:
        """Collect all editions from every festival config entry."""
        editions = set()
        for fc in self.festival_config.values():
            for ed in fc.get("editions", []):
                editions.add(ed)
        return editions

    def resolve_festival_with_edition(self, name: str) -> tuple[str, str]:
        """Resolve alias and extract edition from the name if applicable.

        Returns (canonical_festival, edition).
        "Dreamstate SoCal" -> ("Dreamstate", "SoCal")
        "Tomorrowland Winter" -> ("Tomorrowland", "Winter")
        "TML" -> ("Tomorrowland", "")
        """
        canonical = self.resolve_festival_alias(name)

        # Alias resolved to something different: check for edition suffix
        if canonical != name:
            fc = self.festival_config.get(canonical, {})
            suffix = name[len(canonical):].strip() if name.lower().startswith(canonical.lower()) else ""
            for ed in fc.get("editions", []):
                if ed.lower() == suffix.lower():
                    return canonical, ed
            return canonical, ""

        # No alias match. Try canonical + edition decomposition.
        for fest_name, fc in self.festival_config.items():
            for ed in fc.get("editions", []):
                if f"{fest_name} {ed}".lower() == name.lower():
                    return fest_name, ed

        # Try alias prefixes (handles "Ultra Europe" via alias "Ultra")
        for alias, canon in self.festival_aliases.items():
            fc = self.festival_config.get(canon, {})
            for ed in fc.get("editions", []):
                if f"{alias} {ed}".lower() == name.lower():
                    return canon, ed

        return name, ""

    @property
    def poster_settings(self) -> dict:
        defaults = DEFAULT_CONFIG.get("poster_settings", {})
        overrides = self._data.get("poster_settings", {})
        return {**defaults, **overrides}

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
    def tool_paths(self) -> dict:
        return self._data.get("tool_paths", {})

    @property
    def tracklists_settings(self) -> dict:
        """Settings for tracklist chapter operations."""
        return self._data.get("tracklists", {})

    @property
    def tracklists_credentials(self) -> tuple[str, str]:
        """Return (email, password) — env vars override config."""
        import os
        tl = self._data.get("tracklists", {})
        email = os.environ.get("TRACKLISTS_EMAIL") or tl.get("email", "")
        password = os.environ.get("TRACKLISTS_PASSWORD") or tl.get("password", "")
        return (email, password)

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
        """All festival names the system can recognize."""
        names = set(self.festival_aliases.keys())
        names.update(self.festival_aliases.values())
        for fest_name, fc in self.festival_config.items():
            for ed in fc.get("editions", []):
                names.add(f"{fest_name} {ed}")
        return names

    def resolve_festival_alias(self, name: str) -> str:
        """Map a festival name/abbreviation to its canonical form."""
        # Try exact match first, then case-insensitive
        if name in self.festival_aliases:
            resolved = self.festival_aliases[name]
            if resolved != name:
                logger.debug("Festival alias: '%s' -> '%s'", name, resolved)
            return resolved
        lower_map = {k.lower(): v for k, v in self.festival_aliases.items()}
        resolved = lower_map.get(name.lower(), name)
        if resolved != name:
            logger.debug("Festival alias (case-insensitive): '%s' -> '%s'", name, resolved)
        return resolved

    def _load_dj_aliases(self) -> dict[str, str]:
        """Load artist aliases derived from DJ cache."""
        try:
            from festival_organizer.tracklists.dj_cache import DjCache
            cache = DjCache()
            return cache.derive_artist_aliases()
        except Exception:
            return {}

    def _load_dj_groups(self) -> set[str]:
        """Load artist groups derived from DJ cache."""
        try:
            from festival_organizer.tracklists.dj_cache import DjCache
            cache = DjCache()
            return cache.derive_artist_groups()
        except Exception:
            return set()

    @property
    def artist_aliases(self) -> dict[str, str]:
        raw = self._load_external_config("artists.json", {}).get("aliases", {})
        if "artist_aliases" in self._data:
            raw = {**raw, **self._data["artist_aliases"]}
        flat = _invert_alias_map(raw)
        # Merge DJ cache aliases (manual config takes priority)
        dj_aliases = self._load_dj_aliases()
        return {**dj_aliases, **flat}

    @property
    def artist_groups(self) -> set[str]:
        if "artist_groups" in self._data:
            groups = {g.lower() for g in self._data["artist_groups"]}
        else:
            groups = set()
        ext_groups = self._load_external_config("artists.json", {}).get("groups", [])
        groups.update(g.lower() for g in ext_groups)
        groups.update(self._load_dj_groups())
        return groups

    def resolve_artist(self, name: str) -> str:
        """Resolve artist alias, then for B2Bs not in groups return first artist."""
        original = name
        # 1. Resolve alias (case-insensitive)
        aliased = False
        if name in self.artist_aliases:
            name = self.artist_aliases[name]
            aliased = True
        else:
            lower_map = {k.lower(): v for k, v in self.artist_aliases.items()}
            resolved = lower_map.get(name.lower())
            if resolved is not None:
                name = resolved
                aliased = True

        # If an alias matched, the user explicitly chose this canonical name
        if aliased:
            if name != original:
                logger.debug("Artist alias: '%s' -> '%s'", original, name)
            return name

        # 2. If the full name is a known group, keep it
        if name.lower() in self.artist_groups:
            return name

        # 3. Split on separators, return first artist
        parts = re.split(r"\s+(?:&|B2B|b2b|vs\.?|x)\s+", name, flags=re.IGNORECASE)
        if len(parts) > 1:
            return parts[0].strip()

        return name

    def get_festival_display(self, canonical_festival: str, edition: str) -> str:
        """Get display name for a festival, optionally including edition."""
        fc = self.festival_config.get(canonical_festival, {})
        editions = fc.get("editions", [])
        if editions and edition:
            for ed in editions:
                if ed.lower() == edition.lower():
                    return f"{canonical_festival} {ed}"
        return canonical_festival

    def get_layout_template(self, content_type: str, layout_name: str | None = None) -> str:
        """Get the folder layout template for a content type."""
        layout = layout_name or self.default_layout
        layouts = self.layouts.get(layout, {})
        return layouts.get(content_type, layouts.get("festival_set", "{artist}/{year}"))

    def get_filename_template(self, content_type: str) -> str:
        """Get the filename template for a content type."""
        return self.filename_templates.get(content_type, "{artist} - {title}")

    @property
    def fanart_settings(self) -> dict:
        return self._data.get("fanart", {})

    @property
    def fanart_project_api_key(self) -> str:
        """Return fanart.tv project API key — env var override + config fallback."""
        import os
        return os.environ.get("FANART_PROJECT_API_KEY") or self.fanart_settings.get("project_api_key", "")

    @property
    def fanart_personal_api_key(self) -> str:
        """Return fanart.tv personal API key — env var override + config fallback."""
        import os
        return os.environ.get("FANART_PERSONAL_API_KEY") or self.fanart_settings.get("personal_api_key", "")

    @property
    def fanart_enabled(self) -> bool:
        return self.fanart_settings.get("enabled", True)

    @property
    def kodi_settings(self) -> dict:
        return self._data.get("kodi", {})

    @property
    def kodi_enabled(self) -> bool:
        return self.kodi_settings.get("enabled", False)

    @property
    def kodi_host(self) -> str:
        import os
        return os.environ.get("KODI_HOST") or self.kodi_settings.get("host", "localhost")

    @property
    def kodi_port(self) -> int:
        import os
        env_port = os.environ.get("KODI_PORT")
        if env_port:
            try:
                return int(env_port)
            except ValueError:
                logger.warning("Invalid KODI_PORT '%s', using config default", env_port)
        return self.kodi_settings.get("port", 8080)

    @property
    def kodi_username(self) -> str:
        import os
        return os.environ.get("KODI_USERNAME") or self.kodi_settings.get("username", "kodi")

    @property
    def kodi_password(self) -> str:
        import os
        return os.environ.get("KODI_PASSWORD") or self.kodi_settings.get("password", "")

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


def load_config(
    config_path: Path | None = None,
    user_config_dir: Path | None = None,
    library_config_dir: Path | None = None,
) -> Config:
    """Load config with three-layer merge: built-in < user < library.

    If config_path is provided (legacy), loads from that file as user layer.
    Otherwise:
      - user_config_dir defaults to ~/.cratedigger/
      - library_config_dir is typically .cratedigger/ at library root
    """
    data = deepcopy(DEFAULT_CONFIG)

    # Legacy path support
    if config_path and config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                _deep_merge(data, json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not read {config_path}: {e}", file=sys.stderr)
        _migrate_layout_names(data)
        return Config(data, config_dir=config_path.parent)

    # Layer 2: User config
    if user_config_dir is None:
        user_config_dir = Path.home() / ".cratedigger"
    user_file = user_config_dir / "config.json"
    if user_file.exists():
        try:
            with open(user_file, "r", encoding="utf-8") as f:
                _deep_merge(data, json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not read {user_file}: {e}", file=sys.stderr)

    # Layer 3: Library config
    if library_config_dir is not None:
        lib_file = library_config_dir / "config.json"
        if lib_file.exists():
            try:
                with open(lib_file, "r", encoding="utf-8") as f:
                    _deep_merge(data, json.load(f))
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: could not read {lib_file}: {e}", file=sys.stderr)

    _migrate_layout_names(data)
    return Config(data, config_dir=library_config_dir or user_config_dir)


def _migrate_layout_names(data: dict) -> None:
    """Backward compatibility: map old layout names to new."""
    if data.get("default_layout") == "artist_first":
        data["default_layout"] = "artist_nested"
    elif data.get("default_layout") == "festival_first":
        data["default_layout"] = "festival_nested"


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base (mutates base)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
