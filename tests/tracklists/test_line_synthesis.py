"""Unit tests for export-line synthesis from parsed page tracks."""

from festival_organizer.tracklists.api import (
    Track,
    _line_text,
    _synthesize_export_lines,
)


def _t(start_s=0, text="A - B", **kw):
    return Track(
        start_ms=start_s * 1000,
        raw_text=text,
        artist_slugs=[],
        genres=[],
        **kw,
    )


def test_line_text_appends_qualifier_then_label():
    t = _t(text="Afrojack - Pacha On Acid", qualifier="(ID Remix)", label_full="WALL")
    assert _line_text(t) == "Afrojack - Pacha On Acid (ID Remix) [WALL]"


def test_line_text_plain_when_no_extras():
    assert _line_text(_t(text="A - B")) == "A - B"


def test_synthesize_simple_timed_lines():
    tracks = [_t(0, "A - B"), _t(145, "C - D", label_full="STMPD")]
    assert _synthesize_export_lines(tracks) == [
        "[00:00:00.000] A - B",
        "[00:02:25.000] C - D [STMPD]",
    ]


def test_synthesize_includes_mashup_mains():
    tracks = [_t(0, "A - B"), _t(100, "A vs. C - B vs. D (A Mashup)", is_mashup=True)]
    lines = _synthesize_export_lines(tracks)
    assert lines[1] == "[00:01:40.000] A vs. C - B vs. D (A Mashup)"


def test_synthesize_excludes_overlays_and_subcomponents():
    tracks = [
        _t(0, "A - B"),
        _t(30, "w/ track", is_overlay=True),
        _t(0, "component", is_subcomponent=True),
    ]
    assert _synthesize_export_lines(tracks) == ["[00:00:00.000] A - B"]


def test_synthesize_first_uncued_main_emits_at_zero():
    tracks = [_t(0, "Opener - X", cue_unset=True), _t(145, "A - B")]
    assert _synthesize_export_lines(tracks) == [
        "[00:00:00.000] Opener - X",
        "[00:02:25.000] A - B",
    ]


def test_synthesize_drops_later_uncued_mains():
    tracks = [_t(12, "A - B"), _t(0, "Uncued - X", cue_unset=True), _t(145, "C - D")]
    assert _synthesize_export_lines(tracks) == [
        "[00:00:12.000] A - B",
        "[00:02:25.000] C - D",
    ]


def test_synthesize_all_uncued_emits_numbered_lines():
    tracks = [
        _t(0, "A - B", cue_unset=True),
        _t(0, "C - D", cue_unset=True),
    ]
    assert _synthesize_export_lines(tracks) == ["1. A - B", "2. C - D"]


def test_synthesize_empty_tracks_gives_empty_lines():
    assert _synthesize_export_lines([]) == []


def test_synthesize_emits_player_markers_on_transitions():
    tracks = [
        _t(0, "P2 opener", player=2),
        _t(145, "P2 second", player=2),
        _t(1, "P1 opener", player=1),
        _t(3298, "P2 again", player=2),
    ]
    assert _synthesize_export_lines(tracks) == [
        "Player 2",
        "[00:00:00.000] P2 opener",
        "[00:02:25.000] P2 second",
        "Player 1",
        "[00:00:01.000] P1 opener",
        "Player 2",
        "[00:54:58.000] P2 again",
    ]


def test_synthesize_no_markers_for_single_unmarked_timeline():
    # Two ytPlayer sources can share one unmarked timeline: every Track
    # keeps player=0 and no markers may be emitted (prod case 2wrmg6f1).
    tracks = [_t(0, "A - B", player=0), _t(145, "C - D", player=0)]
    lines = _synthesize_export_lines(tracks)
    assert all(not ln.startswith("Player ") for ln in lines)
