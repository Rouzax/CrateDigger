"""Kodi musicvideo NFO XML generation."""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from xml.dom import minidom

from festival_organizer.config import Config
from festival_organizer.models import MediaFile, build_display_title

logger = logging.getLogger(__name__)


def generate_nfo_xml(
    media_file: MediaFile,
    video_path: Path,
    config: Config,
    dj_cache=None,
    dateadded: str | None = None,
) -> str:
    """Build a Kodi-compatible musicvideo NFO XML string.

    When *dateadded* is provided it is used verbatim; otherwise ``datetime.now()``
    is stamped.  Returns the pretty-printed XML without an XML declaration.
    """
    mf = media_file
    nfo_settings = config.nfo_settings

    root = ET.Element("musicvideo")

    title = build_display_title(mf, config)
    _add(root, "title", title)

    if mf.artists:
        for a in mf.artists:
            _add(root, "artist", a)
    else:
        _add(root, "artist", mf.artist or "Unknown Artist")

    if mf.content_type == "festival_set":
        # Route through the resolved place like build_display_title, so
        # venue- and location-routed sets (empty mf.festival) still get a
        # named album. The mf.festival fallback covers MediaFile instances
        # built without the analyzer's place resolution. Stage is the last
        # resort before a bare year, mirroring TrackSplit's album fallback.
        if mf.place_kind in ("festival", "venue", "location") and mf.place:
            place_name = config.get_place_display(mf.place, mf.edition)
        else:
            place_name = (
                config.get_place_display(mf.festival, mf.edition) if mf.festival else ""
            )
        base = place_name or mf.stage
        if base and mf.year and mf.year not in base:
            album = f"{base} {mf.year}"
        else:
            album = base or mf.year
    else:
        place_name = ""
        album = mf.title or mf.festival or ""
    if album:
        _add(root, "album", album)

    if mf.date:
        _add(root, "premiered", mf.date)
    elif mf.year:
        _add(root, "premiered", f"{mf.year}-01-01")

    if mf.genres:
        for genre in mf.genres:
            _add(root, "genre", genre)
    elif mf.content_type == "festival_set":
        _add(root, "genre", nfo_settings.get("genre_festival", "Electronic"))
    else:
        _add(root, "genre", nfo_settings.get("genre_concert", "Live"))

    existing_tags: set[str] = set()
    if mf.content_type:
        _add(root, "tag", mf.content_type)
        existing_tags.add(mf.content_type.lower())
    # Tag the resolved place (festival, venue, or location) so smart
    # playlists can find venue-routed sets too; raw name, edition is its
    # own tag below. Falls back to mf.festival for MediaFile instances
    # built without the analyzer's place resolution.
    place_tag = (
        mf.place
        if mf.place_kind in ("festival", "venue", "location") and mf.place
        else mf.festival
    )
    if place_tag:
        _add(root, "tag", place_tag)
        existing_tags.add(place_tag.lower())
    if mf.edition:
        _add(root, "tag", mf.edition)
        existing_tags.add(mf.edition.lower())
    # Combined "{place} {year}" tag, mirroring <album>. Kodi already reaches a
    # single edition via its Music Videos > Albums node, but Jellyfin exposes no
    # album browse for music videos and ORs multiple selected tags together, so
    # one pre-combined tag is the only way to select an edition in a single
    # click there. Uses the edition-qualified display name (like <album>), not
    # the raw place tag above, so "Dreamstate SoCal 2026" stays distinct from
    # the other Dreamstate editions that year.
    if mf.content_type == "festival_set" and place_name and mf.year:
        place_year = place_name if mf.year in place_name else f"{place_name} {mf.year}"
        if place_year.lower() not in existing_tags:
            _add(root, "tag", place_year)
            existing_tags.add(place_year.lower())

    if mf.artists:
        group_members = dj_cache.derive_group_members() if dj_cache else {}
        slugs = mf.artist_slugs if len(mf.artist_slugs) == len(mf.artists) else []
        for idx, artist_name in enumerate(mf.artists):
            if artist_name.lower() not in existing_tags:
                _add(root, "tag", artist_name)
                existing_tags.add(artist_name.lower())
            # derive_group_members() is keyed by group slug, so prefer the
            # file's album-artist slug; fall back to the name key for older
            # files with no slug tag.
            members = group_members.get(slugs[idx]) if slugs else None
            if members is None:
                members = group_members.get(artist_name, [])
            for member in members:
                if member.lower() not in existing_tags:
                    _add(root, "tag", member)
                    existing_tags.add(member.lower())

    if mf.stage:
        _add(root, "studio", mf.stage)

    plot_parts = []
    if mf.stage:
        plot_parts.append(f"Stage: {mf.stage}")
    if mf.edition:
        plot_parts.append(f"Edition: {mf.edition}")
    if mf.set_title:
        plot_parts.append(f"Edition: {mf.set_title}")
    if plot_parts:
        _add(root, "plot", "\n".join(plot_parts))

    if mf.duration_seconds:
        runtime_min = int(mf.duration_seconds) // 60
        _add(root, "runtime", str(runtime_min))

    thumb = ET.SubElement(root, "thumb", aspect="thumb")
    thumb.text = f"{video_path.stem}-thumb.jpg"
    poster = ET.SubElement(root, "thumb", aspect="poster")
    poster.text = f"{video_path.stem}-poster.jpg"
    fanart_elem = ET.SubElement(root, "fanart")
    fanart_thumb = ET.SubElement(fanart_elem, "thumb")
    fanart_thumb.text = f"{video_path.stem}-fanart.jpg"

    _add(root, "dateadded", dateadded or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    xml_str = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(
        indent="  "
    )
    lines = xml_str.split("\n")
    if lines[0].startswith("<?xml"):
        xml_str = "\n".join(lines[1:])

    return xml_str.strip() + "\n"


def generate_nfo(
    media_file: MediaFile,
    video_path: Path,
    config: Config,
    dj_cache=None,
    dateadded: str | None = None,
) -> Path:
    """Write a Kodi-compatible musicvideo NFO file alongside a video file.

    Delegates to ``generate_nfo_xml`` for the XML content, then writes to disk.
    Returns the path to the generated .nfo file.
    """
    nfo_path = video_path.with_suffix(".nfo")
    xml_str = generate_nfo_xml(
        media_file, video_path, config, dj_cache=dj_cache, dateadded=dateadded
    )
    try:
        nfo_path.write_text(xml_str, encoding="utf-8")
    except OSError as e:
        logger.warning('nfo.write: status=failed file=%s error="%s"', nfo_path, e)
        raise
    return nfo_path


def _add(parent: ET.Element, tag: str, text: str) -> ET.Element:
    """Add a child element with text content."""
    elem = ET.SubElement(parent, tag)
    elem.text = text
    return elem
