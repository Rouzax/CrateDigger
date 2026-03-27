import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from festival_organizer.nfo import generate_nfo
from festival_organizer.config import Config, DEFAULT_CONFIG
from festival_organizer.models import MediaFile

CFG = Config(DEFAULT_CONFIG)


def test_generate_nfo_festival_set():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "2024 - AMF - Martin Garrix.mkv"
        video_path.touch()

        mf = MediaFile(
            source_path=video_path,
            artist="Martin Garrix",
            festival="AMF",
            year="2024",
            date="2024-10-19",
            content_type="festival_set",
            stage="Johan Cruijff ArenA",
            tracklists_url="https://www.1001tracklists.com/tracklist/qv6kl89/",
            duration_seconds=7200.0,
            width=3840,
            height=2160,
            video_format="VP9",
            audio_format="Opus",
            extension=".mkv",
        )

        nfo_path = generate_nfo(mf, video_path, CFG)

        assert nfo_path.exists()
        assert nfo_path.suffix == ".nfo"
        assert nfo_path.stem == video_path.stem

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        assert root.tag == "musicvideo"
        assert root.find("title").text == "2024 - AMF - Martin Garrix"
        assert root.find("artist").text == "Martin Garrix"
        assert root.find("album").text == "AMF"
        assert root.find("year").text == "2024"
        assert root.find("genre").text == "Electronic"
        assert root.find("premiered").text == "2024-10-19"
        assert "1001tracklists" in root.find("plot").text


def test_generate_nfo_concert_film():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "Coldplay - A Head Full of Dreams.mkv"
        video_path.touch()

        mf = MediaFile(
            source_path=video_path,
            artist="Coldplay",
            title="A Head Full of Dreams",
            year="2018",
            content_type="concert_film",
            duration_seconds=6240.0,
            width=1920,
            height=1080,
            video_format="AVC",
            audio_format="E-AC-3",
            extension=".mkv",
        )

        nfo_path = generate_nfo(mf, video_path, CFG)

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        assert root.find("artist").text == "Coldplay"
        assert root.find("album").text == "A Head Full of Dreams"
        assert root.find("genre").text == "Live"


def test_generate_nfo_with_streamdetails():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "test.mkv"
        video_path.touch()

        mf = MediaFile(
            source_path=video_path,
            artist="Test",
            festival="AMF",
            year="2024",
            content_type="festival_set",
            width=3840,
            height=2160,
            video_format="VP9",
            audio_format="Opus",
            extension=".mkv",
        )

        nfo_path = generate_nfo(mf, video_path, CFG)

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        vstream = root.find(".//fileinfo/streamdetails/video")
        assert vstream is not None
        assert vstream.find("codec").text == "VP9"
        assert vstream.find("width").text == "3840"
        assert vstream.find("height").text == "2160"
