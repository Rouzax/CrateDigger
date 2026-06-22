from PIL import Image

from festival_organizer.poster import (
    COVER_POSTER_VERSION,
    build_cover_stamp,
    inject_poster_stamp,
    read_poster_stamp,
)


def _make_jpeg(path):
    Image.new("RGB", (1000, 1500), (10, 10, 20)).save(str(path), "JPEG", quality=95)


def test_build_cover_stamp_is_deterministic():
    a = build_cover_stamp(
        artist="AFROJACK",
        festival="UMF Miami",
        date="2026-03-29",
        year="2026",
        stage="Mainstage",
        venue="",
    )
    b = build_cover_stamp(
        artist="AFROJACK",
        festival="UMF Miami",
        date="2026-03-29",
        year="2026",
        stage="Mainstage",
        venue="",
    )
    assert a == b and isinstance(a, bytes)
    assert str(COVER_POSTER_VERSION).encode() in a


def test_stamp_changes_when_a_field_changes():
    base = dict(artist="A", festival="F", date="d", year="y", stage="s", venue="v")
    assert build_cover_stamp(**base, artists_1001tl=None) != build_cover_stamp(
        **{**base, "festival": "F2"}, artists_1001tl=None
    )


def test_inject_and_read_round_trip(tmp_path):
    p = tmp_path / "x-poster.jpg"
    _make_jpeg(p)
    assert read_poster_stamp(p) is None  # freshly rendered: no stamp
    stamp = build_cover_stamp(
        artist="A", festival="F", date="d", year="y", stage="s", venue="v"
    )
    inject_poster_stamp(p, stamp)
    assert read_poster_stamp(p) == stamp
    with Image.open(p) as im:
        assert im.size == (1000, 1500)


def test_read_poster_stamp_missing_file(tmp_path):
    assert read_poster_stamp(tmp_path / "nope.jpg") is None


def test_read_poster_stamp_non_jpeg(tmp_path):
    p = tmp_path / "not.jpg"
    p.write_bytes(b"PNG-ish bytes, definitely not a jpeg")
    assert read_poster_stamp(p) is None


def test_stamp_changes_when_billed_list_changes_same_display():
    # B: rendered lines differ (2 acts vs 3) even though the display string is held constant.
    base = dict(
        artist="ignored", festival="F", date="d", year="y", stage="s", venue="v"
    )
    two = build_cover_stamp(**base, artists_1001tl=["A", "B"])
    three = build_cover_stamp(**base, artists_1001tl=["A", "B", "C"])
    assert two != three


def test_stamp_ignores_display_enrichment_when_billed_list_present():
    # C: same billed list -> same rendered lines -> same stamp, regardless of display enrichment.
    bare = build_cover_stamp(
        artist="Everything Always",
        festival="F",
        date="d",
        year="y",
        stage="s",
        venue="v",
        artists_1001tl=["Everything Always"],
    )
    enriched = build_cover_stamp(
        artist="Everything Always (Dom Dolla & John Summit)",
        festival="F",
        date="d",
        year="y",
        stage="s",
        venue="v",
        artists_1001tl=["Everything Always"],
    )
    assert bare == enriched


def test_stamp_tracks_display_for_non_1001tl():
    # Fallback: no billed list -> display still drives the stamp.
    base = dict(festival="F", date="d", year="y", stage="s", venue="v")
    assert build_cover_stamp(
        artist="DJ One", **base, artists_1001tl=None
    ) != build_cover_stamp(artist="DJ Two", **base, artists_1001tl=None)


def test_inject_is_idempotent_no_accumulation(tmp_path):
    p = tmp_path / "x-poster.jpg"
    _make_jpeg(p)
    s1 = build_cover_stamp(
        artist="A", festival="F", date="d", year="y", stage="s", venue="v"
    )
    inject_poster_stamp(p, s1)
    size_after_first = p.stat().st_size
    s2 = build_cover_stamp(
        artist="B", festival="F", date="d", year="y", stage="s", venue="v"
    )
    inject_poster_stamp(p, s2)
    # read returns the latest stamp, and the file did not grow by a second marker
    assert read_poster_stamp(p) == s2
    assert (
        p.stat().st_size == size_after_first
    )  # same stamp length -> identical size, no accumulation
    with Image.open(p) as im:
        assert im.size == (1000, 1500)
