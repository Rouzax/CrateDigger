"""Tests for the mkv_tags extract-merge-write module."""
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from festival_organizer.mkv_tags import _tag_values_from_root, extract_all_tags, merge_tags


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


def test_merge_tags_clear_tag_clears_existing():
    """CLEAR_TAG sentinel explicitly clears an existing tag value."""
    from festival_organizer.mkv_tags import CLEAR_TAG
    existing_xml = """<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>DESCRIPTION</Name><String>yt-dlp junk</String></Simple>
  </Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {50: {"DESCRIPTION": CLEAR_TAG}})
    root = _parse_merged(result)

    tag50 = _get_tag_block(root, 50)
    assert tag50 is not None
    # ET serializes empty text as <String/>, which parses back as None
    assert _get_simple_value(tag50, "DESCRIPTION") is None


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
    """Simples from a Targets-less block fold into the single global TTV=50 block.

    Per Matroska spec a Tag block with no Targets element is implicitly TTV=50,
    so an unrelated Simple like ENCODER in that block and an explicit TTV=50
    block collapse into one on merge. The ENCODER value is preserved, ARTIST
    is updated in place.
    """
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

    global_blocks = []
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is None:
            global_blocks.append(tag)
            continue
        if targets.find("TrackUID") is not None:
            continue
        if targets.find("ChapterUID") is not None:
            continue
        global_blocks.append(tag)

    assert len(global_blocks) == 1
    keeper = global_blocks[0]
    assert _get_simple_value(keeper, "ENCODER") == "ffmpeg"
    assert _get_simple_value(keeper, "ARTIST") == "New"


def test_merge_tags_strips_track_uid_blocks():
    """Track-targeted tags (with TrackUID) must be stripped from merged output.

    mkvpropedit --tags global: silently discards all global tags if the XML
    contains track-targeted Tag blocks alongside global ones.
    """
    existing_xml = """<Tags>
  <Tag>
    <Targets><TrackUID>12345</TrackUID></Targets>
    <Simple><Name>BPS</Name><String>128000</String></Simple>
    <Simple><Name>DURATION</Name><String>01:00:00.000</String></Simple>
  </Tag>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>Existing</String></Simple>
  </Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {70: {"1001TRACKLISTS_URL": "https://example.com"}})
    root = _parse_merged(result)

    # TrackUID block must be gone
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is not None:
            assert targets.find("TrackUID") is None, "TrackUID block should be stripped"

    # Global tags preserved
    tag50 = _get_tag_block(root, 50)
    assert tag50 is not None
    assert _get_simple_value(tag50, "ARTIST") == "Existing"

    tag70 = _get_tag_block(root, 70)
    assert tag70 is not None
    assert _get_simple_value(tag70, "1001TRACKLISTS_URL") == "https://example.com"


def test_tag_values_from_root_missing_ttv_defaults_to_50():
    """Tag blocks with Targets but no TargetTypeValue default to TTV=50."""
    xml = """<Tags>
  <Tag>
    <Targets></Targets>
    <Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
  </Tag>
</Tags>"""
    root = ET.fromstring(xml)
    result = _tag_values_from_root(root)
    assert 50 in result
    assert result[50]["ARTIST"] == "Tiesto"


def test_tag_values_from_root_fixes_mojibake():
    """Mojibake in tag values is cleaned on extraction."""
    xml = """<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>KÃ¶lsch</String></Simple>
    <Simple><Name>TITLE</Name><String>Ã©dition</String></Simple>
  </Tag>
</Tags>"""
    root = ET.fromstring(xml)
    result = _tag_values_from_root(root)
    assert result[50]["ARTIST"] == "Kölsch"
    assert result[50]["TITLE"] == "édition"


