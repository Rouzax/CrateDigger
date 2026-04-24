import re
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from festival_organizer.embed_tags import embed_tags
from festival_organizer.models import MediaFile


def _make_mf(**kwargs):
    defaults = dict(source_path=Path("test.mkv"), artist="Test",
                    festival="TML", year="2024", content_type="festival_set")
    defaults.update(kwargs)
    return MediaFile(**defaults)


def test_embed_tags_failure_logged(tmp_path, caplog):
    """Tag embedding failure is logged via write_merged_tags."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()

    with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with patch("festival_organizer.embed_tags.write_merged_tags", return_value=False):
            result = embed_tags(mf, video)
    assert result == "error"


def test_embed_tags_calls_write_merged_tags(tmp_path):
    """embed_tags uses mkv_tags.write_merged_tags, not raw mkvpropedit."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(artist="Afrojack", festival="EDC Las Vegas",
                   stage="kineticFIELD", year="2025")

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            result = embed_tags(mf, video)

    assert result == "done"
    mock_wmt.assert_called_once()
    call_args = mock_wmt.call_args
    assert call_args[0][0] == video
    tags_dict = call_args[0][1]
    assert 50 in tags_dict
    assert tags_dict[50]["ARTIST"] == "Afrojack"
    assert tags_dict[50]["TITLE"] == "Afrojack @ kineticFIELD, EDC Las Vegas"
    assert tags_dict[50]["DATE_RELEASED"] == "2025"


def test_embed_tags_title_includes_set_title(tmp_path):
    """MKV TITLE tag includes set_title (WE1/WE2) appended to festival."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(artist="Armin van Buuren", festival="Tomorrowland",
                   stage="Mainstage", year="2025", set_title="WE2")

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    assert tags_dict[50]["TITLE"] == "Armin van Buuren @ Mainstage, Tomorrowland WE2"


def test_embed_tags_title_fallback_no_stage(tmp_path):
    """MKV TITLE uses Artist @ Festival when no stage available."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(artist="Martin Garrix", festival="Red Rocks", year="2025")

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    assert tags_dict[50]["TITLE"] == "Martin Garrix @ Red Rocks"


def test_embed_tags_writes_enrichment_tags_at_ttv70(tmp_path):
    """Enrichment tags (fanart/clearlogo URLs) are written at TTV=70."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        fanart_url="https://fanart.tv/bg.jpg",
        clearlogo_url="https://fanart.tv/logo.png",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            result = embed_tags(mf, video)

    assert result == "done"
    tags_dict = mock_wmt.call_args[0][1]
    assert 70 in tags_dict
    assert tags_dict[70]["CRATEDIGGER_FANART_URL"] == "https://fanart.tv/bg.jpg"
    assert tags_dict[70]["CRATEDIGGER_CLEARLOGO_URL"] == "https://fanart.tv/logo.png"
    # CRATEDIGGER_ENRICHED_AT should be a current ISO timestamp
    assert "CRATEDIGGER_ENRICHED_AT" in tags_dict[70]
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", tags_dict[70]["CRATEDIGGER_ENRICHED_AT"])


def test_embed_tags_skips_empty_enrichment_fields(tmp_path):
    """Empty enrichment fields are not written to TTV=70."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(fanart_url="", clearlogo_url="")

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    # TTV=70 should not be present if all enrichment fields are empty
    assert 70 not in tags_dict


def test_embed_tags_b2b_artist_in_title_not_artist_tag(tmp_path):
    """TITLE uses display_artist (B2B), ARTIST stays primary for Plex."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        year="2025",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    assert tags_dict[50]["ARTIST"] == "Martin Garrix"  # primary for Plex
    assert tags_dict[50]["TITLE"] == "Martin Garrix & Alesso @ Red Rocks"  # display_artist in title


def test_embed_tags_b2b_with_stage_in_title(tmp_path):
    """TITLE with stage uses display_artist for B2B."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        stage="Main Stage",
        year="2025",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    assert tags_dict[50]["ARTIST"] == "Martin Garrix"
    assert tags_dict[50]["TITLE"] == "Martin Garrix & Alesso @ Main Stage, Red Rocks"


def test_embed_tags_skipped_when_tags_match(tmp_path):
    """embed_tags returns 'skipped' when existing TTV=50 tags already match."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(artist="Tiesto", festival="TML", year="2024")

    existing_xml = """<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
    <Simple><Name>TITLE</Name><String>Tiesto @ TML</String></Simple>
    <Simple><Name>DATE_RELEASED</Name><String>2024</String></Simple>
    <Simple><Name>SYNOPSIS</Name><String>Tiesto
