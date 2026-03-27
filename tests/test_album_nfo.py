"""Tests for album NFO generation."""
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from festival_organizer.album_nfo import generate_album_nfo
from festival_organizer.config import Config, DEFAULT_CONFIG
from festival_organizer.models import MediaFile

CFG = Config(DEFAULT_CONFIG)


def test_generate_album_nfo_festival_nested():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        files = [
            MediaFile(source_path=folder / "a.mkv", artist="Martin Garrix", festival="AMF", year="2024", content_type="festival_set"),
            MediaFile(source_path=folder / "b.mkv", artist="Tiesto", festival="AMF", year="2024", content_type="festival_set"),
        ]
        nfo_path = generate_album_nfo(folder, files, CFG, layout_name="festival_nested")

        assert nfo_path.exists()
        tree = ET.parse(nfo_path)
        root = tree.getroot()
        assert root.tag == "album"
        assert "AMF" in root.find("title").text
        assert root.find("year").text == "2024"
        assert root.find("genre").text == "Electronic"
        assert "Martin Garrix" in root.find("plot").text


def test_generate_album_nfo_artist_first():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        files = [
            MediaFile(source_path=folder / "a.mkv", artist="Hardwell", festival="Tomorrowland", year="2025", location="Belgium", content_type="festival_set"),
        ]
        nfo_path = generate_album_nfo(folder, files, CFG)

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        assert "Hardwell" in root.find("title").text
        assert "Tomorrowland" in root.find("title").text


def test_generate_album_nfo_concert():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        files = [
            MediaFile(source_path=folder / "a.mkv", artist="Coldplay", title="Live 2012", year="2012", content_type="concert_film"),
        ]
        nfo_path = generate_album_nfo(folder, files, CFG)

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        assert root.find("genre").text == "Live"