def test_merge_tags_missing_ttv_treated_as_50():
    """Existing block without TargetTypeValue is updated in-place, no duplicate."""
    existing_xml = """<Tags>
  <Tag>
    <Targets></Targets>
    <Simple><Name>ARTIST</Name><String>Old</String></Simple>
  </Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {50: {"ARTIST": "New"}})
    root = _parse_merged(result)

    # Should have exactly one Tag block (updated in-place, no duplicate)
    tag_blocks = root.findall("Tag")
    assert len(tag_blocks) == 1
    assert _get_simple_value(tag_blocks[0], "ARTIST") == "New"


def test_extract_all_tags_exit_code_1_still_parses(tmp_path):
    """mkvextract returning exit code 1 (warnings) still produces parsed XML."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    tag_xml = '<?xml version="1.0"?><Tags><Tag><Targets><TargetTypeValue>50</TargetTypeValue></Targets><Simple><Name>ARTIST</Name><String>Tiesto</String></Simple></Tag></Tags>'

    def fake_run(cmd, **kwargs):
        tag_file = cmd[3]  # mkvextract <file> tags <tagfile>
        Path(tag_file).write_text(tag_xml, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="Warning: something")

    with patch("festival_organizer.mkv_tags.metadata.MKVEXTRACT_PATH", "/usr/bin/mkvextract"):
        with patch("festival_organizer.mkv_tags.tracked_run", side_effect=fake_run):
            root = extract_all_tags(video)

    assert root is not None
    tag = root.find("Tag")
    assert tag is not None


def test_merge_tags_folds_duplicate_global_blocks():
    """A pre-existing bug accumulated duplicate Tag blocks at the same TTV
    (e.g. 30x ARTIST=Tiësto from repeated enrichment runs). merge_tags must
    fold them into one block on next write."""
    existing_xml = """<Tags>
<Tag><Targets/><Simple><Name>ARTIST</Name><String>Tiësto</String></Simple></Tag>
<Tag><Targets/><Simple><Name>ARTIST</Name><String>Tiësto</String></Simple></Tag>
<Tag><Targets/><Simple><Name>ARTIST</Name><String>Tiësto</String></Simple></Tag>
<Tag><Targets><TargetTypeValue>70</TargetTypeValue></Targets>
<Simple><Name>URL</Name><String>https://x</String></Simple></Tag>
</Tags>"""
    import xml.etree.ElementTree as ET
    existing = ET.fromstring(existing_xml)
    result = merge_tags(existing, {})
    root = ET.fromstring(result)
    # Count blocks whose content is just ARTIST=Tiësto
    artist_blocks = []
    for tag in root.findall("Tag"):
        for s in tag.findall("Simple"):
            n = s.find("Name")
            v = s.find("String")
            if n is not None and n.text == "ARTIST" and v is not None and v.text == "Tiësto":
                artist_blocks.append(tag)
                break
    assert len(artist_blocks) == 1, f"Expected 1 ARTIST block, got {len(artist_blocks)}"


def test_merge_tags_fold_preserves_distinct_names_across_duplicates():
    """Folding duplicate TTV=50 blocks should preserve distinct Simple names."""
    existing_xml = """<Tags>
<Tag><Targets/><Simple><Name>ARTIST</Name><String>X</String></Simple></Tag>
<Tag><Targets/><Simple><Name>TITLE</Name><String>Y</String></Simple></Tag>
</Tags>"""
    import xml.etree.ElementTree as ET
    existing = ET.fromstring(existing_xml)
    result = merge_tags(existing, {})
    root = ET.fromstring(result)
    # Should end up with one Tag block containing both ARTIST and TITLE
    assert len(root.findall("Tag")) == 1
    names = {s.find("Name").text for s in root.find("Tag").findall("Simple")}
    assert names == {"ARTIST", "TITLE"}


def test_merge_tags_fold_later_wins_on_conflicting_values():
    """If two duplicate TTV=50 blocks have the same Name with different values,
    the later block's value wins after folding."""
    existing_xml = """<Tags>
<Tag><Targets/><Simple><Name>ARTIST</Name><String>Old</String></Simple></Tag>
<Tag><Targets/><Simple><Name>ARTIST</Name><String>New</String></Simple></Tag>
</Tags>"""
    import xml.etree.ElementTree as ET
    existing = ET.fromstring(existing_xml)
    result = merge_tags(existing, {})
    root = ET.fromstring(result)
    tags = root.findall("Tag")
    assert len(tags) == 1
    simples = tags[0].findall("Simple")
    assert len(simples) == 1
    assert simples[0].find("String").text == "New"


