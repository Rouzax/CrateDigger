"""Tests for festival_organizer.tracklists.overlays."""

from festival_organizer.tracklists.api import Track
from festival_organizer.tracklists.chapters import Chapter, _ms_to_timestamp
from festival_organizer.tracklists.overlays import (
    AssembledChapter,
    assemble,
    combined_title,
)


def _track(raw_text: str, label: str = "") -> Track:
    return Track(
        start_ms=0,
        raw_text=raw_text,
        artist_slugs=[],
        genres=[],
        label=label,
    )


def test_single_member_artist_title_label() -> None:
    member = _track("4B - Bass Drop", label="DIM MAK")
    assert combined_title(member, [member]) == "4B - Bass Drop [DIM MAK]"


def test_single_member_no_label_omits_brackets() -> None:
    member = _track("4B - Bass Drop")
    assert combined_title(member, [member]) == "4B - Bass Drop"


def test_two_members_vs_title_and_labels() -> None:
    a = _track("Artist A - Title A", label="L1")
    b = _track("Artist B - Title B", label="L2")
    assert (
        combined_title(a, [a, b])
        == "Artist A vs. Artist B - Title A vs. Title B [L1/L2]"
    )


def test_duplicate_artist_deduped_order_preserving() -> None:
    a = _track("Marshmello - Alone", label="Joytime")
    b = _track("Marshmello - Happier", label="Joytime")
    # Artist deduped to one Marshmello; titles kept in order; label deduped.
    assert combined_title(a, [a, b]) == "Marshmello - Alone vs. Happier [Joytime]"


def test_duplicate_label_deduped() -> None:
    a = _track("Artist A - Title A", label="STMPD")
    b = _track("Artist B - Title B", label="STMPD")
    assert (
        combined_title(a, [a, b])
        == "Artist A vs. Artist B - Title A vs. Title B [STMPD]"
    )


def test_missing_label_omitted_when_no_labels() -> None:
    a = _track("Artist A - Title A")
    b = _track("Artist B - Title B")
    assert combined_title(a, [a, b]) == "Artist A vs. Artist B - Title A vs. Title B"


def test_member_without_separator_keeps_raw_text_as_title() -> None:
    # No " - " in raw_text: artist empty, whole raw_text is the title segment.
    member = _track("ID")
    assert combined_title(member, [member]) == "ID"


def test_member_without_separator_in_combination() -> None:
    a = _track("Artist A - Title A", label="L1")
    b = _track("ID")
    # b has no artist; only a contributes an artist segment.
    assert combined_title(a, [a, b]) == "Artist A - Title A vs. ID [L1]"


def test_split_on_last_separator() -> None:
    # Artist is everything before the LAST " - "; title is the remainder.
    member = _track("A - B - Title", label="L")
    assert combined_title(member, [member]) == "A - B - Title [L]"


def test_partial_labels_only_distinct_present() -> None:
    a = _track("Artist A - Title A", label="L1")
    b = _track("Artist B - Title B")  # no label
    assert (
        combined_title(a, [a, b]) == "Artist A vs. Artist B - Title A vs. Title B [L1]"
    )


def test_primary_none_uses_members_in_order() -> None:
    a = _track("Artist A - Title A", label="L1")
    b = _track("Artist B - Title B", label="L2")
    assert (
        combined_title(None, [a, b])
        == "Artist A vs. Artist B - Title A vs. Title B [L1/L2]"
    )


# --- assemble() ----------------------------------------------------------


def _anchor_chapter(start_ms: int, raw_text: str) -> Chapter:
    return Chapter(timestamp=_ms_to_timestamp(start_ms), title=raw_text)


def _anchor_track(start_ms: int, raw_text: str) -> Track:
    return Track(
        start_ms=start_ms,
        raw_text=raw_text,
        artist_slugs=[],
        genres=[],
    )


def _overlay(start_ms: int, raw_text: str, label: str = "") -> Track:
    return Track(
        start_ms=start_ms,
        raw_text=raw_text,
        artist_slugs=[],
        genres=[],
        label=label,
        is_overlay=True,
    )


def _subcomponent(start_ms: int, raw_text: str, group_id: int) -> Track:
    return Track(
        start_ms=start_ms,
        raw_text=raw_text,
        artist_slugs=[],
        genres=[],
        is_overlay=True,
        is_subcomponent=True,
        group_id=group_id,
    )


