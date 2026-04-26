"""Configuration loading and access.

Logging:
    Logger: 'festival_organizer.config'
    Key events:
        - alias.invalid_entry (WARNING): Alias map entry has unexpected type
        - alias.circular (WARNING): Two aliases point at each other
        - alias.resolve_place (DEBUG): Place name resolved via alias
        - alias.resolve_artist (DEBUG): Artist name resolved via alias
        - config.layer (DEBUG): Config TOML file loaded or not found (deferred)
        - config.external_candidates (DEBUG): Candidate paths for external config
        - config.external_loaded (DEBUG): External JSON config loaded from path
        - config.external_not_found (DEBUG): External JSON not found in any candidate
        - config.invalid_kodi_port (WARNING): KODI_PORT env var is not a valid int
        - config.deprecated_once (WARNING): Deprecated config surface used; logged once per key per process
    See docs/logging.md for full guidelines.
"""
import json
import logging
import re
import tomllib
from copy import deepcopy
from fnmatch import fnmatch
from functools import cached_property
from pathlib import Path

from festival_organizer import paths
from festival_organizer.normalization import strip_diacritics

logger = logging.getLogger(__name__)


_emitted_deprecations: set[str] = set()


def _log_deprecated_once(key: str, message: str) -> None:
    """Emit a WARNING-level deprecation log exactly once per process per key."""
    if key in _emitted_deprecations:
        return
    _emitted_deprecations.add(key)
    logger.warning(message)


