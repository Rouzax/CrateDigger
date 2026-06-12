from PIL import Image
from festival_organizer.poster import (
    COVER_POSTER_VERSION, build_cover_stamp, read_poster_stamp, inject_poster_stamp,
)


def _make_jpeg(path):
    Image.new("RGB", (1000, 1500), (10, 10, 20)).save(str(path), "JPEG", quality=95)


def test_build_cover_stamp_is_deterministic():
    a = build_cover_stamp(artist="AFROJACK", festival="UMF Miami", date="2026-03-29",
                          year="2026", stage="Mainstage", venue="")
    b = build_cover_stamp(artist="AFROJACK", festival="UMF Miami", date="2026-03-29",
                          year="2026", stage="Mainstage", venue="")
    assert a == b and isinstance(a, bytes)
    assert str(COVER_POSTER_VERSION).encode() in a


def test_stamp_changes_when_a_field_changes():
    base = dict(artist="A", festival="F", date="d", year="y", stage="s", venue="v")
    assert build_cover_stamp(**base) != build_cover_stamp(**{**base, "festival": "F2"})


def test_inject_and_read_round_trip(tmp_path):
    p = tmp_path / "x-poster.jpg"
    _make_jpeg(p)
    assert read_poster_stamp(p) is None  # freshly rendered: no stamp
    stamp = build_cover_stamp(artist="A", festival="F", date="d", year="y", stage="s", venue="v")
    inject_poster_stamp(p, stamp)
    assert read_poster_stamp(p) == stamp
    with Image.open(p) as im:
        assert im.size == (1000, 1500)


def test_read_poster_stamp_missing_file(tmp_path):
    assert read_poster_stamp(tmp_path / "nope.jpg") is None