def test_merge_tags_fold_does_not_touch_chapter_scoped_blocks():
    """TTV=30 blocks (one per ChapterUID) each target a distinct UID and
    must NOT be folded, even though they share the same TTV."""
    existing_xml = """<Tags>
<Tag><Targets><TargetTypeValue>30</TargetTypeValue><ChapterUID>111</ChapterUID></Targets>
<Simple><Name>PERFORMER</Name><String>A</String></Simple></Tag>
<Tag><Targets><TargetTypeValue>30</TargetTypeValue><ChapterUID>222</ChapterUID></Targets>
<Simple><Name>PERFORMER</Name><String>B</String></Simple></Tag>
</Tags>"""
    import xml.etree.ElementTree as ET
    existing = ET.fromstring(existing_xml)
    result = merge_tags(existing, {})
    root = ET.fromstring(result)
    chap_tags = [t for t in root.findall("Tag")
                 if t.find("Targets/ChapterUID") is not None]
    assert len(chap_tags) == 2


def test_has_chapter_tags_returns_false_when_no_tags(tmp_path, monkeypatch):
    """File with no tags at all: extract_all_tags returns None → False."""
    from festival_organizer.mkv_tags import has_chapter_tags
    import festival_organizer.mkv_tags as mod
    monkeypatch.setattr(mod, "extract_all_tags", lambda p: None)
    assert has_chapter_tags(tmp_path / "x.mkv") is False


def test_has_chapter_tags_returns_false_when_only_global(monkeypatch):
    """File with only TTV=50 and TTV=70 blocks: False."""
    import xml.etree.ElementTree as ET
    from festival_organizer.mkv_tags import has_chapter_tags
    import festival_organizer.mkv_tags as mod
    xml = """<Tags>
<Tag><Targets><TargetTypeValue>50</TargetTypeValue></Targets>
<Simple><Name>ARTIST</Name><String>Tiësto</String></Simple></Tag>
<Tag><Targets><TargetTypeValue>70</TargetTypeValue></Targets>
<Simple><Name>CRATEDIGGER_1001TL_ID</Name><String>abc</String></Simple></Tag>
</Tags>"""
    monkeypatch.setattr(mod, "extract_all_tags", lambda p: ET.fromstring(xml))
    from pathlib import Path
    assert has_chapter_tags(Path("/x.mkv")) is False


def test_has_chapter_tags_returns_true_when_performer_names_present(monkeypatch):
    """TTV=30 block carrying CRATEDIGGER_TRACK_PERFORMER_NAMES: True (current contract)."""
    import xml.etree.ElementTree as ET
    from festival_organizer.mkv_tags import has_chapter_tags
    import festival_organizer.mkv_tags as mod
    xml = """<Tags>
<Tag><Targets><TargetTypeValue>50</TargetTypeValue></Targets>
<Simple><Name>ARTIST</Name><String>x</String></Simple></Tag>
<Tag><Targets><TargetTypeValue>30</TargetTypeValue><ChapterUID>111</ChapterUID></Targets>
<Simple><Name>CRATEDIGGER_TRACK_PERFORMER</Name><String>y</String></Simple>
<Simple><Name>CRATEDIGGER_TRACK_PERFORMER_NAMES</Name><String>y</String></Simple></Tag>
</Tags>"""
    monkeypatch.setattr(mod, "extract_all_tags", lambda p: ET.fromstring(xml))
    from pathlib import Path
    assert has_chapter_tags(Path("/x.mkv")) is True


def test_has_chapter_tags_returns_false_when_ttv30_lacks_performer_names(monkeypatch):
    """Legacy file carrying only the pre-rename unprefixed PERFORMER_NAMES:
    False, so identify self-heals on next run and switches to the prefixed name."""
    import xml.etree.ElementTree as ET
    from festival_organizer.mkv_tags import has_chapter_tags
    import festival_organizer.mkv_tags as mod
    xml = """<Tags>
<Tag><Targets><TargetTypeValue>30</TargetTypeValue><ChapterUID>111</ChapterUID></Targets>
<Simple><Name>PERFORMER</Name><String>y</String></Simple>
<Simple><Name>PERFORMER_NAMES</Name><String>y</String></Simple></Tag>
</Tags>"""
    monkeypatch.setattr(mod, "extract_all_tags", lambda p: ET.fromstring(xml))
    from pathlib import Path
    assert has_chapter_tags(Path("/x.mkv")) is False


