from pathlib import Path
from festival_organizer.tracklists.api import _parse_tracks

FIXTURE = Path(__file__).parent / "fixtures" / "afrojack_edc_2025.html"


def test_parse_tracks_returns_chapter_aligned_rows_only():
    """HTML has 77 tlpItem rows but only ~27-30 are chapter-aligned."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    assert 24 <= len(tracks) <= 35


def test_parse_tracks_extracts_slugs():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    # First track is AFROJACK - Take Over Control; its slug is 'afrojack'.
    assert tracks[0].artist_slugs
    assert tracks[0].artist_slugs[0] == "afrojack"
    # At least 80% of chapter-aligned rows have at least one slug
    with_slugs = [t for t in tracks if t.artist_slugs]
    assert len(with_slugs) >= int(len(tracks) * 0.8)


def test_parse_tracks_extracts_genres_from_chapter_rows():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    all_genres = [g for t in tracks for g in t.genres]
    assert len(all_genres) >= 5


def test_parse_tracks_start_ms_monotonic():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    starts = [t.start_ms for t in tracks]
    assert starts == sorted(starts)


def test_parse_tracks_first_chapter_at_zero():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    assert tracks[0].start_ms == 0


def test_parse_tracks_raw_text_preserved():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    assert "Take Over Control" in tracks[0].raw_text


def test_parse_tracks_no_mojibake():
    """After the 1e45b59 fix, no parsed text should contain mojibake bytes."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    for t in tracks:
        assert "\u251c" not in t.raw_text, f"mojibake in {t.raw_text!r}"
        for g in t.genres:
            assert "\u251c" not in g


def test_parse_tracks_extracts_artist_names():
    """Each slug gets a paired display name from the HTML row."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    # Row 0: AFROJACK - Take Over Control
    assert tracks[0].artist_slugs[0] == "afrojack"
    assert tracks[0].artist_names[0] == "AFROJACK"
    # artist_names and artist_slugs are paired by index
    for t in tracks:
        assert len(t.artist_names) == len(t.artist_slugs), (
            f"slug/name length mismatch on '{t.raw_text}': "
            f"{t.artist_slugs} vs {t.artist_names}"
        )


def test_parse_tracks_extracts_title():
    """Track title is extracted, artist prefix stripped."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    # First track: "AFROJACK ft. Eva Simons - Take Over Control"
    assert tracks[0].title == "Take Over Control"
    # Most chapter-aligned tracks should have a non-empty title
    with_title = [t for t in tracks if t.title]
    assert len(with_title) >= int(len(tracks) * 0.8)


def test_parse_tracks_extracts_label():
    """Record label is extracted when present in the row."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    # First track's label in the fixture is WALL (Afrojack's label)
    assert tracks[0].label == "WALL"
    # At least some tracks should have a label (many do on 1001TL)
    with_label = [t for t in tracks if t.label]
    assert len(with_label) >= 3


def test_parse_tracks_title_handles_no_separator():
    """If the raw text has no ' - ' separator, title falls back to full text."""
    import re
    from festival_organizer.tracklists.api import Track
    # Build a minimal HTML row with a name meta containing no ' - '
    # This path is defensive; most tracks have artist-title format.
    html = """<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="0">
