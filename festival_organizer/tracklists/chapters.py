"""Chapter XML generation, extraction, comparison, and embedding.

Handles Matroska chapter/tag XML for MKV files via mkvextract/mkvpropedit.
"""
import logging
import os
import random
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

from festival_organizer import metadata
from festival_organizer.embed_tags import xml_escape
from festival_organizer.mkv_tags import extract_all_tags, write_merged_tags


@dataclass
class Chapter:
    """A single chapter marker."""
    timestamp: str   # "HH:MM:SS.mmm"
    title: str
    language: str = "eng"


def normalize_timestamp(time_str: str) -> str:
    """Normalize a timestamp to HH:MM:SS.mmm format.

    Handles: mm:ss, m:ss, hh:mm:ss, hh:mm:ss.mmm, mm:ss.s
    """
    time_str = time_str.strip()
    millis = "000"

    # Extract milliseconds if present
    if "." in time_str:
        parts = time_str.rsplit(".", 1)
        time_str = parts[0]
        millis = parts[1].ljust(3, "0")[:3]

    segments = time_str.split(":")

    if len(segments) == 2:
        # mm:ss
        return f"00:{int(segments[0]):02d}:{int(segments[1]):02d}.{millis}"
    elif len(segments) == 3:
        # hh:mm:ss
        return f"{int(segments[0]):02d}:{int(segments[1]):02d}:{int(segments[2]):02d}.{millis}"
    else:
        raise ValueError(f"Invalid timestamp format: {time_str}")


def parse_tracklist_lines(lines: list[str], language: str = "eng") -> list[Chapter]:
    """Parse tracklist export lines into Chapter objects.

    Expected format: "[mm:ss] Track Title" or "[hh:mm:ss] Track Title"

    Raises ValueError if lines contain numbered tracks but no timestamps
    (indicates tracklist exists but community hasn't added timestamps yet).
    """
    chapters = []
    has_numbered_tracks = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for timestamp pattern: [mm:ss] or [hh:mm:ss]
        match = re.match(r"^\s*\[([0-9:.]+)\]\s*(.+?)\s*$", line)
        if match:
            timestamp = normalize_timestamp(match.group(1))
            title = match.group(2)
            chapters.append(Chapter(timestamp=timestamp, title=title, language=language))
        elif re.match(r"^\s*\d+\.\s+", line):
            has_numbered_tracks = True

    if not chapters and has_numbered_tracks:
        raise ValueError("Tracklist has no timestamps yet (tracks are numbered but no time markers)")

    return chapters


def build_chapter_xml(chapters: list[Chapter]) -> str:
    """Generate Matroska chapter XML string."""
    root = ET.Element("Chapters")
    edition = ET.SubElement(root, "EditionEntry")

    for ch in chapters:
        atom = ET.SubElement(edition, "ChapterAtom")
        uid = ET.SubElement(atom, "ChapterUID")
        uid.text = str(random.getrandbits(64))

        time_start = ET.SubElement(atom, "ChapterTimeStart")
        time_start.text = ch.timestamp

        display = ET.SubElement(atom, "ChapterDisplay")
        ch_string = ET.SubElement(display, "ChapterString")
        ch_string.text = ch.title
        ch_lang = ET.SubElement(display, "ChapterLanguage")
        ch_lang.text = ch.language

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")



def extract_existing_chapters(filepath: Path) -> list[Chapter] | None:
    """Extract chapters from an MKV file via mkvextract.

    Returns list of Chapter objects, or None if no chapters or tool unavailable.
    """
    if not metadata.MKVEXTRACT_PATH:
        return None

    try:
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w") as f:
            xml_path = f.name

        result = subprocess.run(
            [metadata.MKVEXTRACT_PATH, str(filepath), "chapters", xml_path],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )

        if result.returncode != 0 or not os.path.exists(xml_path):
            return None

        # Check if file has content
        content = Path(xml_path).read_text(encoding="utf-8").strip()
        if not content:
            return None

        tree = ET.parse(xml_path)
        root = tree.getroot()

        chapters = []
        for atom in root.iter("ChapterAtom"):
            time_elem = atom.find("ChapterTimeStart")
            display = atom.find("ChapterDisplay")
            if time_elem is not None and display is not None:
                title_elem = display.find("ChapterString")
                lang_elem = display.find("ChapterLanguage")
                timestamp = time_elem.text or ""
                # Normalize nanosecond timestamps to milliseconds
                if len(timestamp) > 12:
                    timestamp = timestamp[:12]
                title = title_elem.text if title_elem is not None else ""
                language = lang_elem.text if lang_elem is not None else "eng"
                chapters.append(Chapter(timestamp=timestamp, title=title, language=language))

        return chapters if chapters else None

    except (OSError, subprocess.SubprocessError, ET.ParseError) as e:
        logger.debug("Chapter extraction failed for %s: %s", filepath, e)
        return None
    finally:
        try:
            os.unlink(xml_path)
        except Exception:
            pass


