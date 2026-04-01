import xml.etree.ElementTree as ET
from pathlib import Path
from festival_organizer.models import MediaFile
from festival_organizer.config import load_config
from festival_organizer.nfo import generate_nfo


def _parse_nfo(nfo_path: Path) -> ET.Element:
    return ET.fromstring(nfo_path.read_text(encoding="utf-8"))


def test_nfo_uses_premiered_not_year(tmp_path):
    """premiered field present, year tag absent (deprecated in Kodi v20)."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test", year="2024",
                   date="2024-07-21", content_type="festival_set", festival="TML")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("premiered") is not None
    assert root.find("premiered").text == "2024-07-21"
    assert root.find("year") is None


def test_nfo_album_is_festival_plus_year(tmp_path):
    """album = festival + year for Kodi grouping."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   festival="Tomorrowland", year="2024",
                   content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("album").text == "Tomorrowland 2024"


def test_nfo_title_falls_back_to_artist_when_no_stage(tmp_path):
    """title = artist when no stage available for festival sets."""
    mf = MediaFile(source_path=Path("2024 - TML - Artist.mkv"), artist="Martin Garrix",
                   festival="Tomorrowland", year="2024",
                   content_type="festival_set")
    video = tmp_path / "2024 - TML - Martin Garrix.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix"


def test_nfo_title_is_title_for_concerts(tmp_path):
    """title = descriptive title for concert films."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Adele",
                   title="Live at Hyde Park", content_type="concert_film")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Live at Hyde Park"


def test_nfo_tags_for_smart_playlists(tmp_path):
    """tag elements for content type, festival, edition."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   festival="Tomorrowland", edition="Belgium",
                   year="2024", content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    tags = [t.text for t in root.findall("tag")]
    assert "festival_set" in tags
    assert "Tomorrowland" in tags
    assert "Belgium" in tags


def test_nfo_studio_is_stage(tmp_path):
    """studio = stage name for festival sets."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   stage="Mainstage", content_type="festival_set",
                   festival="TML", year="2024")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("studio").text == "Mainstage"


def test_nfo_dateadded_present(tmp_path):
    """dateadded element is present with ISO format."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   content_type="festival_set", festival="TML", year="2024")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    dateadded = root.find("dateadded")
    assert dateadded is not None
    assert len(dateadded.text) >= 10  # At least YYYY-MM-DD


def test_nfo_plot_no_tracklist_url(tmp_path):
    """plot should NOT contain 1001Tracklists URL."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   festival="TML", year="2024", content_type="festival_set",
                   stage="Mainstage", edition="Belgium",
                   tracklists_url="https://www.1001tracklists.com/tracklist/abc123")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    plot = root.find("plot")
    if plot is not None and plot.text:
        assert "1001tracklists" not in plot.text.lower()


def test_nfo_multiple_thumb_aspects(tmp_path):
    """thumb elements for both thumb and poster images."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   content_type="festival_set", festival="TML", year="2024")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    thumbs = root.findall("thumb")
    aspects = [t.get("aspect") for t in thumbs]
    assert "thumb" in aspects
    assert "poster" in aspects
    # Fanart references the thumb image
    fanart = root.find("fanart")
    assert fanart is not None
    fanart_thumb = fanart.find("thumb")
    assert fanart_thumb is not None
    assert fanart_thumb.text == "test-thumb.jpg"


def test_nfo_no_streamdetails(tmp_path):
    """fileinfo/streamdetails should not be present (Kodi overwrites on playback)."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   content_type="festival_set", festival="TML", year="2024",
                   video_format="HEVC", audio_format="AAC",
                   width=1920, height=1080, duration_seconds=3600)
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("fileinfo") is None


def test_nfo_concert_film(tmp_path):
    """Concert film NFO has correct album and genre."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Coldplay",
                   title="A Head Full of Dreams", year="2018",
                   content_type="concert_film")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("artist").text == "Coldplay"
    assert root.find("album").text == "A Head Full of Dreams"
    assert root.find("genre").text == "Live"


def test_nfo_title_artist_at_stage_festival(tmp_path):
    """title = 'Artist @ Stage, Festival' for festival sets."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Afrojack",
                   stage="kineticFIELD", festival="EDC Las Vegas", year="2025",
                   content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Afrojack @ kineticFIELD, EDC Las Vegas"


def test_nfo_title_includes_set_title(tmp_path):
    """title appends set_title (WE1/WE2) to festival name."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Armin van Buuren",
                   stage="Mainstage", festival="Tomorrowland", year="2025",
                   set_title="WE2", content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Armin van Buuren @ Mainstage, Tomorrowland WE2"


def test_nfo_title_falls_back_to_artist(tmp_path):
    """title = artist when no stage available."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Martin Garrix",
                   festival="Red Rocks", year="2025",
                   content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix"


def test_nfo_title_uses_display_artist_for_b2b(tmp_path):
    """NFO title uses display_artist for B2B sets."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        stage="Main Stage",
        festival="Red Rocks",
        year="2025",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix & Alesso @ Main Stage, Red Rocks"
    assert root.find("artist").text == "Martin Garrix"  # primary for Plex


def test_nfo_title_display_artist_no_stage(tmp_path):
    """NFO title without stage still uses display_artist."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        year="2025",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix & Alesso"
