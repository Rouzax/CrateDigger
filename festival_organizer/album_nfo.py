"""Kodi album NFO generation for folder-level metadata."""
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

from festival_organizer.config import Config
from festival_organizer.models import MediaFile


def generate_album_nfo(
    folder_path: Path,
    media_files: list[MediaFile],
    config: Config,
    layout_name: str | None = None,
) -> Path:
    """Generate an album.nfo file for a folder containing grouped media files.

    Args:
        folder_path: The folder to write album.nfo into
        media_files: All MediaFile objects in this folder
        config: Configuration
        layout_name: Override layout name

    Returns:
        Path to the generated album.nfo file
    """
    nfo_path = folder_path / "album.nfo"
    layout = layout_name or config.default_layout

    # Derive album metadata from the files in this folder
    first = media_files[0] if media_files else None
    if not first:
        return nfo_path

    root = ET.Element("album")

    # Title depends on layout
    if layout == "festival_first":
        # album = festival + year
        festival = first.festival or ""
        if first.location:
            festival = config.get_festival_display(first.festival, first.location)
        title = f"{festival} {first.year}".strip()
    else:
        # artist_first: album = artist — festival year
        artists = sorted({mf.artist for mf in media_files if mf.artist})
        festival = first.festival or first.title or ""
        if first.location:
            festival = config.get_festival_display(first.festival, first.location)
        if len(artists) == 1:
            title = f"{artists[0]} \u2014 {festival} {first.year}".strip()
        else:
            title = f"{festival} {first.year}".strip()

    _add_element(root, "title", title)

    # Year
    years = sorted({mf.year for mf in media_files if mf.year})
    if years:
        _add_element(root, "year", years[0])

    # Genre — aggregate from all files, fall back to static config
    all_genres = []
    seen = set()
    for mf in media_files:
        for g in mf.genres:
            if g.lower() not in seen:
                seen.add(g.lower())
                all_genres.append(g)
    if all_genres:
        for genre in all_genres:
            _add_element(root, "genre", genre)
    else:
        content_types = {mf.content_type for mf in media_files}
        if "festival_set" in content_types:
            _add_element(root, "genre", config.nfo_settings.get("genre_festival", "Electronic"))
        else:
            _add_element(root, "genre", config.nfo_settings.get("genre_concert", "Live"))

    # Plot — list of artists in this folder
    artists = sorted({mf.artist for mf in media_files if mf.artist})
    plot_parts = []
    if first.location:
        plot_parts.append(f"Location: {first.location}")
    if artists:
        plot_parts.append(f"Artists: {', '.join(artists)}")
    plot_parts.append(f"{len(media_files)} file(s)")
    _add_element(root, "plot", "\n".join(plot_parts))

    # Write with pretty-printing
    xml_str = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
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