def extract_stored_tracklist_info(filepath: Path) -> dict | None:
    """Extract stored 1001TL tags from MKV file.

    Returns dict with all 1001TL tag values, or None if no tags found.
    """
    root = extract_all_tags(filepath)
    if root is None:
        return None

    tag_map = {
        "1001TRACKLISTS_URL": "url",
        "1001TRACKLISTS_TITLE": "title",
        "1001TRACKLISTS_ID": "id",
        "1001TRACKLISTS_DATE": "date",
        "1001TRACKLISTS_GENRES": "genres",
        "1001TRACKLISTS_EVENT_ARTWORK": "event_artwork",
        "1001TRACKLISTS_DJ_ARTWORK": "dj_artwork",
    }
    result = {v: "" for v in tag_map.values()}

    for tag in root.iter("Tag"):
        targets = tag.find("Targets")
        if targets is not None:
            ttv = targets.find("TargetTypeValue")
            if ttv is not None and int(ttv.text or "0") < 70:
                continue

        for simple in tag.iter("Simple"):
            name = simple.find("Name")
            string = simple.find("String")
            if name is not None and string is not None and name.text in tag_map:
                result[tag_map[name.text]] = string.text or ""

    if any(result.values()):
        return result
    return None


def chapters_are_identical(existing: list[Chapter] | None, new: list[Chapter]) -> bool:
    """Compare two chapter lists for equality.

    Compares count, timestamps (to mm:ss precision), and titles.
    """
    if existing is None:
        return False
    if len(existing) != len(new):
        return False

    for e, n in zip(existing, new):
        # Compare timestamps to mm:ss precision (ignore milliseconds)
        e_short = e.timestamp[:8] if len(e.timestamp) >= 8 else e.timestamp
        n_short = n.timestamp[:8] if len(n.timestamp) >= 8 else n.timestamp
        if e_short != n_short:
            return False
        if e.title != n.title:
            return False

    return True


def embed_chapters(
    filepath: Path,
    chapters: list[Chapter],
    tracklist_url: str | None = None,
    tracklist_title: str | None = None,
    tracklist_id: str | None = None,
    tracklist_date: str | None = None,
    genres: list[str] | None = None,
    event_artwork_url: str | None = None,
    dj_artwork_url: str | None = None,
) -> bool:
    """Write chapters and optional tags to an MKV file.

    Chapters: written via mkvpropedit --chapters (replaces chapters only, safe).
    Tags: written via extract-merge-write to preserve existing tags.

    Returns True on success, False on failure.
    """
    if not metadata.MKVPROPEDIT_PATH:
        return False

    if not filepath.exists() or filepath.suffix.lower() not in (".mkv", ".webm"):
        return False

    chapter_file = None

    try:
        # Write chapters via mkvpropedit --chapters (only if chapters provided)
        if chapters:
            chapter_xml = build_chapter_xml(chapters)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
                f.write(chapter_xml)
                chapter_file = f.name

            result = subprocess.run(
                [metadata.MKVPROPEDIT_PATH, str(filepath), "--chapters", chapter_file],
                capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )

            if result.returncode != 0:
                return False

        # Write 1001TL tags via merge (preserves ARTIST/TITLE/DATE etc.)
        if tracklist_url:
            tags: dict[str, str] = {"1001TRACKLISTS_URL": tracklist_url}
            if tracklist_title:
                tags["1001TRACKLISTS_TITLE"] = tracklist_title
            if tracklist_id:
                tags["1001TRACKLISTS_ID"] = tracklist_id
            if tracklist_date:
                tags["1001TRACKLISTS_DATE"] = tracklist_date
            if genres:
                tags["1001TRACKLISTS_GENRES"] = "|".join(genres)
            if event_artwork_url:
                tags["1001TRACKLISTS_EVENT_ARTWORK"] = event_artwork_url
            if dj_artwork_url:
                tags["1001TRACKLISTS_DJ_ARTWORK"] = dj_artwork_url
            return write_merged_tags(filepath, {70: tags})

        return True

    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Chapter embedding failed for %s: %s", filepath, e)
        return False
    finally:
        if chapter_file:
            try:
                os.unlink(chapter_file)
            except Exception:
                pass
