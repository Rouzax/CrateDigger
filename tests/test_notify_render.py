from pathlib import Path

from festival_organizer.notify.models import EmailSet, RunReport, UpdateInfo
from festival_organizer.notify.render import render


def _fest(artist, event, year, genres, metric):
    return EmailSet(artist=artist, event=event, year=year, note="",
                    genres=genres, metric=metric, poster_path=Path("/x.jpg"),
                    kind="festival_set")


def _report(sets, update=None):
    return RunReport(channel="new_sets", sets=sets, update=update,
                     stats={"added": len(sets), "up_to_date": 0, "errors": 0},
                     host="mediabox", timestamp="11 Jun 2026, 22:14")


def test_render_groups_by_event_and_includes_metric():
    report = _report([
        _fest("Eric Prydz", "UMF Miami", "2026", ["Techno"], "19 tracks"),
        _fest("Madeon", "Coachella", "2026", ["Pop"], "18 tracks"),
    ])
    out = render(report, thumbs={})
    assert "UMF Miami" in out.html
    assert "Coachella" in out.html
    assert "Eric Prydz" in out.html
    assert "19 tracks" in out.html
    assert "Eric Prydz" in out.text
    assert out.subject.startswith("CrateDigger:")


def test_render_concerts_section_grouped_by_artist():
    concert = EmailSet(artist="Coldplay", event="", year="2023", note="",
                       genres=["Pop"], metric="", poster_path=None, kind="concert_film")
    out = render(_report([concert]), thumbs={})
    assert "Concerts & Albums" in out.html
    assert "Coldplay" in out.html


def test_render_update_banner_only_when_behind():
    behind = _report([_fest("A", "E", "2026", [], "")],
                     update=UpdateInfo("0.19.9", "0.20.0", True))
    current = _report([_fest("A", "E", "2026", [], "")],
                      update=UpdateInfo("0.20.0", "0.20.0", False))
    assert "update available" in render(behind, thumbs={}).html.lower()
    assert "update available" not in render(current, thumbs={}).html.lower()


def test_render_embeds_thumbnail_cid_and_returns_image():
    report = _report([_fest("Eric Prydz", "UMF Miami", "2026", [], "19 tracks")])
    out = render(report, thumbs={0: ("poster0", b"jpegbytes")})
    assert "cid:poster0" in out.html
    assert ("poster0", b"jpegbytes") in out.images


def test_render_updated_channel_header():
    report = RunReport(channel="updated_sets",
                       sets=[_fest("Armin", "ASOT", "2026", [], "41 chapters")],
                       update=None, stats={}, host="mediabox", timestamp="t")
    out = render(report, thumbs={})
    assert "updated" in out.subject.lower()
    assert "41 chapters" in out.html
