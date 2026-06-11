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
                     timestamp="11 Jun 2026, 22:14")


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
                       update=None, stats={}, timestamp="t")
    out = render(report, thumbs={})
    assert "updated" in out.subject.lower()
    assert "41 chapters" in out.html


def test_render_subject_event_pluralization():
    # 3 sets across 1 event -> "1 event" (singular), not "1 events"
    one_event = _report([
        _fest("A", "UMF Miami", "2026", [], ""),
        _fest("B", "UMF Miami", "2026", [], ""),
        _fest("C", "UMF Miami", "2026", [], ""),
    ])
    assert "across 1 event" in render(one_event, thumbs={}).subject
    assert "1 events" not in render(one_event, thumbs={}).subject

    # 2 sets across 2 events -> "2 events" (plural)
    two_events = _report([
        _fest("A", "UMF Miami", "2026", [], ""),
        _fest("B", "Coachella", "2026", [], ""),
    ])
    assert "across 2 events" in render(two_events, thumbs={}).subject


def test_render_caps_sets_and_shows_overflow():
    from festival_organizer.notify.render import MAX_SETS
    sets = [_fest(f"Artist{i}", "UMF Miami", "2026", [], "") for i in range(MAX_SETS + 5)]
    out = render(_report(sets), thumbs={})
    # heading shows true total
    assert f"{MAX_SETS + 5} new set" in out.html
    # overflow indicator present
    assert "5 more" in out.html
    # only MAX_SETS rows rendered: count the row tables (each row is one <table ... margin-bottom:12px)
    assert out.html.count("margin-bottom:12px") == MAX_SETS


def test_render_escapes_user_fields():
    s = EmailSet("<script>x</script>", "UMF & Friends", "2026", "a<b",
                 ["<i>g</i>"], "1 & 2", None, "festival_set")
    out = render(_report([s]), thumbs={})
    assert "<script>x</script>" not in out.html
    assert "&lt;script&gt;" in out.html
    assert "UMF &amp; Friends" in out.html   # event escaped at call site


def test_render_updated_footer_uses_identify_stats():
    report = RunReport(channel="updated_sets",
                       sets=[_fest("A", "ASOT", "2026", [], "41 chapters")],
                       update=None,
                       stats={"updated": 1, "up_to_date": 5, "skipped": 2, "error": 1},
                       timestamp="t")
    out = render(report, thumbs={})
    assert "1 updated" in out.html
    assert "5 unchanged" in out.html
    assert "3 skipped" in out.html        # skipped + error combined
    assert "added" not in out.html        # no organize tally on the updated channel
    assert "mediabox" not in out.html     # hostname removed


def test_render_has_full_width_dark_wrapper_and_no_host():
    out = render(_report([_fest("A", "E", "2026", [], "")]), thumbs={})
    assert 'bgcolor="#05060a"' in out.html   # full-width dark page background
    assert "mediabox" not in out.html        # host removed from header
    assert "mediabox" not in out.text        # and from the text part


def test_render_poster_column_is_proportional_not_fixed():
    out = render(_report([_fest("A", "E", "2026", [], "19 tracks")]),
                 thumbs={0: ("poster0", b"x")})
    assert 'width="25%"' in out.html   # proportional poster column scales with width
    assert 'width="75%"' in out.html   # text column
    assert "140px" not in out.html     # no fixed-pixel poster width remains


def test_render_row_repeats_event_on_card():
    # The event/place should appear on the card line itself, not only the group header.
    out = render(_report([_fest("Eric Prydz", "UMF Miami", "2026", ["Techno"], "19 tracks")]),
                 thumbs={})
    # "<event> &middot; " only appears as the row's metadata prefix; the group
    # header renders "UMF Miami" followed by a count span, not a middot.
    assert "UMF Miami &middot; " in out.html


def test_render_footer_muted_color_is_wcag_aa():
    # The tertiary text color (footer tally, event count) must be the AA-compliant
    # value, not the old #555570 which failed WCAG AA at 2.81:1.
    out = render(_report([_fest("A", "E", "2026", [], "")]), thumbs={})
    assert "#7a7a93" in out.html
    assert "#555570" not in out.html
