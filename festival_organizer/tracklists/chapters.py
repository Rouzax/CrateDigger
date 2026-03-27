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


def build_tags_xml(tracklist_url: str, tracklist_title: str = "") -> str:
    """Generate Matroska tags XML with 1001TL URL/title at TargetTypeValue=70 (COLLECTION)."""
    tags = []
    if tracklist_url:
        tags.append(f'    <Simple><Name>1001TRACKLISTS_URL</Name><String>{xml_escape(tracklist_url)}</String></Simple>')
    if tracklist_title:
        tags.append(f'    <Simple><Name>1001TRACKLISTS_TITLE</Name><String>{xml_escape(tracklist_title)}</String></Simple>')

    tags_str = "\n".join(tags)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Tags>
  <Tag>
    <Targets>
      <TargetTypeValue>70</TargetTypeValue>
    </Targets>
{tags_str}
  </Tag>
</Tags>
"""


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
    """Extract stored 1001TL URL/title from MKV tags via mkvextract.

    Returns {"url": str, "title": str} or None.
    """
    if not metadata.MKVEXTRACT_PATH:
        return None

    try:
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w") as f:
            xml_path = f.name

        result = subprocess.run(
            [metadata.MKVEXTRACT_PATH, str(filepath), "tags", xml_path],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )

        if result.returncode != 0:
            return None

        content = Path(xml_path).read_text(encoding="utf-8").strip()
        if not content:
            return None

        tree = ET.parse(xml_path)
        root = tree.getroot()

        url = ""
        title = ""

        for tag in root.iter("Tag"):
            # Check for global scope (TargetTypeValue >= 70 or no Targets)
            targets = tag.find("Targets")
            if targets is not None:
                ttv = targets.find("TargetTypeValue")
                if ttv is not None and int(ttv.text or "0") < 70:
                    continue

            for simple in tag.iter("Simple"):
                name = simple.find("Name")
                string = simple.find("String")
                if name is not None and string is not None:
                    if name.text == "1001TRACKLISTS_URL":
                        url = string.text or ""
                    elif name.text == "1001TRACKLISTS_TITLE":
                        title = string.text or ""

        if url or title:
            return {"url": url, "title": title}
        return None

    except (OSError, subprocess.SubprocessError, ET.ParseError, ValueError) as e:
        logger.debug("Stored tracklist extraction failed for %s: %s", filepath, e)
        return None
    finally:
        try:
            os.unlink(xml_path)
        except Exception:
            pass


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
) -> bool:
    """Write chapters and optional tags to an MKV file via mkvpropedit.

    Returns True on success, False on failure.
    """
    if not metadata.MKVPROPEDIT_PATH:
        return False

    if not filepath.exists() or filepath.suffix.lower() not in (".mkv", ".webm"):
        return False

    chapter_file = None
    tags_file = None

    try:
        # Write chapter XML
        chapter_xml = build_chapter_xml(chapters)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(chapter_xml)
            chapter_file = f.name

        cmd = [metadata.MKVPROPEDIT_PATH, str(filepath), "--chapters", chapter_file]

        # Optionally add tags
        if tracklist_url:
            tags_xml = build_tags_xml(tracklist_url, tracklist_title or "")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
                f.write(tags_xml)
                tags_file = f.name
            cmd.extend(["--tags", f"global:{tags_file}"])

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )

        return result.returncode == 0

    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Chapter embedding failed for %s: %s", filepath, e)
        return False
    finally:
        for f in [chapter_file, tags_file]:
            if f:
                try:
                    os.unlink(f)
                except Exception:
                    pass
