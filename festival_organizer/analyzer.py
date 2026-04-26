"""Analyzer: combines metadata and parsing into a single MediaFile.

Logging:
    Logger: 'festival_organizer.analyzer'
    Key events:
        - analyze.result (INFO): Final parsed artist, festival, year, and metadata source
    See docs/logging.md for full guidelines.
"""
import logging
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.metadata import extract_metadata
from festival_organizer.models import MediaFile
from festival_organizer.normalization import normalise_name
from festival_organizer.parsers import (
    parse_filename,
    parse_parent_dirs,
)

logger = logging.getLogger(__name__)

# Extensions
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m2ts", ".ts"}


def analyse_file(filepath: Path, root: Path, config: Config) -> MediaFile:
    """Analyse a single file, combining all metadata sources.

    Priority (highest first):
    1. 1001Tracklists dedicated tags (artists, festival, stage, venue, date)
    2. Embedded metadata tags (ARTIST, DATE, Title)
    3. Filename parsing
    4. Parent directory names
    """
    meta = extract_metadata(filepath)
    filename_info = parse_filename(filepath, config)
    parent_info = parse_parent_dirs(filepath, root, config)

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
        "location": "",
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

    # Layer 4: 1001TL dedicated tags (authoritative when present)
    metadata_source = "filename"
    tracklists_artists_raw = meta.get("tracklists_artists", "")
    artists_list = [a.strip() for a in tracklists_artists_raw.split("|") if a.strip()] if tracklists_artists_raw else []
    if artists_list:
        info["artist"] = artists_list[0]
        metadata_source = "1001tracklists"

    # 1001TL date tag overwrites date/year
    if meta.get("tracklists_date"):
        tl_date = meta["tracklists_date"]
        if len(tl_date) >= 4:
            info["year"] = tl_date[:4]
        if len(tl_date) == 10:
            info["date"] = tl_date

    if meta.get("tracklists_stage"):
        info["stage"] = meta["tracklists_stage"]
    if meta.get("tracklists_venue"):
        info["venue"] = meta["tracklists_venue"]
    if meta.get("tracklists_location"):
        info["location"] = meta["tracklists_location"]
    # Layer 5: Direct 1001TL festival tag (written by chapters command from
    # source cache). Authoritative for festival + edition.
    if meta.get("tracklists_festival"):
        fest, ed = config.resolve_festival_with_edition(
            meta["tracklists_festival"]
        )
        info["festival"] = fest
        if ed:
            info["edition"] = ed
        metadata_source = "1001tracklists"
    if not artists_list and not meta.get("tracklists_festival"):
        if embedded:
            metadata_source = "metadata+filename"

    # Build display_artist
    if artists_list:
        if len(artists_list) > 1:
            display_artist = " & ".join(artists_list)
        else:
            display_artist = artists_list[0]
            # Enrich with parenthetical member info from 1001TL title
            # e.g. "Everything Always" -> "Everything Always (Dom Dolla & John Summit)"
            tracklists_title = meta.get("tracklists_title", "")
            if tracklists_title and " @ " in tracklists_title:
                title_artist = tracklists_title.split(" @ ")[0].strip()
                if (title_artist.lower().startswith(display_artist.lower())
                        and len(title_artist) > len(display_artist)):
                    display_artist = title_artist
    else:
        # Fallback: same priority as artist but skip ARTIST tag
        da = ""
        if parent_info.get("artist"):
            da = parent_info["artist"]
        if filename_info.get("artist"):
            da = filename_info["artist"]
        display_artist = normalise_name(da)
        # Title-case if the source was ALL-CAPS (e.g. YouTube titles)
        if display_artist and display_artist == display_artist.upper():
            display_artist = display_artist.title()

    # Normalise
    artist = normalise_name(info.get("artist", ""))
    if artist:
        artist = config.resolve_artist(artist)

    # Build resolved artists list from 1001TL pipe-separated tag
    resolved_artists: list[str] = []
    if artists_list:
        for a in artists_list:
            resolved = config.resolve_artist(normalise_name(a))
            resolved_artists.append(resolved if resolved else normalise_name(a))
    # Align display_artist with the config-resolved canonical form
    # when it refers to the same single artist (preserves B2B names)
    if display_artist and normalise_name(display_artist).lower() == normalise_name(artist).lower():
        display_artist = artist  # Use config-resolved canonical form
    festival = info.get("festival", "")
    # Resolve festival alias
    if festival:
        festival = config.resolve_festival_alias(festival)

    # Clear festival when it's a parser artifact. When 1001TL metadata is
    # present but has no festival tag, the filename parser's guess is unreliable
    # (e.g., standalone venue sets where YYYY-Part2-Part3 misparses). Trust the
    # 1001TL signal: if it doesn't name a festival, there probably isn't one.
    # Preserve only festivals that are independently recognized (known_festivals).
    if festival and festival not in config.known_festivals:
        if artists_list and not meta.get("tracklists_festival"):
            festival = ""
        elif artist and festival.lower() == artist.lower():
            festival = ""

    ext = filepath.suffix.lower()
    file_type = "video" if ext in VIDEO_EXTS else "audio"

    logger.info("Parsed: artist=%s, festival=%s, year=%s, source=%s",
                artist, festival, info.get("year", ""), metadata_source)

    # Identified files (anything with 1001TL tags) get their canonical fields
    # from the embedded tags, not from filename parsing. set_title and title are
    # filename-only salvage fields: keeping them for identified files breaks
    # render idempotency because the filename shape mutates between runs while
    # the tags stay put. Gate them on the identified-ness signal so renders
    # converge after one organize.
    identified = bool(meta.get("tracklists_url") or meta.get("tracklists_title"))
    set_title = "" if identified else normalise_name(info.get("set_title", ""))
    title_field = "" if identified else normalise_name(info.get("title", ""))

    return MediaFile(
        source_path=filepath,
        artist=artist,
        display_artist=display_artist,
        artists=resolved_artists,
        festival=festival,
        festival_full=meta.get("tracklists_festival", ""),
        year=info.get("year", "").strip(),
        date=info.get("date", ""),
        set_title=set_title,
        title=title_field,
        stage=info.get("stage", ""),
        venue=config.resolve_place_alias(info["venue"]) if info.get("venue") else "",
        venue_full=info.get("venue", ""),
        location=info.get("location", ""),
        edition=info.get("edition", ""),
        youtube_id=info.get("youtube_id", ""),
        tracklists_url=meta.get("tracklists_url", ""),
        tracklists_title=meta.get("tracklists_title", ""),
        genres=[g.strip() for g in meta.get("tracklists_genres", "").split("|") if g.strip()] if meta.get("tracklists_genres") else [],
        dj_artwork_url=meta.get("tracklists_dj_artwork", ""),
        country=meta.get("tracklists_country", ""),
        source_type=meta.get("tracklists_source_type", ""),
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
