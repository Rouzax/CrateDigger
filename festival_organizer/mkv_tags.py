"""MKV tag extract-merge-write module.

Provides safe tag operations that extract existing tags, merge new ones in,
and write the combined result — preventing mkvpropedit's --tags global: from
destroying tags written by other modules.

Logging:
    Logger: 'festival_organizer.mkv_tags'
    Key events:
        - mkv_tags.extract_failed (WARNING): Tag extraction via mkvextract failed
        - mkv_tags.write_failed (WARNING): Tag writing via mkvpropedit failed
    See docs/logging.md for full guidelines.
"""
import logging
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from festival_organizer import metadata

logger = logging.getLogger(__name__)


def extract_all_tags(filepath: Path) -> ET.Element | None:
    """Extract all global tags from an MKV file.

    Runs mkvextract to pull out the tags XML, parses it, and returns
    the root <Tags> element. Returns None if extraction fails or there
    are no tags.

    Args:
        filepath: Path to the MKV file

    Returns:
        Root <Tags> Element, or None if no tags or extraction failed
    """
    if not metadata.MKVEXTRACT_PATH:
        return None

    if not filepath.exists():
        return None

    tag_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False, encoding="utf-8"
        ) as f:
            tag_file = f.name

        result = subprocess.run(
            [metadata.MKVEXTRACT_PATH, str(filepath), "tags", tag_file],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            logger.warning(
                "Tag extraction failed for %s: %s", filepath, result.stderr.strip()
            )
            return None

        # mkvextract writes an empty file when there are no tags
        content = Path(tag_file).read_text(encoding="utf-8").strip()
        if not content:
            return None

        return ET.fromstring(content)

    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("Tag extraction failed for %s: %s", filepath, e)
        return None
    except ET.ParseError as e:
        logger.warning("Tag XML parse failed for %s: %s", filepath, e)
        return None
    finally:
        if tag_file:
            try:
                os.unlink(tag_file)
            except Exception:
                pass


def merge_tags(
    existing: ET.Element | None, new_tags: dict[int, dict[str, str]]
) -> str:
    """Merge new tags into existing tag XML, organized by TargetTypeValue scope.

    For each TTV in new_tags:
    - If a Tag block exists at that TTV: update/add Simple elements by Name
      (new value wins if non-empty, empty values preserve existing)
    - If no block exists: create one
    - All other Tag blocks are preserved unchanged

    Args:
        existing: Root <Tags> Element from extract_all_tags, or None
        new_tags: Dict mapping TargetTypeValue -> {Name: String} pairs
            e.g. {50: {"ARTIST": "Tiesto"}, 70: {"URL": "..."}}

    Returns:
        Merged XML string ready for mkvpropedit
    """
    if existing is not None:
        root = existing
    else:
        root = ET.Element("Tags")

    # Remove track-targeted Tag blocks (with TrackUID) — these are managed by
    # mkvpropedit separately and must NOT be in the --tags global: XML, or
    # mkvpropedit silently discards all global tags from the file.
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is not None and targets.find("TrackUID") is not None:
            root.remove(tag)

    # Index remaining (global) Tag blocks by their TTV
    ttv_to_tag: dict[int | None, ET.Element] = {}
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is not None:
            ttv_el = targets.find("TargetTypeValue")
            if ttv_el is not None and ttv_el.text is not None:
                ttv_to_tag[int(ttv_el.text)] = tag

    # Merge each TTV scope
    for ttv, tag_dict in new_tags.items():
        if ttv in ttv_to_tag:
            tag_block = ttv_to_tag[ttv]
        else:
            # Create new Tag block with Targets
            tag_block = ET.SubElement(root, "Tag")
            targets = ET.SubElement(tag_block, "Targets")
            ttv_el = ET.SubElement(targets, "TargetTypeValue")
            ttv_el.text = str(ttv)
            ttv_to_tag[ttv] = tag_block

        # Index existing Simple elements by Name
        simple_by_name: dict[str, ET.Element] = {}
        for simple in tag_block.findall("Simple"):
            name_el = simple.find("Name")
            if name_el is not None and name_el.text is not None:
                simple_by_name[name_el.text] = simple

        for name, value in tag_dict.items():
            if name in simple_by_name:
                # Update existing — but empty value preserves existing
                if value:
                    string_el = simple_by_name[name].find("String")
                    if string_el is not None:
                        string_el.text = value
                    else:
                        string_el = ET.SubElement(simple_by_name[name], "String")
                        string_el.text = value
            else:
                # Add new Simple element (skip if value is empty)
                if value:
                    simple = ET.SubElement(tag_block, "Simple")
                    name_el = ET.SubElement(simple, "Name")
                    name_el.text = name
                    string_el = ET.SubElement(simple, "String")
                    string_el.text = value

    # Serialize
    ET.indent(root, space="  ")
    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return xml_str


def write_merged_tags(
    filepath: Path, new_tags: dict[int, dict[str, str]]
) -> bool:
    """Extract existing tags, merge new ones in, and write the combined result.

    This is the safe replacement for direct mkvpropedit --tags global: calls.
    It preserves tags written by other modules.

    Args:
        filepath: Path to the MKV file to modify
        new_tags: Dict mapping TargetTypeValue -> {Name: String} pairs

    Returns:
        True if successful, False otherwise
    """
    if not metadata.MKVPROPEDIT_PATH:
        return False

    if not filepath.exists() or filepath.suffix.lower() != ".mkv":
        return False

    # Extract existing tags
    existing = extract_all_tags(filepath)

    # Merge
    merged_xml = merge_tags(existing, new_tags)

    # Write via mkvpropedit
    tag_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False, encoding="utf-8"
        ) as f:
            f.write(merged_xml)
            tag_file = f.name

        result = subprocess.run(
            [metadata.MKVPROPEDIT_PATH, str(filepath), "--tags", f"global:{tag_file}"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            logger.warning(
                "Tag writing failed for %s: %s", filepath, result.stderr.strip()
            )
            return False

        return True

    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("Tag writing failed for %s: %s", filepath, e)
        return False
    finally:
        if tag_file:
            try:
                os.unlink(tag_file)
            except Exception:
                pass
