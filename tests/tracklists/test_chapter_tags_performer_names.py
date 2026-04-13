"""PERFORMER_NAMES per-chapter tag: pipe-joined display names aligned with SLUGS."""
from festival_organizer.tracklists.api import Track
from festival_organizer.tracklists.chapters import Chapter, _build_chapter_tags_map


def _chapter(ts="00:00:00", title="t"):
    return Chapter(timestamp=ts, title=title)


def test_performer_names_emitted_aligned_with_slugs():
    track = Track(
        raw_text="Afrojack & Oliver Heldens - Happy",
        title="Happy",
        label="",
        genres=[],
        artist_slugs=["afrojack", "oliver-heldens"],
        start_ms=0,
        artist_names=["Afrojack", "Oliver Heldens"],
    )
    out = _build_chapter_tags_map([_chapter()], [111], [track], dj_cache=None)
    entry = out[111]
    assert entry["PERFORMER_SLUGS"] == "afrojack|oliver-heldens"
    assert entry["PERFORMER_NAMES"] == "Afrojack|Oliver Heldens"
    assert entry["PERFORMER_NAMES"].count("|") == entry["PERFORMER_SLUGS"].count("|")


def test_performer_names_absent_when_parser_did_not_populate():
    # Old tracklists or parser gaps leave artist_names empty; do not emit the tag.
    track = Track(
        raw_text="Afrojack - Happy", title="Happy", label="", genres=[],
        artist_slugs=["afrojack"], start_ms=0, artist_names=[],
    )
    out = _build_chapter_tags_map([_chapter()], [111], [track], dj_cache=None)
    assert "PERFORMER_NAMES" not in out[111]


def test_performer_names_preserves_diacritics():
    track = Track(
        raw_text="Tiësto & Kölsch - Song", title="Song", label="", genres=[],
        artist_slugs=["tiesto", "koelsch"], start_ms=0,
        artist_names=["Tiësto", "Kölsch"],
    )
    out = _build_chapter_tags_map([_chapter()], [111], [track], dj_cache=None)
    assert out[111]["PERFORMER_NAMES"] == "Tiësto|Kölsch"


def test_performer_names_omitted_when_slug_and_name_lengths_mismatch():
    # Alignment invariant is load-bearing for enrich (zips SLUGS|NAMES|MBIDS by index).
    # When parser yields misaligned data, omit NAMES entirely rather than emit something
    # that would silently corrupt downstream zips.
    track = Track(
        raw_text="Afrojack & Oliver Heldens - Happy",
        title="Happy",
        label="",
        genres=[],
        artist_slugs=["afrojack", "oliver-heldens"],
        start_ms=0,
        artist_names=["Afrojack"],  # only one name for two slugs
    )
    out = _build_chapter_tags_map([_chapter()], [111], [track], dj_cache=None)
    entry = out[111]
    assert entry["PERFORMER_SLUGS"] == "afrojack|oliver-heldens"
    assert "PERFORMER_NAMES" not in entry
