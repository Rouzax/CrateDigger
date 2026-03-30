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

    # Title — must stand alone in Kodi browse views (only label shown)
    if mf.content_type == "festival_set":
        artist = mf.display_artist or mf.artist or "Unknown Artist"
        if mf.stage:
            parts = [f"{artist} @ {mf.stage}"]
            if mf.festival:
                festival = mf.festival
                if mf.set_title:
                    festival = f"{festival} {mf.set_title}"
                parts.append(festival)
            title = ", ".join(parts)
        else:
            title = artist
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

    # Genre — use extracted genres when available, fall back to static config
    if mf.genres:
        for genre in mf.genres:
            _add(root, "genre", genre)
    elif mf.content_type == "festival_set":
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