TML</String></Simple>
    <Simple><Name>DESCRIPTION</Name><String></String></Simple>
  </Tag>
</Tags>"""
    existing_root = ET.fromstring(existing_xml)

    with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with patch("festival_organizer.embed_tags.extract_all_tags", return_value=existing_root):
            with patch("festival_organizer.embed_tags.write_merged_tags") as mock_wmt:
                result = embed_tags(mf, video)

    assert result == "skipped"
    mock_wmt.assert_not_called()


def test_embed_tags_skipped_with_enrichment_tags_match(tmp_path):
    """embed_tags returns 'skipped' when TTV=50 and TTV=70 tags all match."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Tiesto", festival="TML", year="2024",
        fanart_url="https://fanart.tv/bg.jpg",
        clearlogo_url="https://fanart.tv/logo.png",
    )

    existing_xml = """<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
    <Simple><Name>TITLE</Name><String>Tiesto @ TML</String></Simple>
    <Simple><Name>DATE_RELEASED</Name><String>2024</String></Simple>
    <Simple><Name>SYNOPSIS</Name><String>Tiesto
TML</String></Simple>
    <Simple><Name>DESCRIPTION</Name><String></String></Simple>
  </Tag>
  <Tag>
    <Targets><TargetTypeValue>70</TargetTypeValue></Targets>
    <Simple><Name>CRATEDIGGER_FANART_URL</Name><String>https://fanart.tv/bg.jpg</String></Simple>
    <Simple><Name>CRATEDIGGER_CLEARLOGO_URL</Name><String>https://fanart.tv/logo.png</String></Simple>
    <Simple><Name>CRATEDIGGER_ENRICHED_AT</Name><String>2024-01-01T00:00:00+00:00</String></Simple>
  </Tag>
</Tags>"""
    existing_root = ET.fromstring(existing_xml)

    with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with patch("festival_organizer.embed_tags.extract_all_tags", return_value=existing_root):
            with patch("festival_organizer.embed_tags.write_merged_tags") as mock_wmt:
                result = embed_tags(mf, video)

    assert result == "skipped"
    mock_wmt.assert_not_called()


# --- Curated SYNOPSIS tag tests ---


def test_embed_tags_curated_description_full(tmp_path):
    """SYNOPSIS tag built from display_artist, stage, festival, country, source_type."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Armin van Buuren",
        display_artist="Armin van Buuren",
        festival="Tomorrowland", stage="Mainstage",
        country="Belgium", source_type="Open Air / Festival",
        edition="Belgium", set_title="WE2", year="2024",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    desc = tags_dict[50]["SYNOPSIS"]
    assert desc == "Armin van Buuren @ Mainstage\nTomorrowland (Open Air / Festival), Belgium\nEdition: Belgium | WE2"


def test_embed_tags_description_no_stage(tmp_path):
    """DESCRIPTION omits @ stage when no stage."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Martin Garrix",
        display_artist="Martin Garrix",
        festival="Tomorrowland",
        country="Belgium", source_type="Open Air / Festival",
        year="2024",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    desc = tags_dict[50]["SYNOPSIS"]
    assert desc == "Martin Garrix\nTomorrowland (Open Air / Festival), Belgium"


def test_embed_tags_description_venue_fallback(tmp_path):
    """DESCRIPTION uses venue when no festival."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Martin Garrix",
        display_artist="Martin Garrix",
        festival="", venue="Red Rocks Amphitheatre",
        country="United States", source_type="Event Location",
        year="2025",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    desc = tags_dict[50]["SYNOPSIS"]
    assert "Red Rocks Amphitheatre (Event Location), United States" in desc


def test_embed_tags_description_skipped_when_same(tmp_path):
    """SYNOPSIS not rewritten when it already matches curated text."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Tiesto", display_artist="Tiesto",
        festival="TML", country="Belgium",
        source_type="Open Air / Festival", year="2024",
    )

    curated = "Tiesto\nTML (Open Air / Festival), Belgium"

    existing_xml = f"""<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
    <Simple><Name>TITLE</Name><String>Tiesto @ TML</String></Simple>
    <Simple><Name>DATE_RELEASED</Name><String>2024</String></Simple>
    <Simple><Name>SYNOPSIS</Name><String>{curated}</String></Simple>
    <Simple><Name>DESCRIPTION</Name><String></String></Simple>
  </Tag>
</Tags>"""
    existing_root = ET.fromstring(existing_xml)

    with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with patch("festival_organizer.embed_tags.extract_all_tags", return_value=existing_root):
            with patch("festival_organizer.embed_tags.write_merged_tags") as mock_wmt:
                result = embed_tags(mf, video)

    assert result == "skipped"
    mock_wmt.assert_not_called()


