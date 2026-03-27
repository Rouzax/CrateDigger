from pathlib import Path
from festival_organizer.classifier import classify
from festival_organizer.config import Config, DEFAULT_CONFIG
from festival_organizer.models import MediaFile

CFG = Config(DEFAULT_CONFIG)
ROOT = Path("//hyperv/Data/Concerts")


def test_classify_force_concert():
    mf = MediaFile(source_path=ROOT / "Adele/2011/file.mkv", artist="Adele")
    assert classify(mf, ROOT, CFG) == "concert_film"

    mf2 = MediaFile(source_path=ROOT / "U2/360/file.mkv", artist="U2")
    assert classify(mf2, ROOT, CFG) == "concert_film"

    mf3 = MediaFile(source_path=ROOT / "Coldplay/2016/file.mkv", artist="Coldplay")
    assert classify(mf3, ROOT, CFG) == "concert_film"


def test_classify_1001tl_is_festival():
    mf = MediaFile(
        source_path=ROOT / "AMF/2024/file.mkv",
        artist="Martin Garrix",
        festival="AMF",
        metadata_source="1001tracklists",
    )
    assert classify(mf, ROOT, CFG) == "festival_set"


def test_classify_known_festival():
    mf = MediaFile(
        source_path=ROOT / "EDC/2025/file.mkv",
        artist="Armin van Buuren",
        festival="EDC Las Vegas",
        metadata_source="filename",
    )
    assert classify(mf, ROOT, CFG) == "festival_set"


def test_classify_unknown():
    mf = MediaFile(
        source_path=ROOT / "random/file.mkv",
        artist="Some Artist",
    )
    assert classify(mf, ROOT, CFG) == "unknown"


def test_classify_festival_overrides_no_force_concert():
    """A file in a concert-forced dir but with 1001TL should still be concert (force_concert wins)."""
    mf = MediaFile(
        source_path=ROOT / "Adele/2011/file.mkv",
        artist="Adele",
        festival="Glastonbury",
        metadata_source="1001tracklists",
    )
    # force_concert takes precedence
    assert classify(mf, ROOT, CFG) == "concert_film"
