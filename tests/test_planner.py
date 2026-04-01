from pathlib import Path
from festival_organizer.planner import plan_actions
from festival_organizer.config import Config, DEFAULT_CONFIG
from festival_organizer.models import MediaFile, FileAction

CFG = Config(DEFAULT_CONFIG)
OUTPUT = Path("/tmp/test/Output")


def test_plan_festival_set_artist_flat():
    mf = MediaFile(
        source_path=Path("/tmp/test/Input/file.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        content_type="festival_set",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG)
    assert len(actions) == 1
    a = actions[0]
    assert a.target == OUTPUT / "Martin Garrix" / "2024 - Martin Garrix - AMF.mkv"
    assert a.action == "move"


def test_plan_concert_film():
    mf = MediaFile(
        source_path=Path("/tmp/test/Input/file.mkv"),
        artist="Coldplay",
        title="A Head Full of Dreams",
        year="2018",
        content_type="concert_film",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG)
    a = actions[0]
    assert a.target == OUTPUT / "Coldplay" / "Coldplay - A Head Full of Dreams (2018).mkv"


def test_plan_unknown_goes_to_needs_review():
    mf = MediaFile(
        source_path=Path("/tmp/test/Input/mystery.mkv"),
        content_type="unknown",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG)
    a = actions[0]
    assert "_Needs Review" in str(a.target)


def test_plan_with_set_title():
    mf = MediaFile(
        source_path=Path("/tmp/test/Input/file.mkv"),
        artist="Hardwell",
        festival="Tomorrowland",
        year="2025",
        edition="Belgium",
        set_title="WE1",
        content_type="festival_set",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG)
    a = actions[0]
    assert "WE1" in a.target.name
    assert "Hardwell" in str(a.target)


def test_plan_action_type_copy():
    mf = MediaFile(
        source_path=Path("/tmp/test/Input/file.mkv"),
        artist="Test",
        festival="AMF",
        year="2024",
        content_type="festival_set",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG, action="copy")
    assert actions[0].action == "copy"


def test_plan_action_type_rename():
    mf = MediaFile(
        source_path=Path("/tmp/test/Input/file.mkv"),
        artist="Test",
        festival="AMF",
        year="2024",
        content_type="festival_set",
        extension=".mkv",
    )
    actions = plan_actions([mf], OUTPUT, CFG, action="rename")
    a = actions[0]
    assert a.action == "rename"
    # Rename keeps the file in its original directory
    assert a.target.parent == Path("/tmp/test/Input")
