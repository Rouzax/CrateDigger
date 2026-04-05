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


def test_nfo_title_artist_at_festival_when_no_stage(tmp_path):
    """title = 'Artist @ Festival' when no stage available for festival sets."""
    mf = MediaFile(source_path=Path("2024 - TML - Artist.mkv"), artist="Martin Garrix",
                   festival="Tomorrowland", year="2024",
                   content_type="festival_set")
    video = tmp_path / "2024 - TML - Martin Garrix.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix @ Tomorrowland"


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
    # Fanart references the dedicated fanart sidecar
    fanart = root.find("fanart")
    assert fanart is not None
    fanart_thumb = fanart.find("thumb")
    assert fanart_thumb is not None
    assert fanart_thumb.text == "test-fanart.jpg"


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


def test_nfo_title_artist_at_festival_no_stage(tmp_path):
    """title = 'Artist @ Festival' when no stage available."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Martin Garrix",
                   festival="Red Rocks", year="2025",
                   content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix @ Red Rocks"


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


def test_nfo_title_display_artist_at_festival_no_stage(tmp_path):
    """NFO title = 'display_artist @ Festival' when no stage."""
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
    assert root.find("title").text == "Martin Garrix & Alesso @ Red Rocks"


def test_nfo_title_no_stage_no_festival(tmp_path):
    """title = bare artist when neither stage nor festival."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Martin Garrix",
                   year="2025", content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Martin Garrix"


def test_nfo_title_no_stage_with_set_title(tmp_path):
    """set_title appended to festival when no stage."""
    mf = MediaFile(source_path=Path("test.mkv"), artist="Agents Of Time",
                   festival="Tomorrowland", set_title="WE1", year="2025",
                   content_type="festival_set")
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    assert root.find("title").text == "Agents Of Time @ Tomorrowland WE1"


def test_nfo_multiple_artists_b2b(tmp_path):
    """B2B set has two <artist> elements."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        artists=["Martin Garrix", "Alesso"],
        festival="Red Rocks", year="2025",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    artist_elems = root.findall("artist")
    assert len(artist_elems) == 2
    assert artist_elems[0].text == "Martin Garrix"
    assert artist_elems[1].text == "Alesso"


def test_nfo_single_artist_stays_single(tmp_path):
    """Single artist still produces one <artist> element."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Armin van Buuren",
        artists=["Armin van Buuren"],
        festival="Tomorrowland", year="2024",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    artist_elems = root.findall("artist")
    assert len(artist_elems) == 1
    assert artist_elems[0].text == "Armin van Buuren"


def test_nfo_empty_artists_falls_back(tmp_path):
    """Empty artists list falls back to mf.artist."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        artists=[],
        festival="TML", year="2024",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    artist_elems = root.findall("artist")
    assert len(artist_elems) == 1
    assert artist_elems[0].text == "Martin Garrix"


def test_nfo_artist_tags_present(tmp_path):
    """Each artist appears as a <tag> element."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        artists=["Martin Garrix", "Alesso"],
        festival="Red Rocks", year="2025",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    tags = [t.text for t in root.findall("tag")]
    assert "Martin Garrix" in tags
    assert "Alesso" in tags


def test_nfo_artist_tags_deduplicated(tmp_path):
    """Artist tags don't duplicate existing tags like festival name."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Tomorrowland",
        artists=["Tomorrowland"],
        festival="Tomorrowland", year="2024",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    tags = [t.text for t in root.findall("tag")]
    assert tags.count("Tomorrowland") == 1


def test_nfo_group_members_as_tags(tmp_path):
    """Group members from DJ cache appear as <tag> elements."""
    from festival_organizer.tracklists.dj_cache import DjCache
    dj_cache = DjCache(tmp_path / "dj_cache.json")
    dj_cache.put("arminvanbuuren", {
        "name": "Armin van Buuren", "artwork_url": "",
        "aliases": [], "member_of": [{"slug": "gaia-nl", "name": "Gaia"}],
    })
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Gaia",
        artists=["Gaia"],
        festival="Tomorrowland", year="2024",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config(), dj_cache=dj_cache))
    tags = [t.text for t in root.findall("tag")]
    assert "Gaia" in tags
    assert "Armin van Buuren" in tags


def test_nfo_no_dj_cache_no_expansion(tmp_path):
    """Without DJ cache, no group member expansion."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Gaia",
        artists=["Gaia"],
        festival="Tomorrowland", year="2024",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config()))
    tags = [t.text for t in root.findall("tag")]
    assert "Gaia" in tags
