"""Regression tests for the canonical ``Artist - Title`` splitter.

The boundary is the FIRST ``" - "``. 1001TL titles frequently contain their own
``" - "`` (subtitles, "- Extended Mix", "- Radio Edit", "... reimagined"), so
splitting on the last separator spills title text into the artist field. Mashup
acts are joined with ``" vs. "`` rather than ``" - "``, so the first separator is
still the artist/title boundary for composites.
"""

from festival_organizer.tracklists.api import split_artist_title


def test_plain_artist_title():
    assert split_artist_title("4B - Bass Drop") == ("4B", "Bass Drop")


def test_title_with_embedded_separator_splits_on_first():
    raw = (
        "Kölsch ft. Troels Abrahamsen - "
        "All that Matters (Symphony of Unity - strings reimagined)"
    )
    assert split_artist_title(raw) == (
        "Kölsch ft. Troels Abrahamsen",
        "All that Matters (Symphony of Unity - strings reimagined)",
    )


def test_extended_mix_suffix_stays_in_title():
    assert split_artist_title("Some Artist - Some Track - Extended Mix") == (
        "Some Artist",
        "Some Track - Extended Mix",
    )


def test_mashup_vs_acts_keep_first_dash_as_boundary():
    assert split_artist_title("A vs. B - Title (Mashup)") == (
        "A vs. B",
        "Title (Mashup)",
    )


def test_no_separator_is_all_title():
    assert split_artist_title("ID") == ("", "ID")


def test_hyphenated_name_without_spaces_is_not_a_boundary():
    # 1001TL hyphenated names carry no surrounding spaces, so they never look
    # like the " - " separator.
    assert split_artist_title("Jean-Michel Jarre - Oxygène") == (
        "Jean-Michel Jarre",
        "Oxygène",
    )


def test_strips_surrounding_whitespace():
    assert split_artist_title("  Artist  -  Title  ") == ("Artist", "Title")
