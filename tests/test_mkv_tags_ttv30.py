"""Per-chapter (TTV=30) tag merging."""
import xml.etree.ElementTree as ET
from festival_organizer.mkv_tags import merge_tags


def _find_chapter_tags(xml_str: str) -> list[ET.Element]:
    """Return all Tag elements with TargetTypeValue=30."""
    root = ET.fromstring(xml_str)
    out = []
    for tag in root.findall("Tag"):
        targets = tag.find("Targets")
        if targets is None:
            continue
        ttv_el = targets.find("TargetTypeValue")
        if ttv_el is not None and ttv_el.text == "30":
            out.append(tag)
    return out


def test_merge_tags_emits_per_chapter_tags():
    result = merge_tags(None, {50: {"ARTIST": "Afrojack"}}, chapter_tags={
        111: {"ARTIST": "Afrojack", "GENRE": "House"},
        222: {"ARTIST": "Guest", "GENRE": "Techno"},
    })
    chap_tags = _find_chapter_tags(result)
    assert len(chap_tags) == 2
    # Verify ChapterUID targeting
    uids = set()
    for t in chap_tags:
        uid_el = t.find("Targets/ChapterUID")
        assert uid_el is not None
        uids.add(uid_el.text)
    assert uids == {"111", "222"}
    # Verify content
    for t in chap_tags:
        uid = t.find("Targets/ChapterUID").text
        simples = {s.find("Name").text: s.find("String").text for s in t.findall("Simple")}
        if uid == "111":
            assert simples["ARTIST"] == "Afrojack"
            assert simples["GENRE"] == "House"
        else:
            assert simples["ARTIST"] == "Guest"
            assert simples["GENRE"] == "Techno"


def test_merge_tags_chapter_tags_replace_existing():
    existing_xml = """<Tags>
<Tag><Targets><TargetTypeValue>30</TargetTypeValue><ChapterUID>999</ChapterUID></Targets>
<Simple><Name>ARTIST</Name><String>Old</String></Simple></Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)
    result = merge_tags(existing, {}, chapter_tags={
        111: {"ARTIST": "New"},
    })
    chap_tags = _find_chapter_tags(result)
    uids = [t.find("Targets/ChapterUID").text for t in chap_tags]
    # Existing UID 999 must be gone; new UID 111 present; no duplicates
    assert uids == ["111"]


def test_merge_tags_without_chapter_tags_preserves_existing_ttv30():
    """If chapter_tags is not passed, pre-existing TTV=30 blocks survive."""
    existing_xml = """<Tags>
<Tag><Targets><TargetTypeValue>50</TargetTypeValue></Targets>
<Simple><Name>ARTIST</Name><String>X</String></Simple></Tag>
<Tag><Targets><TargetTypeValue>30</TargetTypeValue><ChapterUID>999</ChapterUID></Targets>
<Simple><Name>ARTIST</Name><String>Preserved</String></Simple></Tag>
</Tags>"""
    existing = ET.fromstring(existing_xml)
    result = merge_tags(existing, {50: {"TITLE": "T"}})
    chap_tags = _find_chapter_tags(result)
    assert len(chap_tags) == 1
    assert chap_tags[0].find("Targets/ChapterUID").text == "999"
    assert chap_tags[0].find("Simple/String").text == "Preserved"


def test_merge_tags_chapter_tags_coexist_with_global_tags():
    result = merge_tags(
        None,
        {50: {"ARTIST": "Afrojack"}, 70: {"URL": "https://example.com"}},
        chapter_tags={111: {"ARTIST": "Afrojack"}},
    )
    root = ET.fromstring(result)
    ttvs = []
    for tag in root.findall("Tag"):
        ttv_el = tag.find("Targets/TargetTypeValue")
        ttvs.append(ttv_el.text if ttv_el is not None else None)
    # Expect one each: 50, 70, 30
    assert sorted(ttvs) == ["30", "50", "70"]


def test_merge_tags_chapter_tag_value_types_are_strings():
    """ChapterUID in XML must be a string representation of the int."""
    result = merge_tags(None, {}, chapter_tags={
        12345678901234567: {"ARTIST": "Big UID"},
    })
    chap_tags = _find_chapter_tags(result)
    assert chap_tags[0].find("Targets/ChapterUID").text == "12345678901234567"
