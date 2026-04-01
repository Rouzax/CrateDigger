"""Analyzer: combines metadata and parsing into a single MediaFile.

Logging:
    Logger: 'festival_organizer.analyzer'
    Key events:
        - analyze.result (INFO): Final parsed artist, festival, year, and metadata source
    See docs/logging.md for full guidelines.
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

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
        "edition": "",
        "youtube_id": "",
        "venue": "",
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
    # Direct tag values (artist_tag, date_tag) overwrite lower layers
    for key in ["artist", "year", "date"]:
        if embedded.get(key):
            info[key] = embedded[key]
    # Parsed title info only fills missing
    _merge_missing(info, embedded)

    # Layer 4 (highest priority): 1001Tracklists overwrites
    metadata_source = "filename"
    if tracklists_info:
        for key in ["artist", "festival", "date", "year", "stage", "edition"]:
            if tracklists_info.get(key):
                info[key] = tracklists_info[key]
        metadata_source = "1001tracklists"
        # Clear set_title if redundant with 1001TL stage (e.g. "RESISTANCE
        # MEGASTRUCTURE" from filename leftover when stage is already set)
        st = normalise_name(info.get("set_title", "")).lower()
        stage = info.get("stage", "").lower()
        if st and stage and (st in stage or stage in st):
            info["set_title"] = ""
    if meta.get("tracklists_stage"):
        info["stage"] = meta["tracklists_stage"]
    if meta.get("tracklists_venue"):
        info["venue"] = meta["tracklists_venue"]
    # Layer 5: Direct 1001TL festival tag (written by chapters command from
    # source cache). Authoritative for festival + location.
    if meta.get("tracklists_festival"):
        fest, ed = config.resolve_festival_with_edition(
            meta["tracklists_festival"]
        )
        info["festival"] = fest
        if ed:
            info["edition"] = ed
        if not tracklists_info:
            metadata_source = "1001tracklists"
    if embedded and not tracklists_info and not meta.get("tracklists_festival"):
        metadata_source = "metadata+filename"

    # Build display_artist: same priority but skip ARTIST tag (Layer 3 direct)
    # This preserves full B2B/collab names in filenames and TITLE tags,
    # while ARTIST tag (written by embed_tags) holds primary-only for Plex.
    da = ""
    # Layer 1: parent dir
    if parent_info.get("artist"):
        da = parent_info["artist"]
    # Layer 2: filename parse (overwrites)
    if filename_info.get("artist"):
        da = filename_info["artist"]
    # Layer 3: SKIP the ARTIST tag — intentionally omitted
    # Layer 4: 1001TL (highest priority, overwrites)
    if tracklists_info and tracklists_info.get("artist"):
        da = tracklists_info["artist"]
    display_artist = normalise_name(da)
    # Title-case if the source was ALL-CAPS (e.g. YouTube titles)
    if display_artist and display_artist == display_artist.upper():
        display_artist = display_artist.title()

    # Normalise
    artist = normalise_name(info.get("artist", ""))
    if artist:
        artist = config.resolve_artist(artist)
    festival = info.get("festival", "")
    # Resolve festival alias
    if festival:
        festival = config.resolve_festival_alias(festival)

    ext = filepath.suffix.lower()
    file_type = "video" if ext in VIDEO_EXTS else "audio"

    logger.info("Parsed: artist=%s, festival=%s, year=%s, source=%s",
                artist, festival, info.get("year", ""), metadata_source)

    return MediaFile(
        source_path=filepath,
        artist=artist,
        display_artist=display_artist,
        festival=festival,
        year=info.get("year", "").strip(),
        date=info.get("date", ""),
        set_title=normalise_name(info.get("set_title", "")),
        title=normalise_name(info.get("title", "")),
        stage=info.get("stage", ""),
        venue=info.get("venue", ""),
        edition=info.get("edition", ""),
        youtube_id=info.get("youtube_id", ""),
        tracklists_url=meta.get("tracklists_url", ""),
        tracklists_title=meta.get("tracklists_title", ""),
        genres=[g.strip() for g in meta.get("tracklists_genres", "").split("|") if g.strip()] if meta.get("tracklists_genres") else [],
        dj_artwork_url=meta.get("tracklists_dj_artwork", ""),
        mbid=meta.get("mbid", ""),
        fanart_url=meta.get("fanart_url", ""),
        clearlogo_url=meta.get("clearlogo_url", ""),
        enriched_at=meta.get("enriched_at", ""),
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