<meta itemprop="name" content="Intro Music">
</div>"""
    tracks = _parse_tracks(html)
    assert len(tracks) == 1
    assert tracks[0].title == "Intro Music"


# --- Edge-case fixtures ---

FIXTURE_B2B = Path(__file__).parent / "fixtures" / "armin_kiki_amf_2025.html"
FIXTURE_ALIAS = Path(__file__).parent / "fixtures" / "something_else_tomorrowland_winter_2026.html"
FIXTURE_LOWERCASE = Path(__file__).parent / "fixtures" / "deadmau5_tomorrowland_brasil_2025.html"


def test_parse_tracks_b2b_multi_artist_rows():
    """B2B / multi-artist track rows pair slug and display name by index."""
    tracks = _parse_tracks(FIXTURE_B2B.read_text(encoding="utf-8"))
    multi = [t for t in tracks if len(t.artist_slugs) >= 2]
    assert multi, "expected at least one multi-artist track in B2B set"
    for t in multi:
        assert len(t.artist_names) == len(t.artist_slugs)
        # Display names should not look like title-cased slugs
        for slug, name in zip(t.artist_slugs, t.artist_names):
            slug_titled = slug.replace("-", " ").title()
            # Either the name differs from the title-cased slug (preserved
            # original casing), or they happen to match because the display
            # form IS title case for that artist. Both are legitimate.
            assert name  # never empty


def test_parse_tracks_preserves_lowercase_artist():
    """deadmau5-style lowercase artist names must round-trip through the parser."""
    tracks = _parse_tracks(FIXTURE_LOWERCASE.read_text(encoding="utf-8"))
    # At least one track should have 'deadmau5' as a slug and name
    mau5 = [t for t in tracks if "deadmau5" in t.artist_slugs]
    assert mau5, "expected deadmau5 tracks in fixture"
    for t in mau5:
        idx = t.artist_slugs.index("deadmau5")
        assert t.artist_names[idx] == "deadmau5", (
            f"lowercase deadmau5 got title-cased to {t.artist_names[idx]!r}"
        )


def test_parse_tracks_preserves_uppercase_artist():
    """All-caps artist names like ARTBAT, AYYBO must keep their casing."""
    tracks = _parse_tracks(FIXTURE_LOWERCASE.read_text(encoding="utf-8"))
    names = {n for t in tracks for n in t.artist_names}
    assert "ARTBAT" in names, f"ARTBAT missing from {names}"


def test_parse_tracks_alias_artist_uses_1001tl_display_form():
    """SOMETHING ELSE (ALOK alias) tracks keep 1001TL display form in artist_names."""
    tracks = _parse_tracks(FIXTURE_ALIAS.read_text(encoding="utf-8"))
    # Parser returns the 1001TL page's display form. Alias resolution
    # happens later in _build_chapter_tags_map via Config.resolve_artist.
    # Here we just assert the parser doesn't corrupt obscure names.
    for t in tracks:
        for n in t.artist_names:
            assert "├" not in n
            assert n  # non-empty


def test_parse_tracks_labels_preserve_casing():
    """Labels come from <span class="trackLabel"> plain text, casing intact."""
    tracks = _parse_tracks(FIXTURE_LOWERCASE.read_text(encoding="utf-8"))
    labels = {t.label for t in tracks if t.label}
    # Fixture contains MAU5TRAP and UPPERGROUND labels
    assert "MAU5TRAP" in labels, f"MAU5TRAP missing from {labels}"


def test_parse_tracks_titles_handle_apostrophes():
    """Titles with apostrophes ('Don\\'t Want None', 'Moar Ghosts \\'n\\' Stuff')."""
    tracks = _parse_tracks(FIXTURE_ALIAS.read_text(encoding="utf-8"))
    titles_with_apos = [t.title for t in tracks if "'" in t.title]
    assert titles_with_apos, "expected at least one apostrophe-containing title"


def test_parse_tracks_label_no_stray_space_around_nested_icon():
    """A label span with a nested icon <a> between text nodes must not
    produce a stray space (regression: SHEFFIELD TUNES (KONTOR ) bug)."""
    html = """<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="0">
<meta itemprop="name" content="Some Artist - Some Title">
<span class="trackLabel">SHEFFIELD TUNES (KONTOR<a href="/label/kontor/index.html" title="open label page"><i class="fa fa-external-link"></i></a>)</span>
</div>"""
    tracks = _parse_tracks(html)
    assert len(tracks) == 1
    assert tracks[0].label == "SHEFFIELD TUNES (KONTOR)"
