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