def test_has_chapter_tags_ignores_targets_without_ttv(monkeypatch):
    """<Targets/> empty block (defaults to TTV=50 semantically): not a chapter tag."""
    import xml.etree.ElementTree as ET
    from festival_organizer.mkv_tags import has_chapter_tags
    import festival_organizer.mkv_tags as mod
    xml = """<Tags>
<Tag><Targets/><Simple><Name>ARTIST</Name><String>x</String></Simple></Tag>
</Tags>"""
    monkeypatch.setattr(mod, "extract_all_tags", lambda p: ET.fromstring(xml))
    from pathlib import Path
    assert has_chapter_tags(Path("/x.mkv")) is False


def test_has_album_artist_display_tags_false_when_no_tags(tmp_path, monkeypatch):
    """File with no tags at all: extract_all_tags returns None → False."""
    from festival_organizer.mkv_tags import has_album_artist_display_tags
    import festival_organizer.mkv_tags as mod
    monkeypatch.setattr(mod, "extract_all_tags", lambda p: None)
    assert has_album_artist_display_tags(tmp_path / "x.mkv") is False


def test_has_album_artist_display_tags_false_for_legacy_only_artists(monkeypatch):
    """Pre-0.12.4 file with only CRATEDIGGER_1001TL_ARTISTS: self-heal needed."""
    import xml.etree.ElementTree as ET
    from festival_organizer.mkv_tags import has_album_artist_display_tags
    import festival_organizer.mkv_tags as mod
    xml = """<Tags>
<Tag><Targets><TargetTypeValue>70</TargetTypeValue></Targets>
<Simple><Name>CRATEDIGGER_1001TL_ARTISTS</Name><String>Martin Garrix|Alesso</String></Simple></Tag>
</Tags>"""
    monkeypatch.setattr(mod, "extract_all_tags", lambda p: ET.fromstring(xml))
    from pathlib import Path
    assert has_album_artist_display_tags(Path("/x.mkv")) is False


def test_has_album_artist_display_tags_true_when_display_present(monkeypatch):
    """Current contract (0.12.4+): _DISPLAY present at TTV=70 global → True."""
    import xml.etree.ElementTree as ET
    from festival_organizer.mkv_tags import has_album_artist_display_tags
    import festival_organizer.mkv_tags as mod
    xml = """<Tags>
<Tag><Targets><TargetTypeValue>70</TargetTypeValue></Targets>
<Simple><Name>CRATEDIGGER_1001TL_ARTISTS</Name><String>Martin Garrix|Alesso</String></Simple>
<Simple><Name>CRATEDIGGER_ALBUMARTIST_SLUGS</Name><String>martin-garrix|alesso</String></Simple>
<Simple><Name>CRATEDIGGER_ALBUMARTIST_DISPLAY</Name><String>Martin Garrix &amp; Alesso</String></Simple></Tag>
</Tags>"""
    monkeypatch.setattr(mod, "extract_all_tags", lambda p: ET.fromstring(xml))
    from pathlib import Path
    assert has_album_artist_display_tags(Path("/x.mkv")) is True


def test_has_album_artist_display_tags_ignores_chapter_scoped_name(monkeypatch):
    """A TTV=30 chapter block that happens to mention the album name must not
    count as album-level coverage."""
    import xml.etree.ElementTree as ET
    from festival_organizer.mkv_tags import has_album_artist_display_tags
    import festival_organizer.mkv_tags as mod
    xml = """<Tags>
<Tag><Targets><TargetTypeValue>30</TargetTypeValue><ChapterUID>111</ChapterUID></Targets>
<Simple><Name>CRATEDIGGER_ALBUMARTIST_DISPLAY</Name><String>misplaced</String></Simple></Tag>
</Tags>"""
    monkeypatch.setattr(mod, "extract_all_tags", lambda p: ET.fromstring(xml))
    from pathlib import Path
    assert has_album_artist_display_tags(Path("/x.mkv")) is False


