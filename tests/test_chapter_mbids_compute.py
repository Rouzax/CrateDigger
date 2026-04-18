"""Pure computation of per-chapter MUSICBRAINZ_ARTISTIDS from CRATEDIGGER_TRACK_PERFORMER_NAMES."""
import logging

from festival_organizer.fanart import compute_chapter_mbid_tags, resolve_mbids_aligned


def test_all_resolved():
    chapter_tags = {111: {"CRATEDIGGER_TRACK_PERFORMER_NAMES": "Afrojack|Oliver Heldens"}}

    def resolver(name):
        return {"Afrojack": "A", "Oliver Heldens": "O"}[name]

    out = compute_chapter_mbid_tags(chapter_tags, resolver)
    assert out == {111: {"MUSICBRAINZ_ARTISTIDS": "A|O"}}


def test_partial_resolved_preserves_empty_slots():
    chapter_tags = {111: {"CRATEDIGGER_TRACK_PERFORMER_NAMES": "Afrojack|ID|Oliver Heldens"}}

    def resolver(name):
        return {"Afrojack": "A", "Oliver Heldens": "O"}.get(name)

    out = compute_chapter_mbid_tags(chapter_tags, resolver)
    assert out == {111: {"MUSICBRAINZ_ARTISTIDS": "A||O"}}


def test_all_missing_still_emits_empty_slots():
    # Preserves downstream zip invariant: slot count must match NAMES count.
    chapter_tags = {111: {"CRATEDIGGER_TRACK_PERFORMER_NAMES": "ID|ID"}}

    def resolver(name):
        return None

    out = compute_chapter_mbid_tags(chapter_tags, resolver)
    assert out == {111: {"MUSICBRAINZ_ARTISTIDS": "|"}}


def test_skips_chapter_without_performer_names():
    # Legacy chapter with no CRATEDIGGER_TRACK_PERFORMER_NAMES: skip without resolving.
    chapter_tags = {111: {"CRATEDIGGER_TRACK_PERFORMER": "Afrojack"}}

    def resolver(name):
        raise AssertionError("must not be called")

    assert compute_chapter_mbid_tags(chapter_tags, resolver) == {}


def test_unique_names_looked_up_once_across_chapters():
    chapter_tags = {
        111: {"CRATEDIGGER_TRACK_PERFORMER_NAMES": "Afrojack|Oliver Heldens"},
        222: {"CRATEDIGGER_TRACK_PERFORMER_NAMES": "Afrojack|Tiësto"},
    }
    calls = []

    def resolver(name):
        calls.append(name)
        return {"Afrojack": "A", "Oliver Heldens": "O", "Tiësto": "T"}[name]

    compute_chapter_mbid_tags(chapter_tags, resolver)
    # Afrojack appears in both chapters but must only be resolved once.
    assert sorted(calls) == ["Afrojack", "Oliver Heldens", "Tiësto"]


def test_unresolved_logged_once_per_name(caplog):
    caplog.set_level(logging.INFO, logger="festival_organizer.fanart")
    chapter_tags = {
        111: {"CRATEDIGGER_TRACK_PERFORMER_NAMES": "Mystery DJ|Mystery DJ"},
        222: {"CRATEDIGGER_TRACK_PERFORMER_NAMES": "Mystery DJ"},
    }

    def resolver(name):
        return None

    compute_chapter_mbid_tags(chapter_tags, resolver)
    mystery_warnings = [r for r in caplog.records if "Mystery DJ" in r.message]
    assert len(mystery_warnings) == 1


def test_empty_input_returns_empty():
    assert compute_chapter_mbid_tags({}, lambda n: "x") == {}


def test_mbids_for_chapters_preserved_even_when_other_chapters_have_no_names():
    # Output contains only chapters that had CRATEDIGGER_TRACK_PERFORMER_NAMES; others are omitted.
    chapter_tags = {
        111: {"CRATEDIGGER_TRACK_PERFORMER_NAMES": "Afrojack"},
        222: {"CRATEDIGGER_TRACK_PERFORMER": "No Names Here"},
        333: {"CRATEDIGGER_TRACK_PERFORMER_NAMES": "Oliver Heldens"},
    }

    def resolver(name):
        return {"Afrojack": "A", "Oliver Heldens": "O"}[name]

    out = compute_chapter_mbid_tags(chapter_tags, resolver)
    assert out == {
        111: {"MUSICBRAINZ_ARTISTIDS": "A"},
        333: {"MUSICBRAINZ_ARTISTIDS": "O"},
    }


# --- resolve_mbids_aligned: the shared helper ---------------------------------

def test_resolve_mbids_aligned_empty():
    assert resolve_mbids_aligned([], lambda n: "x") == []


def test_resolve_mbids_aligned_all_miss_preserves_slots():
    out = resolve_mbids_aligned(["A", "B", "C"], lambda n: None)
    assert out == ["", "", ""]


def test_resolve_mbids_aligned_mixed_hits_and_misses():
    def resolver(name):
        return {"A": "mbid_a", "C": "mbid_c"}.get(name)
    out = resolve_mbids_aligned(["A", "B", "C"], resolver)
    assert out == ["mbid_a", "", "mbid_c"]


def test_resolve_mbids_aligned_dedupes_resolver_calls():
    calls = []

    def resolver(name):
        calls.append(name)
        return "x"

    resolve_mbids_aligned(["A", "B", "A", "B", "A"], resolver)
    assert sorted(calls) == ["A", "B"]


def test_resolve_mbids_aligned_warns_once_per_miss(caplog):
    caplog.set_level(logging.INFO, logger="festival_organizer.fanart")
    resolve_mbids_aligned(["Mystery", "Mystery", "Mystery"], lambda n: None)
    mystery_warnings = [r for r in caplog.records if "Mystery" in r.message]
    assert len(mystery_warnings) == 1