def test_timed_overlay_within_fold_seconds_becomes_contributor() -> None:
    host = _anchor_track(10_000, "Host - Main")
    overlay = _overlay(15_000, "Other - Layered")
    anchors = [_anchor_chapter(10_000, "Host - Main")]
    result = assemble(anchors, {10_000: host}, [host, overlay], fold_seconds=20)
    assert len(result) == 1
    chapter = result[0]
    assert chapter.start_ms == 10_000
    assert chapter.primary is host
    assert chapter.contributors == [overlay]
    # Title is vs.-combined: host + overlay.
    assert chapter.title == "Host vs. Other - Main vs. Layered"


def test_timed_overlay_beyond_fold_seconds_breaks_out() -> None:
    host = _anchor_track(10_000, "Host - Main")
    overlay = _overlay(40_000, "Other - Layered")
    anchors = [_anchor_chapter(10_000, "Host - Main")]
    result = assemble(anchors, {10_000: host}, [host, overlay], fold_seconds=20)
    assert len(result) == 2
    assert result[0].primary is host
    assert result[0].contributors == []
    breakout = result[1]
    assert breakout.start_ms == 40_000
    assert breakout.primary is None
    assert breakout.contributors == [overlay]
    assert breakout.title == "Other - Layered"


def test_second_breakout_within_fold_joins_first() -> None:
    host = _anchor_track(10_000, "Host - Main")
    first = _overlay(40_000, "Other - One")
    second = _overlay(45_000, "Third - Two")
    anchors = [_anchor_chapter(10_000, "Host - Main")]
    result = assemble(anchors, {10_000: host}, [host, first, second], fold_seconds=20)
    assert len(result) == 2
    breakout = result[1]
    assert breakout.start_ms == 40_000
    assert breakout.contributors == [first, second]


def test_second_breakout_beyond_fold_is_separate() -> None:
    host = _anchor_track(10_000, "Host - Main")
    first = _overlay(40_000, "Other - One")
    second = _overlay(70_000, "Third - Two")
    anchors = [_anchor_chapter(10_000, "Host - Main")]
    result = assemble(anchors, {10_000: host}, [host, first, second], fold_seconds=20)
    assert len(result) == 3
    assert result[1].start_ms == 40_000
    assert result[1].contributors == [first]
    assert result[2].start_ms == 70_000
    assert result[2].contributors == [second]


def test_positionless_overlay_folds_into_current_anchor() -> None:
    host = _anchor_track(10_000, "Host - Main")
    overlay = _overlay(0, "Other - Acapella")
    anchors = [_anchor_chapter(10_000, "Host - Main")]
    result = assemble(anchors, {10_000: host}, [host, overlay], fold_seconds=20)
    assert len(result) == 1
    assert result[0].contributors == [overlay]


def test_overlay_at_exact_host_second_folds_no_duplicate() -> None:
    host = _anchor_track(10_000, "Host - Main")
    overlay = _overlay(10_000, "Other - Layered")
    anchors = [_anchor_chapter(10_000, "Host - Main")]
    result = assemble(anchors, {10_000: host}, [host, overlay], fold_seconds=20)
    assert len(result) == 1
    assert result[0].start_ms == 10_000
    assert result[0].contributors == [overlay]


def test_subcomponents_attach_to_matching_group_id_never_a_chapter() -> None:
    host = _anchor_track(10_000, "Host - Mashup")
    host.group_id = 7
    host.is_mashup = True
    sub_a = _subcomponent(0, "Comp A - Part A", group_id=7)
    sub_b = _subcomponent(0, "Comp B - Part B", group_id=7)
    anchors = [_anchor_chapter(10_000, "Host - Mashup")]
    result = assemble(anchors, {10_000: host}, [host, sub_a, sub_b], fold_seconds=20)
    assert len(result) == 1
    chapter = result[0]
    assert chapter.contributors == [sub_a, sub_b]
    # Sub-components are metadata-only: never in the title.
    assert chapter.title == "Host - Mashup"


def test_subcomponent_with_no_matching_anchor_is_skipped() -> None:
    host = _anchor_track(10_000, "Host - Main")
    sub = _subcomponent(0, "Comp - Part", group_id=99)
    anchors = [_anchor_chapter(10_000, "Host - Main")]
    result = assemble(anchors, {10_000: host}, [host, sub], fold_seconds=20)
    assert len(result) == 1
    assert result[0].contributors == []


def test_positionless_overlay_before_any_anchor_is_dropped() -> None:
    overlay = _overlay(0, "Other - Acapella")
    host = _anchor_track(10_000, "Host - Main")
    anchors = [_anchor_chapter(10_000, "Host - Main")]
    # Positionless overlay has start_ms 0, so it sorts before the anchor and
    # there is no current anchor yet; it is dropped (no contributor, no chapter).
    result = assemble(anchors, {10_000: host}, [overlay, host], fold_seconds=20)
    assert len(result) == 1
    assert result[0].contributors == []