def test_tag_values_from_root_reads_targetless_block_as_ttv50():
    """Tag block with no <Targets> element is surfaced at TTV=50 (spec default)."""
    xml = """<Tags>
      <Tag>
        <Simple><Name>ARTIST</Name><String>Marlon Hoffstadt</String></Simple>
        <Simple><Name>TITLE</Name><String>Marlon Hoffstadt @ AMF</String></Simple>
      </Tag>
    </Tags>"""
    root = ET.fromstring(xml)

    result = _tag_values_from_root(root)

    assert 50 in result
    assert result[50]["ARTIST"] == "Marlon Hoffstadt"
    assert result[50]["TITLE"] == "Marlon Hoffstadt @ AMF"


def test_tag_values_from_root_still_skips_trackuid_blocks():
    """Negative control: TrackUID-targeted blocks are track tags, not global. Still skipped."""
    xml = """<Tags>
      <Tag>
        <Targets><TrackUID>12345</TrackUID></Targets>
        <Simple><Name>BPS</Name><String>14000000</String></Simple>
      </Tag>
    </Tags>"""
    root = ET.fromstring(xml)

    result = _tag_values_from_root(root)

    assert result == {}


def test_tag_values_from_root_later_targetless_overrides_earlier():
    """When duplicate Targets-less blocks exist, later values win at the Name level.

    Acceptable for idempotency: duplicates on real files carry identical values,
    so the "last wins" semantics are not lossy. Test pins the contract.
    """
    xml = """<Tags>
      <Tag>
        <Simple><Name>ARTIST</Name><String>Old</String></Simple>
      </Tag>
      <Tag>
        <Simple><Name>ARTIST</Name><String>New</String></Simple>
      </Tag>
    </Tags>"""
    root = ET.fromstring(xml)

    result = _tag_values_from_root(root)

    assert result[50]["ARTIST"] == "New"


def test_merge_tags_consolidates_targetless_duplicates():
    """Multiple Targets-less Tag blocks fold into one TTV=50 block on merge."""
    existing_xml = """<Tags>
      <Tag>
        <Simple><Name>ARTIST</Name><String>Marlon Hoffstadt</String></Simple>
        <Simple><Name>TITLE</Name><String>Marlon Hoffstadt @ AMF</String></Simple>
      </Tag>
      <Tag>
        <Simple><Name>ARTIST</Name><String>Marlon Hoffstadt</String></Simple>
        <Simple><Name>TITLE</Name><String>Marlon Hoffstadt @ AMF</String></Simple>
      </Tag>
      <Tag>
        <Simple><Name>ARTIST</Name><String>Marlon Hoffstadt</String></Simple>
        <Simple><Name>TITLE</Name><String>Marlon Hoffstadt @ AMF</String></Simple>
      </Tag>
    </Tags>"""
    existing = ET.fromstring(existing_xml)

    # Merge with no new TTV=50 tags, should still consolidate
    result = merge_tags(existing, {})
    root = _parse_merged(result)

    # Count global (non-TrackUID, non-ChapterUID) Tag blocks
    global_blocks = []
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is None:
            global_blocks.append(tag)
            continue
        if targets.find("TrackUID") is not None:
            continue
        if targets.find("ChapterUID") is not None:
            continue
        global_blocks.append(tag)

    assert len(global_blocks) == 1, (
        f"Expected one global block after consolidation, got {len(global_blocks)}"
    )
    keeper = global_blocks[0]
    assert _get_simple_value(keeper, "ARTIST") == "Marlon Hoffstadt"
    assert _get_simple_value(keeper, "TITLE") == "Marlon Hoffstadt @ AMF"


