import logging
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
    """Enrichment tags (MBID, fanart/clearlogo URLs) are written at TTV=70."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(
        mbid="abc-123-def",
        fanart_url="https://fanart.tv/bg.jpg",
        clearlogo_url="https://fanart.tv/logo.png",
    )

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            result = embed_tags(mf, video)

    assert result == "done"
    tags_dict = mock_wmt.call_args[0][1]
    assert 70 in tags_dict
    assert tags_dict[70]["CRATEDIGGER_MBID"] == "abc-123-def"
    assert tags_dict[70]["CRATEDIGGER_FANART_URL"] == "https://fanart.tv/bg.jpg"
    assert tags_dict[70]["CRATEDIGGER_CLEARLOGO_URL"] == "https://fanart.tv/logo.png"
    # CRATEDIGGER_ENRICHED_AT should be a current ISO timestamp
    assert "CRATEDIGGER_ENRICHED_AT" in tags_dict[70]
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", tags_dict[70]["CRATEDIGGER_ENRICHED_AT"])


def test_embed_tags_skips_empty_enrichment_fields(tmp_path):
    """Empty enrichment fields are not written to TTV=70."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(mbid="", fanart_url="", clearlogo_url="")

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
        mbid="abc-123", fanart_url="https://fanart.tv/bg.jpg",
        clearlogo_url="https://fanart.tv/logo.png",
    )

    existing_xml = """<Tags>
  <Tag>
    <Targets><TargetTypeValue>50</TargetTypeValue></Targets>
    <Simple><Name>ARTIST</Name><String>Tiesto</String></Simple>
    <Simple><Name>TITLE</Name><String>Tiesto @ TML</String></Simple>
    <Simple><Name>DATE_RELEASED</Name><String>2024</String></Simple>
  </Tag>
  <Tag>
    <Targets><TargetTypeValue>70</TargetTypeValue></Targets>
    <Simple><Name>CRATEDIGGER_MBID</Name><String>abc-123</String></Simple>
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
