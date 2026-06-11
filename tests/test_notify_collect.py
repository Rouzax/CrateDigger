from pathlib import Path
from types import SimpleNamespace

from festival_organizer.notify.collect import collect_new_sets, format_duration
from festival_organizer.notify.models import UpdateInfo
from tests.conftest import make_mediafile


def _op(name, target=None):
    return SimpleNamespace(name=name, target=target)


def _res(name, status):
    return SimpleNamespace(name=name, status=status, detail="", display_name=name)


def test_format_duration():
    assert format_duration(6120) == "1h 42m"
    assert format_duration(3600) == "1h 0m"
    assert format_duration(900) == "15m"
    assert format_duration(None) == ""


def test_collect_new_sets_picks_only_done(tmp_path):
    poster = tmp_path / "2026 - Eric Prydz - UMF Miami-poster.jpg"
    poster.write_bytes(b"x")
    target = tmp_path / "2026 - Eric Prydz - UMF Miami.mkv"

    mf_new = make_mediafile(source_path=target, artist="Eric Prydz", festival="UMF Miami",
                            year="2026", stage="Resistance", genres=["Techno"],
                            duration_seconds=5400.0, content_type="festival_set")
    mf_skip = make_mediafile(source_path=tmp_path / "s.mkv", artist="Skip", year="2025")

    pipeline_files = [
        (target, mf_new, [_op("organize", target)]),
        (tmp_path / "s.mkv", mf_skip, [_op("organize", tmp_path / "s.mkv")]),
    ]
    all_results = [
        [_res("organize", "done")],
        [_res("organize", "up_to_date")],
    ]

    report = collect_new_sets(
        pipeline_files, all_results,
        update=UpdateInfo("0.19.9", "0.20.0", True),
        stats={"added": 1, "up_to_date": 1, "errors": 0},
        host="mediabox", timestamp="11 Jun 2026",
        count_chapters=lambda p: 19,
    )
    assert report.channel == "new_sets"
    assert len(report.sets) == 1
    s = report.sets[0]
    assert s.artist == "Eric Prydz"
    assert s.event == "UMF Miami"
    assert s.note == "Resistance"
    assert s.metric == "19 tracks · 1h 30m"
    assert s.poster_path == poster
    assert s.kind == "festival_set"


def test_collect_new_sets_missing_poster_sets_none(tmp_path):
    target = tmp_path / "x.mkv"
    mf = make_mediafile(source_path=target, artist="A", year="2026", duration_seconds=None)
    report = collect_new_sets(
        [(target, mf, [_op("organize", target)])],
        [[_res("organize", "done")]],
        update=None, stats={}, host="h", timestamp="t",
        count_chapters=lambda p: None,
    )
    assert report.sets[0].poster_path is None
    assert report.sets[0].metric == ""   # no chapters, no duration