def test_merge_tags_consolidates_mixed_targeted_and_targetless_at_ttv50():
    """A Targets-less block and an explicit TTV=50 block fold together."""
    existing_xml = """<Tags>
      <Tag>
        <Simple><Name>ARTIST</Name><String>Old</String></Simple>
      </Tag>
      <Tag>
        <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
        <Simple><Name>TITLE</Name><String>Set Title</String></Simple>
      </Tag>
    </Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {})
    root = _parse_merged(result)

    global_blocks = []
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is None:
            global_blocks.append(tag)
            continue
        if targets.find("TrackUID") is not None:
            continue
        if targets.find("ChapterUID") is not None:
            continue
        global_blocks.append(tag)

    assert len(global_blocks) == 1
    keeper = global_blocks[0]
    assert _get_simple_value(keeper, "ARTIST") == "Old"
    assert _get_simple_value(keeper, "TITLE") == "Set Title"


def test_merge_tags_updates_targetless_block_in_place():
    """Writing new TTV=50 values updates the Targets-less block rather than appending."""
    existing_xml = """<Tags>
      <Tag>
        <Simple><Name>ARTIST</Name><String>Old Artist</String></Simple>
        <Simple><Name>TITLE</Name><String>Old Title</String></Simple>
      </Tag>
    </Tags>"""
    existing = ET.fromstring(existing_xml)

    result = merge_tags(existing, {50: {"ARTIST": "New Artist", "TITLE": "New Title"}})
    root = _parse_merged(result)

    global_blocks = []
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is None:
            global_blocks.append(tag)
            continue
        if targets.find("TrackUID") is not None:
            continue
        if targets.find("ChapterUID") is not None:
            continue
        global_blocks.append(tag)

    assert len(global_blocks) == 1, (
        f"Expected one global block, got {len(global_blocks)} "
        f"(indicates a new Targets-wrapped block was appended instead of updating in place)"
    )
    keeper = global_blocks[0]
    assert _get_simple_value(keeper, "ARTIST") == "New Artist"
    assert _get_simple_value(keeper, "TITLE") == "New Title"


# --- Tier 2 tag-diff DEBUG for write_merged_tags ---

def test_write_merged_tags_logs_diff_counts(tmp_path, caplog):
    """write_merged_tags emits a DEBUG summary of +added -removed ~changed."""
    import logging
    from festival_organizer.mkv_tags import write_merged_tags, CLEAR_TAG

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")

    existing_xml = """<Tags>
<Tag><Targets><TargetTypeValue>50</TargetTypeValue></Targets>
<Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
<Simple><Name>ALBUM</Name><String>Live</String></Simple>
<Simple><Name>GENRE</Name><String>Trance</String></Simple>
</Tag>
</Tags>"""
    existing_root = ET.fromstring(existing_xml)

    new_tags = {
        50: {
            "ARTIST": "Skrillex",   # changed: Tiesto -> Skrillex
            "YEAR": "2025",         # added: not in existing
            "GENRE": CLEAR_TAG,     # removed: was "Trance"
            "ALBUM": "Live",        # no change: same value
        }
    }

    from unittest.mock import MagicMock
    with patch("festival_organizer.mkv_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with patch("festival_organizer.mkv_tags.tracked_run",
                   return_value=MagicMock(returncode=0, stderr="")):
            with caplog.at_level(logging.DEBUG, logger="festival_organizer.mkv_tags"):
                ok = write_merged_tags(video, new_tags, existing_root=existing_root)
    assert ok is True
    joined = "\n".join(r.message for r in caplog.records)
    assert "Tags for test.mkv: +1 -1 ~1" in joined


def test_write_merged_tags_skips_debug_when_no_changes(tmp_path, caplog):
    """No-op merges emit no tag-diff DEBUG line."""
    import logging
    from festival_organizer.mkv_tags import write_merged_tags

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")

    existing_xml = """<Tags>
<Tag><Targets><TargetTypeValue>50</TargetTypeValue></Targets>
<Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
</Tag>
</Tags>"""
    existing_root = ET.fromstring(existing_xml)

    # Same value = no change
    new_tags = {50: {"ARTIST": "Tiesto"}}

    from unittest.mock import MagicMock
    with patch("festival_organizer.mkv_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with patch("festival_organizer.mkv_tags.tracked_run",
                   return_value=MagicMock(returncode=0, stderr="")):
            with caplog.at_level(logging.DEBUG, logger="festival_organizer.mkv_tags"):
                ok = write_merged_tags(video, new_tags, existing_root=existing_root)
    assert ok is True
    joined = "\n".join(r.message for r in caplog.records)
    assert "Tags for test.mkv" not in joined
