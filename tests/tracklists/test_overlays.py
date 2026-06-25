"""Tests for festival_organizer.tracklists.overlays."""

from festival_organizer.tracklists.api import Track
from festival_organizer.tracklists.overlays import combined_title


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