def test_chapters_returned_in_ascending_start_ms_order() -> None:
    host_a = _anchor_track(10_000, "A - One")
    host_b = _anchor_track(100_000, "B - Two")
    breakout = _overlay(40_000, "C - Mid")
    anchors = [
        _anchor_chapter(10_000, "A - One"),
        _anchor_chapter(100_000, "B - Two"),
    ]
    result = assemble(
        anchors,
        {10_000: host_a, 100_000: host_b},
        [host_a, breakout, host_b],
        fold_seconds=20,
    )
    starts = [c.start_ms for c in result]
    assert starts == sorted(starts)
    assert starts == [10_000, 40_000, 100_000]


def test_2wtsw119_player1_fold_20() -> None:
    anchor_specs = [
        (1000, "Martin Garrix & Ed Sheeran - Repeat It"),
        (197000, "Ed Sheeran - Shape Of You"),
        (326000, "Martin Garrix ft. JRM - These Are The Times"),
        (418000, "Rudimental ft. Ed Sheeran - Bloodstream"),
        (624000, "Ed Sheeran - Galway Girl"),
        (733000, "Dimitri Vegas & Like Mike & Martin Garrix - Tremor"),
        (874000, "Martin Garrix ft. Mike Yung - Dreamer"),
        (1003000, "Martin Garrix & Sem Vox ft. Jaimes - Gravity"),
        (1184000, "Martin Garrix & Matisse & Sadko ft. BARBZ - Butterflies"),
        (1400000, "Lewis Capaldi - Someone You Loved"),
        (1657000, "Martin Garrix & Lloyiso - Real Love"),
        (1770000, "Martin Garrix ft. John Martin - Higher Ground"),
        (2020000, "Martin Garrix & Ed Sheeran - Repeat It"),
    ]
    overlay_specs = [
        (280000, "Martin Garrix & Mesto - Limitless"),
        (326000, "Ed Sheeran - Photograph"),
        (463000, "Martin Garrix & Arcando ft. Bonn - Set Me Free"),
        (697000, "Martin Garrix & Troye Sivan - There For You"),
        (733000, "Ed Sheeran - Shivers"),
        (890000, "Ed Sheeran - Sapphire"),
        (1016000, "Ed Sheeran - Perfect"),
        (1184000, "Ed Sheeran - Bad Habits"),
        (1400000, "Ed Sheeran - Castle On The Hill"),
        (1657000, "Ed Sheeran - Beautiful People"),
        (1775000, "Ed Sheeran - Celestial"),
    ]
    anchor_tracks = {ms: _anchor_track(ms, raw_text) for ms, raw_text in anchor_specs}
    anchors = [_anchor_chapter(ms, raw_text) for ms, raw_text in anchor_specs]
    overlays = [_overlay(ms, raw_text) for ms, raw_text in overlay_specs]
    tracks = list(anchor_tracks.values()) + overlays

    result = assemble(anchors, anchor_tracks, tracks, fold_seconds=20)

    assert len(result) == 16

    starts = [c.start_ms for c in result]
    assert starts == sorted(starts)

    by_start = {c.start_ms: c for c in result}

    # Three breakouts: own chapters, primary None.
    for breakout_ms in (280000, 463000, 697000):
        assert breakout_ms in by_start
        assert by_start[breakout_ms].primary is None
    assert by_start[280000].title == "Martin Garrix & Mesto - Limitless"
    assert by_start[463000].title == "Martin Garrix & Arcando ft. Bonn - Set Me Free"
    assert by_start[697000].title == "Martin Garrix & Troye Sivan - There For You"

    # Folds: contributor of the matching host, title contains "vs. <overlay title>".
    folds = {
        326000: "These Are The Times vs. Photograph",
        874000: "Sapphire",
        1003000: "Perfect",
        1770000: "Celestial",
        733000: "Shivers",
        1184000: "Bad Habits",
        1400000: "Castle On The Hill",
        1657000: "Beautiful People",
    }
    for host_ms, needle in folds.items():
        assert host_ms in by_start
        assert by_start[host_ms].primary is not None
        assert needle in by_start[host_ms].title, (
            host_ms,
            by_start[host_ms].title,
        )


def test_assembled_chapter_default_fields() -> None:
    chapter = AssembledChapter(start_ms=0, title="t", primary=None)
    assert chapter.contributors == []
    assert chapter.language == "eng"