def test_embed_tags_description_b2b(tmp_path):
    """DESCRIPTION uses display_artist for B2B sets."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks", stage="Main Stage",
        country="United States", source_type="Event Location",
        year="2025",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    desc = tags_dict[50]["SYNOPSIS"]
    assert "Martin Garrix & Alesso @ Main Stage" in desc


def test_embed_tags_description_no_location(tmp_path):
    """DESCRIPTION with only artist (no festival, no venue)."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Test", display_artist="Test",
        festival="", year="2024",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    desc = tags_dict[50]["SYNOPSIS"]
    assert desc == "Test"


def test_embed_tags_description_cleared(tmp_path):
    """DESCRIPTION is marked for clearing via CLEAR_TAG sentinel."""
    from festival_organizer.mkv_tags import CLEAR_TAG
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Armin van Buuren",
        display_artist="Armin van Buuren",
        festival="Tomorrowland", year="2024",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    assert tags_dict[50]["DESCRIPTION"] is CLEAR_TAG
    assert "SYNOPSIS" in tags_dict[50]


def test_embed_tags_description_uses_location_when_festival_and_venue_empty(tmp_path):
    """SYNOPSIS falls back to plain-text location when no festival/venue.

    A file with only CRATEDIGGER_1001TL_LOCATION (e.g. "Alexandra Palace
    London") should still get a useful line 2 in the synopsis.
    """
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Fred again..",
        display_artist="Fred again..",
        festival="", festival_full="", venue="",
        location="Alexandra Palace London",
        country="United Kingdom",
        year="2024",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    desc = tags_dict[50]["SYNOPSIS"]
    assert "Alexandra Palace London" in desc
    assert "United Kingdom" in desc


def test_embed_tags_description_prefers_venue_over_location(tmp_path):
    """SYNOPSIS prefers structured venue over plain-text location fallback."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="DJ",
        display_artist="DJ",
        stage="Main",
        festival="", festival_full="",
        venue="Structured Venue",
        location="Free Text Location",
        country="Belgium",
        year="2024",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    desc = tags_dict[50]["SYNOPSIS"]
    assert "Structured Venue" in desc
    assert "Free Text Location" not in desc


def test_embed_tags_synopsis_uses_festival_full(tmp_path):
    """SYNOPSIS uses festival_full (raw 1001TL name) over resolved alias."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        artist="Martin Garrix",
        display_artist="Martin Garrix",
        festival="AMF",
        festival_full="Amsterdam Music Festival",
        country="Netherlands", source_type="Open Air / Festival",
        year="2024",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            embed_tags(mf, video)

    tags_dict = mock_wmt.call_args[0][1]
    desc = tags_dict[50]["SYNOPSIS"]
    assert "Amsterdam Music Festival" in desc
    assert "AMF" not in desc


# --- Duplicate global block detection (heal trigger) ---


def test_has_duplicate_global_blocks_detects_multiple_targetless():
    """Two Targets-less global blocks trip the heal trigger."""
    from festival_organizer.mkv_tags import has_duplicate_global_blocks

    xml = """<Tags>
      <Tag><Simple><Name>ARTIST</Name><String>X</String></Simple></Tag>
      <Tag><Simple><Name>ARTIST</Name><String>X</String></Simple></Tag>
    </Tags>"""
    root = ET.fromstring(xml)

    assert has_duplicate_global_blocks(root) is True


def test_has_duplicate_global_blocks_single_block_is_fine():
    """One Targets-less block is not a duplicate."""
    from festival_organizer.mkv_tags import has_duplicate_global_blocks

    xml = """<Tags>
      <Tag><Simple><Name>ARTIST</Name><String>X</String></Simple></Tag>
    </Tags>"""
    root = ET.fromstring(xml)

    assert has_duplicate_global_blocks(root) is False


