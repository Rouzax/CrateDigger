"""Kodi musicvideo NFO XML generation."""
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from xml.dom import minidom

from festival_organizer.config import Config
from festival_organizer.models import MediaFile, build_display_title


def generate_nfo(media_file: MediaFile, video_path: Path, config: Config,
                 dj_cache=None) -> Path:
    """Generate a Kodi-compatible musicvideo NFO file alongside a video file.

    Follows the Kodi v20+ spec: https://kodi.wiki/view/NFO_files/Music_videos
    Returns the path to the generated .nfo file.
    """
    nfo_path = video_path.with_suffix(".nfo")
    mf = media_file
    nfo_settings = config.nfo_settings

    root = ET.Element("musicvideo")

    # Title — must stand alone in Kodi browse views (only label shown)
    title = build_display_title(mf, config)
    _add(root, "title", title)

    # Artist(s): one element per artist from 1001TL; fallback to primary
    if mf.artists:
        for a in mf.artists:
            _add(root, "artist", a)
    else:
        _add(root, "artist", mf.artist or "Unknown Artist")

    # Album — grouping key: festival + year
    if mf.content_type == "festival_set":
        album_parts = []
        festival_display = mf.festival
        if mf.edition:
            festival_display = config.get_festival_display(mf.festival, mf.edition)
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

    # Genre — use extracted genres when available, fall back to static config
    if mf.genres:
        for genre in mf.genres:
            _add(root, "genre", genre)
    elif mf.content_type == "festival_set":
        _add(root, "genre", nfo_settings.get("genre_festival", "Electronic"))
    else:
        _add(root, "genre", nfo_settings.get("genre_concert", "Live"))

    # Tags: for Kodi smart playlists (deduplicated, case-insensitive)
    existing_tags: set[str] = set()
    if mf.content_type:
        _add(root, "tag", mf.content_type)
        existing_tags.add(mf.content_type.lower())
    if mf.festival:
        _add(root, "tag", mf.festival)
        existing_tags.add(mf.festival.lower())
    if mf.edition:
        _add(root, "tag", mf.edition)
        existing_tags.add(mf.edition.lower())

    # Artist tags (deduplicated against existing tags)
    if mf.artists:
        group_members = dj_cache.derive_group_members() if dj_cache else {}
        for artist_name in mf.artists:
            if artist_name.lower() not in existing_tags:
                _add(root, "tag", artist_name)
                existing_tags.add(artist_name.lower())
            # Expand group members
            for member in group_members.get(artist_name, []):
                if member.lower() not in existing_tags:
                    _add(root, "tag", member)
                    existing_tags.add(member.lower())

    # Studio — stage name for sets, venue for concerts
    if mf.stage:
        _add(root, "studio", mf.stage)

    # Plot — rich description without 1001TL URL
    plot_parts = []
    if mf.stage:
        plot_parts.append(f"Stage: {mf.stage}")
    if mf.edition:
        plot_parts.append(f"Edition: {mf.edition}")
    if mf.set_title:
        plot_parts.append(f"Edition: {mf.set_title}")
    if plot_parts:
        _add(root, "plot", "\n".join(plot_parts))

    # Runtime (minutes)
    if mf.duration_seconds:
        runtime_min = int(mf.duration_seconds) // 60
        _add(root, "runtime", str(runtime_min))

    # Thumbnails — thumb, poster, and fanart references
    thumb = ET.SubElement(root, "thumb", aspect="thumb")
    thumb.text = f"{video_path.stem}-thumb.jpg"
    poster = ET.SubElement(root, "thumb", aspect="poster")
    poster.text = f"{video_path.stem}-poster.jpg"
    fanart_elem = ET.SubElement(root, "fanart")
    fanart_thumb = ET.SubElement(fanart_elem, "thumb")
    fanart_thumb.text = f"{video_path.stem}-fanart.jpg"

    # Date added
    _add(root, "dateadded", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

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