# Defaults for external config files (artists.json, places.json)
# Default config embedded so the tool works without a config file
DEFAULT_CONFIG = {
    "default_layout": "artist_flat",
    "layouts": {
        "artist_flat": {
            "festival_set": "{artist}",
            "concert_film": "{artist}",
        },
        "place_flat": {
            "festival_set": "{place}{ edition}",
            "concert_film": "{artist}",
        },
        "artist_nested": {
            "festival_set": "{artist}/{place}{ edition}/{year}",
            "concert_film": "{artist}/{year} - {title}",
        },
        "place_nested": {
            "festival_set": "{place}{ edition}/{year}/{artist}",
            "concert_film": "{artist}/{year} - {title}",
        },
    },
    "filename_templates": {
        "festival_set": "{year} - {artist}{ - place}{ edition}{ [stage]}{ - set_title}",
        "concert_film": "{artist} - {title}{ (year)}",
    },
    "content_type_rules": {
        "force_concert": [
            "Adele/*",
            "Coldplay/*",
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
        "unknown_place": "_Needs Review",
        "unknown_year": "Unknown Year",
        "unknown_title": "Unknown Title",
    },
    "poster_settings": {
        "artist_background_priority": ["dj_artwork", "fanart_tv", "gradient"],
        "festival_background_priority": ["curated_logo", "gradient"],
        "place_background_priority": ["curated_logo", "gradient"],
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
        # Cap on the set-level CRATEDIGGER_1001TL_GENRES tag: keep only the
        # top-N most frequent per-track genres. Ties are broken by first
        # appearance, so the result is deterministic. Set to 0 to disable
        # the cap and write every per-track genre (noisy on some sets).
        "genre_top_n": 5,
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
    "cache_ttl": {
        # Base TTL in days for each cache. Actual per-entry lifetimes jitter
        # by +/- 20% around the base to avoid thundering-herd re-fetches after
        # a bulk first-run cache fill. JSON-backed caches (dj_cache, source_cache,
        # mbid_cache) stamp the randomised TTL into each entry. Filesystem-mtime
        # caches (images) use a deterministic hash of the path for jitter.
        "mbid_days": 90,
        "dj_days": 90,
        "source_days": 365,
        "images_days": 90,
    },
}


def _ci_lookup(mapping: dict[str, str], key: str) -> str | None:
    """Case-insensitive lookup in a string-keyed dict. Returns value or None."""
    lower_map = {k.lower(): v for k, v in mapping.items()}
    return lower_map.get(key.lower())


def _invert_alias_map(grouped: dict) -> dict[str, str]:
    """Convert alias map to {alias: canonical} flat lookup.

    Accepts two formats:
    - Grouped: {canonical: [aliases]}, standard format
    - Flat: {alias: canonical}, deprecated, auto-detected per entry
    """
    flat = {}
    for key, value in grouped.items():
        if isinstance(value, list):
            # Grouped format: {canonical: [aliases]}
            flat[key] = key
            for alias in value:
                flat[alias] = key
        elif isinstance(value, str):
            # Flat format: {alias: canonical}, already inverted
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
        paths._migrate_legacy_paths()
        self._data = {**DEFAULT_CONFIG, **data}
        self._config_dir = config_dir
        self._ext_cache: dict[str, dict] = {}
        self._load_journal: list[tuple] = []

    def log_load_summary(self) -> None:
        """Replay buffered load-time events through the logger.

        Call once after setup_logging() so deferred messages reach handlers.
        """
        for entry in self._load_journal:
            logger.debug(entry[0], *entry[1:])
        self._load_journal.clear()

    def _external_config_candidates(self, filename: str) -> list[Path]:
        """Return the candidate paths the loader checks, in priority order.

        Order:
          1. ``self._config_dir / filename`` (typically the library-local
             ``.cratedigger/`` dir).
          2. ``paths.data_dir() / filename`` (the visible user data dir, e.g.
             ``Documents/CrateDigger/`` on Windows or ``~/CrateDigger/`` on
             Linux).
        """
        candidates: list[Path] = []
        if self._config_dir:
            candidates.append(self._config_dir / filename)
        candidates.append(paths.data_dir() / filename)
        return candidates

    def _load_external_config(self, filename: str, defaults: dict) -> dict:
        """Load a curated JSON data file from library override or user data dir.

        Curated data files (places.json, artists.json, artist_mbids.json)
        stay JSON on purpose; only ``config.toml`` switched to TOML.
        """
        if filename in self._ext_cache:
            return self._ext_cache[filename]

        candidates = self._external_config_candidates(filename)

        logger.debug("%s candidates: %s", filename, [str(p) for p in candidates])

        for path in candidates:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    logger.debug("Loaded %s from %s", filename, path)
                    self._ext_cache[filename] = data
                    return data
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Skipped %s: %s", path, e)

        logger.debug("%s not found in any candidate directory", filename)
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
    def place_aliases(self) -> dict[str, str]:
        places = self.place_config
        raw: dict[str, list[str]] = {}
        for canon, pc in places.items():
            if canon.startswith("_") or not isinstance(pc, dict):
                continue
            raw[canon] = list(pc.get("aliases", []))
            # Per-edition aliases also resolve to the canonical place
            for ed_conf in pc.get("editions", {}).values():
                for alias in ed_conf.get("aliases", []):
                    raw.setdefault(canon, []).append(alias)
        overlay = self._data.get("place_aliases") or self._data.get("festival_aliases")
        if overlay:
            raw = {**raw, **overlay}
        return _invert_alias_map(raw)

    @property
    def place_config(self) -> dict:
        raw = self._load_external_config("places.json", {})
        defaults = {k: v for k, v in raw.items()
                    if not k.startswith("_") and isinstance(v, dict)}
        overlay = self._data.get("place_config") or self._data.get("festival_config")
        if overlay:
            return {**defaults, **overlay}
        return defaults

    @property
    def all_known_editions(self) -> set[str]:
        """Collect all editions from every place config entry."""
        editions = set()
        for pc in self.place_config.values():
            editions.update(pc.get("editions", {}).keys())
        return editions

    def resolve_place_with_edition(self, name: str) -> tuple[str, str]:
        """Resolve alias and extract edition from the name if applicable.

        Returns (canonical_place, edition).
        "Dreamstate SoCal" -> ("Dreamstate", "SoCal")
        "Tomorrowland Winter" -> ("Tomorrowland", "Winter")
        "TML" -> ("Tomorrowland", "")
        """
        canonical = self.resolve_place_alias(name)

        # Alias resolved to something different: check for edition suffix
        if canonical != name:
            pc = self.place_config.get(canonical, {})
            # Check per-edition aliases
            for ed_name, ed_conf in pc.get("editions", {}).items():
                if name in ed_conf.get("aliases", []):
                    return canonical, ed_name
            # Check if suffix matches an edition name
            suffix = name[len(canonical):].strip() if name.lower().startswith(canonical.lower()) else ""
            if suffix:
                for ed_name in pc.get("editions", {}):
                    if ed_name.lower() == suffix.lower():
                        return canonical, ed_name
            return canonical, ""

        # No alias match. Try canonical + edition decomposition.
        for place_name, pc in self.place_config.items():
            for ed_name in pc.get("editions", {}):
                if f"{place_name} {ed_name}".lower() == name.lower():
                    return place_name, ed_name

        # Try alias prefixes (handles "Ultra Europe" via alias "Ultra")
        for alias, canon in self.place_aliases.items():
            pc = self.place_config.get(canon, {})
            for ed_name in pc.get("editions", {}):
                if f"{alias} {ed_name}".lower() == name.lower():
                    return canon, ed_name

        return name, ""

    @property
    def poster_settings(self) -> dict:
        defaults = DEFAULT_CONFIG.get("poster_settings", {})
        overrides = self._data.get("poster_settings", {})
        merged = {**defaults, **overrides}
        if (
            "festival_background_priority" in overrides
            and "place_background_priority" not in overrides
        ):
            _log_deprecated_once(
                "poster_settings.festival_background_priority",
                "poster_settings.festival_background_priority is deprecated, "
                "use poster_settings.place_background_priority instead. "
                "Support for festival_background_priority will be removed in 1.0.0.",
            )
            merged["place_background_priority"] = overrides["festival_background_priority"]
        return merged

    @property
    def skip_patterns(self) -> list[str]:
        return self._data.get("skip_patterns", [])

    @property
    def fallback_values(self) -> dict:
        defaults = DEFAULT_CONFIG.get("fallback_values", {})
        overrides = self._data.get("fallback_values", {})
        merged = {**defaults, **overrides}
        if (
            "unknown_festival" in overrides
            and "unknown_place" not in overrides
        ):
            _log_deprecated_once(
                "fallback_values.unknown_festival",
                "fallback_values.unknown_festival is deprecated, "
                "use fallback_values.unknown_place instead. "
                "Support for unknown_festival will be removed in 1.0.0.",
            )
            merged["unknown_place"] = overrides["unknown_festival"]
        return merged

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
        """Return (email, password); env vars override config."""
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
    def known_places(self) -> set[str]:
        """All place names the system can recognize."""
        names = set(self.place_aliases.keys())
        names.update(self.place_aliases.values())
        for place_name, pc in self.place_config.items():
            for ed_name, ed_conf in pc.get("editions", {}).items():
                names.add(f"{place_name} {ed_name}")
                for alias in ed_conf.get("aliases", []):
                    names.add(alias)
        return names

    def resolve_place_alias(self, name: str) -> str:
        """Map a place name/abbreviation to its canonical form."""
        # Try exact match first, then case-insensitive
        if name in self.place_aliases:
            resolved = self.place_aliases[name]
            if resolved != name:
                logger.debug("Place alias: '%s' -> '%s'", name, resolved)
            return resolved
        resolved = _ci_lookup(self.place_aliases, name) or name
        if resolved != name:
            logger.debug("Place alias (case-insensitive): '%s' -> '%s'", name, resolved)
        return resolved

    def resolve_place_for_media(self, mf) -> tuple[str, str]:
        """Return (canonical_name, place_kind) for the routing chain.

        Chain: festival -> venue -> location -> artist.
        place_kind values: "festival" | "venue" | "location" | "artist".
        Empty (name, kind) tuple indicates nothing routable.

        Whitespace-only fields are treated as empty so a malformed scrape
        like "   " falls through to the next chain position rather than
        producing a folder named after whitespace.
        """
        festival = mf.festival.strip()
        if festival:
            return (festival, "festival")
        venue = mf.venue.strip()
        if venue:
            return (venue, "venue")
        location = mf.location.strip()
        if location:
            canonical = self.resolve_place_alias(location)
            return (canonical, "location")
        artist = mf.artist.strip()
        if artist:
            return (artist, "artist")
        return ("", "")

    @cached_property
    def artist_aliases(self) -> dict[str, str]:
        """Combined alias map: DJ-cache derived first, manual config overrides on top.

        Cached for the lifetime of this Config instance: DjCache is read from
        disk once on first access. If dj_cache.json is updated mid-run by a
        concurrent process, this Config keeps its snapshot, which is acceptable
        because each CLI invocation builds a fresh Config.
        """
        raw = self._load_external_config("artists.json", {}).get("aliases", {})
        if "artist_aliases" in self._data:
            raw = {**raw, **self._data["artist_aliases"]}
        flat = _invert_alias_map(raw)
        try:
            from festival_organizer.tracklists.dj_cache import DjCache
            dj_aliases = DjCache().derive_artist_aliases()
        except (ImportError, OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("DjCache alias load skipped: %s", e)
            dj_aliases = {}
        return {**dj_aliases, **flat}

    @cached_property
    def artist_groups(self) -> set[str]:
        """Combined group set: manual config + external + DJ-cache derived.

        Same caching semantics as artist_aliases: DjCache is read once per
        Config instance.
        """
        if "artist_groups" in self._data:
            groups = {g.lower() for g in self._data["artist_groups"]}
        else:
            groups = set()
        ext_groups = self._load_external_config("artists.json", {}).get("groups", [])
        groups.update(g.lower() for g in ext_groups)
        try:
            from festival_organizer.tracklists.dj_cache import DjCache
            groups.update(DjCache().derive_artist_groups())
        except (ImportError, OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("DjCache group load skipped: %s", e)
        return groups

    def resolve_artist(self, name: str) -> str:
        """Resolve artist alias, then for B2Bs not in groups return first artist."""
        original = name
        # 1. Resolve alias (exact, case-insensitive, then diacritics-insensitive)
        aliased = False
        if name in self.artist_aliases:
            name = self.artist_aliases[name]
            aliased = True
        else:
            resolved = _ci_lookup(self.artist_aliases, name)
            if resolved is not None:
                name = resolved
                aliased = True
            else:
                stripped_map = {strip_diacritics(k).lower(): v for k, v in self.artist_aliases.items()}
                resolved = stripped_map.get(strip_diacritics(name).lower())
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

    def get_place_display(self, canonical_place: str, edition: str) -> str:
        """Get display name for a place, optionally including edition."""
        pc = self.place_config.get(canonical_place, {})
        if edition and edition in pc.get("editions", {}):
            return f"{canonical_place} {edition}"
        return canonical_place

    _LEGACY_LAYOUT_ALIASES = {
        "festival_flat": "place_flat",
        "festival_nested": "place_nested",
    }

    def _resolve_layout_name(self, layout: str) -> str:
        """Map deprecated layout names to their canonical ``place_*`` form.

        A user-defined override in ``self.layouts`` for the deprecated name
        wins (with a deprecation warning); otherwise the name is rewritten to
        the modern equivalent.
        """
        if layout not in self._LEGACY_LAYOUT_ALIASES:
            return layout
        canonical = self._LEGACY_LAYOUT_ALIASES[layout]
        _log_deprecated_once(
            f"layout.{layout}",
            f"Layout name '{layout}' is deprecated, use '{canonical}' instead. "
            f"Support for '{layout}' will be removed in 1.0.0.",
        )
        if layout in self.layouts:
            return layout
        return canonical

    def get_layout_template(self, content_type: str, layout_name: str | None = None) -> str:
        """Get the folder layout template for a content type."""
        layout = self._resolve_layout_name(layout_name or self.default_layout)
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
        """Return fanart.tv project API key; env var override + config fallback."""
        import os
        return os.environ.get("FANART_PROJECT_API_KEY") or self.fanart_settings.get("project_api_key", "")

    @property
    def fanart_personal_api_key(self) -> str:
        """Return fanart.tv personal API key; env var override + config fallback."""
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

    @property
    def cache_ttl(self) -> dict:
        return self._data.get("cache_ttl", {})

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
    user_config_file: Path | None = None,
    library_config_dir: Path | None = None,
) -> Config:
    """Load config with two-layer merge: built-in defaults < user TOML < library TOML.

    - ``user_config_file`` defaults to ``paths.config_file()`` (the visible
      ``config.toml`` in the user data dir, e.g.
      ``Documents/CrateDigger/config.toml`` on Windows or
      ``~/CrateDigger/config.toml`` on Linux).
    - ``library_config_dir`` is typically ``{library}/.cratedigger/``; its
      ``config.toml`` overrides user values.
    - ``config_path`` is retained for explicit-file callers (tests,
      ``--config`` CLI flag) and, when set, overrides the user/library
      lookup entirely: only that file is merged on top of defaults.
    """
    data = deepcopy(DEFAULT_CONFIG)

    journal: list[tuple] = []

    def _merge_toml(path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            with open(path, "rb") as f:
                layer = tomllib.load(f)
            _deep_merge(data, layer)
            return True
        except (tomllib.TOMLDecodeError, OSError) as e:
            logger.warning("Could not read %s: %s", path, e)
            return False

    if config_path is not None:
        loaded = _merge_toml(config_path)
        _migrate_layout_names(data)
        cfg = Config(data, config_dir=config_path.parent)
        cfg._load_journal.append(
            ("Config: %s -> %s", str(config_path), "loaded" if loaded else "not found")
        )
        return cfg

    user_file = user_config_file if user_config_file is not None else paths.config_file()
    user_loaded = _merge_toml(user_file)
    journal.append(
        ("Config: %s -> %s", str(user_file), "loaded" if user_loaded else "not found")
    )

    if library_config_dir is not None:
        legacy_json = library_config_dir / "config.json"
        if legacy_json.is_file():
            logger.warning(
                "Legacy library config detected at %s. "
                "This file is no longer read. Copy its default_layout value "
                "into %s (same directory) or delete it.",
                legacy_json,
                library_config_dir / "config.toml",
            )
        lib_toml = library_config_dir / "config.toml"
        lib_loaded = _merge_toml(lib_toml)
        journal.append(
            ("Config: %s -> %s", str(lib_toml), "loaded" if lib_loaded else "not found")
        )

    _migrate_layout_names(data)
    cfg = Config(data, config_dir=library_config_dir or user_file.parent)
    cfg._load_journal = journal
    return cfg


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
