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
from festival_organizer.normalization import fix_mojibake

logger = logging.getLogger(__name__)

MATROSKA_EXTS = frozenset({".mkv", ".webm"})

# Sentinel value: pass as a tag value to explicitly clear an existing tag.
# Regular empty string "" preserves the existing value (backward compatible).
CLEAR_TAG = object()


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

        if result.returncode >= 2:
            detail = result.stderr.strip() or f"exit code {result.returncode}"
            logger.warning("Tag extraction failed for %s: %s", filepath, detail)
            return None

        if result.returncode == 1:
            logger.debug("mkvextract warnings for %s: %s", filepath, result.stderr.strip())

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
            except OSError:
                pass


def _tag_values_from_root(root: ET.Element) -> dict[int, dict[str, str]]:
    """Derive TTV-grouped tag values from an already-parsed <Tags> root.

    Returns dict mapping TTV -> {Name: String} for all global tags.
    """
    result: dict[int, dict[str, str]] = {}
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is None:
            continue
        if targets.find("TrackUID") is not None:
            continue
        ttv_el = targets.find("TargetTypeValue")
        ttv = int(ttv_el.text) if (ttv_el is not None and ttv_el.text is not None) else 50

        tags: dict[str, str] = {}
        for simple in tag.findall("Simple"):
            name_el = simple.find("Name")
            string_el = simple.find("String")
            if name_el is not None and string_el is not None:
                name = fix_mojibake(name_el.text or "")
                value = fix_mojibake(string_el.text or "")
                tags[name] = value
        if tags:
            result[ttv] = tags

    return result


def extract_tag_values(filepath: Path) -> dict[int, dict[str, str]]:
    """Extract existing tag values grouped by TargetTypeValue.

    Returns dict mapping TTV -> {Name: String} for all global tags.
    Returns empty dict if no tags or extraction fails.
    """
    root = extract_all_tags(filepath)
    if root is None:
        return {}

    return _tag_values_from_root(root)


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
            ttv = int(ttv_el.text) if (ttv_el is not None and ttv_el.text is not None) else 50
            ttv_to_tag[ttv] = tag

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
                # Update existing; empty value preserves existing unless
                # explicitly clearing (value is CLEAR_TAG sentinel)
                if value or value is CLEAR_TAG:
                    write_val = "" if value is CLEAR_TAG else value
                    string_el = simple_by_name[name].find("String")
                    if string_el is not None:
                        string_el.text = write_val
                    else:
                        string_el = ET.SubElement(simple_by_name[name], "String")
                        string_el.text = write_val
            else:
                # Add new Simple element (skip if value is empty)
                if value and value is not CLEAR_TAG:
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
    filepath: Path, new_tags: dict[int, dict[str, str]], existing_root=None
) -> bool:
    """Extract existing tags, merge new ones in, and write the combined result.

    This is the safe replacement for direct mkvpropedit --tags global: calls.
    It preserves tags written by other modules.

    Args:
        filepath: Path to the MKV file to modify
        new_tags: Dict mapping TargetTypeValue -> {Name: String} pairs
        existing_root: Pre-extracted XML root from extract_all_tags(); when
            provided the redundant extraction is skipped.

    Returns:
        True if successful, False otherwise
    """
    if not metadata.MKVPROPEDIT_PATH:
        return False

    if not filepath.exists() or filepath.suffix.lower() not in MATROSKA_EXTS:
        return False

    # Extract existing tags (skip if caller already extracted)
    existing = existing_root if existing_root is not None else extract_all_tags(filepath)

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
            detail = result.stderr.strip() or f"exit code {result.returncode}"
            logger.warning("Tag writing failed for %s: %s", filepath, detail)
            return False

        return True

    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("Tag writing failed for %s: %s", filepath, e)
        return False
    finally:
        if tag_file:
            try:
                os.unlink(tag_file)
            except OSError:
                pass
