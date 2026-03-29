"""Tests for the mkv_tags extract-merge-write module."""
import xml.etree.ElementTree as ET

from festival_organizer.mkv_tags import merge_tags


def _parse_merged(xml_str: str) -> ET.Element:
    """Parse merged XML string into an Element."""
    return ET.fromstring(xml_str)


def _get_tag_block(root: ET.Element, ttv: int) -> ET.Element | None:
    """Find the Tag block with the given TargetTypeValue."""
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is not None:
            ttv_el = targets.find("TargetTypeValue")
            if ttv_el is not None and ttv_el.text == str(ttv):
                return tag
    return None


def _get_simple_value(tag_block: ET.Element, name: str) -> str | None:
    """Get the String value of a Simple element by Name."""
    for simple in tag_block.findall("Simple"):
        name_el = simple.find("Name")
        if name_el is not None and name_el.text == name:
            string_el = simple.find("String")
            return string_el.text if string_el is not None else None
    return None


def test_merge_tags_empty_existing():
    """When no existing tags, creates fresh XML from new_tags."""
    result = merge_tags(None, {50: {"ARTIST": "Tiesto", "TITLE": "TML 2024"}})
    root = _parse_merged(result)

    tag = _get_tag_block(root, 50)
    assert tag is not None
    assert _get_simple_value(tag, "ARTIST") == "Tiesto"
    assert _get_simple_value(tag, "TITLE") == "TML 2024"


def test_merge_tags_preserves_other_ttv():
    """Writing TTV=70 preserves existing TTV=50 block."""
    existing_xml = """<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
  </Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {70: {"1001TRACKLISTS_URL": "https://example.com"}})
    root = _parse_merged(result)

    # TTV=50 preserved
    tag50 = _get_tag_block(root, 50)
    assert tag50 is not None
    assert _get_simple_value(tag50, "ARTIST") == "Tiesto"

    # TTV=70 added
    tag70 = _get_tag_block(root, 70)
    assert tag70 is not None
    assert _get_simple_value(tag70, "1001TRACKLISTS_URL") == "https://example.com"


def test_merge_tags_updates_within_same_ttv():
    """Updating a value within the same TTV replaces the old value."""
    existing_xml = """<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>Old Artist</String></Simple>
    <Simple><Name>TITLE</Name><String>Old Title</String></Simple>
  </Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {50: {"ARTIST": "New Artist"}})
    root = _parse_merged(result)

    tag50 = _get_tag_block(root, 50)
    assert tag50 is not None
    assert _get_simple_value(tag50, "ARTIST") == "New Artist"
    assert _get_simple_value(tag50, "TITLE") == "Old Title"


def test_merge_tags_adds_new_within_same_ttv():
    """Adding a new tag within existing TTV doesn't remove existing tags."""
    existing_xml = """<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
  </Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {50: {"TITLE": "TML 2024"}})
    root = _parse_merged(result)

    tag50 = _get_tag_block(root, 50)
    assert tag50 is not None
    assert _get_simple_value(tag50, "ARTIST") == "Tiesto"
    assert _get_simple_value(tag50, "TITLE") == "TML 2024"


def test_merge_tags_preserves_unknown_tags():
    """Custom/unknown tag names are preserved during merge."""
    existing_xml = """<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>MY_CUSTOM_TAG</Name><String>custom_value</String></Simple>
    <Simple><Name>ARTIST</Name><String>Old</String></Simple>
  </Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {50: {"ARTIST": "New"}})
    root = _parse_merged(result)

    tag50 = _get_tag_block(root, 50)
    assert tag50 is not None
    assert _get_simple_value(tag50, "MY_CUSTOM_TAG") == "custom_value"
    assert _get_simple_value(tag50, "ARTIST") == "New"


def test_merge_tags_empty_value_preserves_existing():
    """An empty string value does not overwrite an existing value."""
    existing_xml = """<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
  </Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {50: {"ARTIST": ""}})
    root = _parse_merged(result)

    tag50 = _get_tag_block(root, 50)
    assert tag50 is not None
    assert _get_simple_value(tag50, "ARTIST") == "Tiesto"


def test_merge_tags_multiple_ttvs_at_once():
    """Can write both TTV=50 and TTV=70 in a single merge call."""
    result = merge_tags(None, {
        50: {"ARTIST": "Tiesto", "TITLE": "TML 2024"},
        70: {"1001TRACKLISTS_URL": "https://example.com"},
    })
    root = _parse_merged(result)

    tag50 = _get_tag_block(root, 50)
    assert tag50 is not None
    assert _get_simple_value(tag50, "ARTIST") == "Tiesto"
    assert _get_simple_value(tag50, "TITLE") == "TML 2024"

    tag70 = _get_tag_block(root, 70)
    assert tag70 is not None
    assert _get_simple_value(tag70, "1001TRACKLISTS_URL") == "https://example.com"


def test_merge_tags_no_targets_preserved():
    """Tag blocks with no Targets element are preserved unchanged."""
    existing_xml = """<Tags>
  <Tag>
    <Simple><Name>ENCODER</Name><String>ffmpeg</String></Simple>
  </Tag>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>Old</String></Simple>
  </Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {50: {"ARTIST": "New"}})
    root = _parse_merged(result)

    # The no-targets block should still be there
    no_target_tags = [
        tag for tag in root.findall("Tag")
        if tag.find("Targets") is None
    ]
    assert len(no_target_tags) == 1
    assert _get_simple_value(no_target_tags[0], "ENCODER") == "ffmpeg"

    # TTV=50 updated
    tag50 = _get_tag_block(root, 50)
    assert tag50 is not None
    assert _get_simple_value(tag50, "ARTIST") == "New"