def test_has_duplicate_global_blocks_ignores_trackuid_and_chapteruid():
    """Per-track and per-chapter blocks are separate contracts, never 'duplicates'."""
    from festival_organizer.mkv_tags import has_duplicate_global_blocks

    xml = """<Tags>
      <Tag><Targets><TrackUID>1</TrackUID></Targets><Simple><Name>BPS</Name><String>1</String></Simple></Tag>
      <Tag><Targets><TrackUID>2</TrackUID></Targets><Simple><Name>BPS</Name><String>2</String></Simple></Tag>
      <Tag><Targets><TargetTypeValue>30</TargetTypeValue><ChapterUID>10</ChapterUID></Targets><Simple><Name>T</Name><String>A</String></Simple></Tag>
      <Tag><Targets><TargetTypeValue>30</TargetTypeValue><ChapterUID>20</ChapterUID></Targets><Simple><Name>T</Name><String>B</String></Simple></Tag>
      <Tag><Simple><Name>ARTIST</Name><String>X</String></Simple></Tag>
    </Tags>"""
    root = ET.fromstring(xml)

    assert has_duplicate_global_blocks(root) is False


def test_has_duplicate_global_blocks_detects_two_ttv70_blocks():
    """Two explicit TTV=70 blocks are a duplicate. Should not happen in practice but pin the contract."""
    from festival_organizer.mkv_tags import has_duplicate_global_blocks

    xml = """<Tags>
      <Tag><Targets><TargetTypeValue>70</TargetTypeValue></Targets><Simple><Name>A</Name><String>1</String></Simple></Tag>
      <Tag><Targets><TargetTypeValue>70</TargetTypeValue></Targets><Simple><Name>B</Name><String>2</String></Simple></Tag>
    </Tags>"""
    root = ET.fromstring(xml)

    assert has_duplicate_global_blocks(root) is True


def test_embed_tags_returns_done_when_duplicates_present_even_if_values_match(tmp_path):
    """File with duplicate Targets-less blocks triggers a heal write even when values match.

    needs_write's value-diff comparison would return False (duplicates carry
    identical values), but has_duplicate_global_blocks flips needs_write to
    True so the Task 2 consolidation runs on the next write.
    """
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(artist="Tiesto", festival="TML", year="2024")

    existing_xml = """<Tags>
  <Tag>
    <Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
    <Simple><Name>TITLE</Name><String>Tiesto @ TML</String></Simple>
    <Simple><Name>DATE_RELEASED</Name><String>2024</String></Simple>
    <Simple><Name>SYNOPSIS</Name><String>Tiesto
TML</String></Simple>
    <Simple><Name>DESCRIPTION</Name><String></String></Simple>
  </Tag>
  <Tag>
    <Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
    <Simple><Name>TITLE</Name><String>Tiesto @ TML</String></Simple>
    <Simple><Name>DATE_RELEASED</Name><String>2024</String></Simple>
    <Simple><Name>SYNOPSIS</Name><String>Tiesto
TML</String></Simple>
    <Simple><Name>DESCRIPTION</Name><String></String></Simple>
  </Tag>
</Tags>"""
    existing_root = ET.fromstring(existing_xml)

    with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with patch("festival_organizer.embed_tags.extract_all_tags", return_value=existing_root):
            with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
                result = embed_tags(mf, video)

    assert result == "done"
    mock_wmt.assert_called_once()


def test_embed_tags_debug_when_mkvpropedit_missing(tmp_path, caplog):
    """Missing MKVPROPEDIT_PATH -> DEBUG (not WARNING; would spam over many
    files when --embed-tags runs without the tool installed) and returns 'error'."""
    import logging as _logging
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()
    with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", None):
        with caplog.at_level(_logging.DEBUG, logger="festival_organizer.embed_tags"):
            result = embed_tags(mf, video)
    assert result == "error"
    joined = "\n".join(r.message for r in caplog.records)
    assert "mkvpropedit" in joined.lower()
    warnings = [r for r in caplog.records if r.levelno >= _logging.WARNING]
    assert warnings == []


def test_embed_tags_warns_when_target_missing_or_wrong_ext(tmp_path, caplog):
    """Missing file or non-Matroska extension -> WARNING (upstream pipeline
    bug, should be rare; one per bad input is fine)."""
    import logging as _logging
    mf = _make_mf()
    video = tmp_path / "nonexistent.mkv"
    with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with caplog.at_level(_logging.WARNING, logger="festival_organizer.embed_tags"):
            result = embed_tags(mf, video)
    assert result == "error"
    joined = "\n".join(r.message for r in caplog.records)
    assert "nonexistent.mkv" in joined
