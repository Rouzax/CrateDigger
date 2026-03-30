"""Configuration loading and access."""
import json
import re
import sys
from copy import deepcopy
from fnmatch import fnmatch
from pathlib import Path


# Defaults for external config files (artists.json, festivals.json)
_ARTIST_DEFAULTS = {
    "aliases": {},
    "groups": [
        "Above & Beyond",
        "Axwell & Ingrosso",
        "Dimitri Vegas & Like Mike",
        "Sunnery James & Ryan Marciano",
        "Swedish House Mafia",
        "Vini Vici",
    ],
}

_FESTIVAL_DEFAULTS = {
    "aliases": {
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
    "config": {
        "Tomorrowland": {
            "location_in_name": True,
            "known_locations": ["Belgium", "Brasil", "Brazil"],
        },
        "EDC": {
            "location_in_name": True,
            "known_locations": ["Las Vegas", "Mexico", "Orlando"],
        },
    },
}

# Default config embedded so the tool works without a config file
DEFAULT_CONFIG = {
    "default_layout": "artist_flat",
    "layouts": {
        "artist_flat": {
            "festival_set": "{artist}",
            "concert_film": "{artist}",
        },
        "festival_flat": {
            "festival_set": "{festival}",
            "concert_film": "{artist}",
        },
        "artist_nested": {
            "festival_set": "{artist}/{festival}/{year}",
            "concert_film": "{artist}/{year} - {title}",
        },
        "festival_nested": {
            "festival_set": "{festival}/{year}/{artist}",
            "concert_film": "{artist}/{year} - {title}",
        },
    },
    "filename_templates": {
        "festival_set": "{year} - {festival} - {artist}",
        "concert_film": "{artist} - {title}",
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
    "tool_paths": {
        "mediainfo": None,
        "ffprobe": None,
        "mkvextract": None,
        "mkvpropedit": None,
        "mkvmerge": None,
    },
    "tracklists_aliases": {
        "amf": "Amsterdam Music Festival",
        "ade": "Amsterdam Dance Event",
        "edc": "Electric Daisy Carnival",
        "umf": "Ultra Music Festival",
        "asot": "A State of Trance",
        "abgt": "Above & Beyond Group Therapy",
        "wao138": "Who's Afraid of 138",
        "fsoe": "Future Sound of Egypt",
        "gdjb": "Global DJ Broadcast",
        "sw4": "South West Four",
        "tml": "Tomorrowland",
        "tl": "Tomorrowland",
        "dwp": "Djakarta Warehouse Project",
        "mmw": "Miami Music Week",
    },
    "tracklists_settings": {
        "chapter_language": "eng",
        "auto_select": False,
        "delay_seconds": 5,
    },
    "tracklists": {
        "email": "",
        "password": "",
        "delay_seconds": 5,
        "chapter_language": "eng",
    },
    "fanart": {
        "project_api_key": "9fb9273dbec3739bd0fdb49f10d6a129",
        "personal_api_key": "",
        "enabled": True,
    },
}


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
        defaults = self._load_external_config("festivals.json", _FESTIVAL_DEFAULTS).get("aliases", {})
        if "festival_aliases" in self._data:
            return {**defaults, **self._data["festival_aliases"]}
        return defaults

    @property
    def festival_config(self) -> dict:
        defaults = self._load_external_config("festivals.json", _FESTIVAL_DEFAULTS).get("config", {})
        if "festival_config" in self._data:
            return {**defaults, **self._data["festival_config"]}
        return defaults

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
    def tracklists_aliases(self) -> dict[str, str]:
        """Lowercase-keyed abbreviation -> full name mappings for tracklist scoring."""
        return self._data.get("tracklists_aliases", {})

    @property
    def tracklists_settings(self) -> dict:
        """Settings for tracklist chapter operations."""
        return self._data.get("tracklists_settings", {})

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
        """All canonical festival names (the values of the alias map)."""
        return set(self.festival_aliases.values())

    def resolve_festival_alias(self, name: str) -> str:
        """Map a festival name/abbreviation to its canonical form."""
        # Try exact match first, then case-insensitive
        if name in self.festival_aliases:
            return self.festival_aliases[name]
        lower_map = {k.lower(): v for k, v in self.festival_aliases.items()}
        return lower_map.get(name.lower(), name)

    @property
    def artist_aliases(self) -> dict[str, str]:
        defaults = self._load_external_config("artists.json", _ARTIST_DEFAULTS).get("aliases", {})
        if "artist_aliases" in self._data:
            return {**defaults, **self._data["artist_aliases"]}
        return defaults

    @property
    def artist_groups(self) -> set[str]:
        if "artist_groups" in self._data:
            return {g.lower() for g in self._data["artist_groups"]}
        groups = self._load_external_config("artists.json", _ARTIST_DEFAULTS).get("groups", [])
        return {g.lower() for g in groups}

    def resolve_artist(self, name: str) -> str:
        """Resolve artist alias, then for B2Bs not in groups return first artist."""
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
            return name

        # 2. If the full name is a known group, keep it
        if name.lower() in self.artist_groups:
            return name

        # 3. Split on separators, return first artist
        parts = re.split(r"\s+(?:&|B2B|b2b|vs\.?|x)\s+", name, flags=re.IGNORECASE)
        if len(parts) > 1:
            return parts[0].strip()

        return name

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
