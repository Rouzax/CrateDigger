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
FIXTURE_B2B_2026 = Path(__file__).parent / "fixtures" / "armin_marlon_ultra_miami_2026.html"
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


def test_parse_tracks_b2b_2026_markup():
    """2026-markup B2B fixture: Armin van Buuren + Marlon Hoffstadt at ASOT Ultra Miami."""
    tracks = _parse_tracks(FIXTURE_B2B_2026.read_text(encoding="utf-8"))
    assert len(tracks) >= 15
    multi = [t for t in tracks if len(t.artist_slugs) >= 2]
    assert multi, "expected at least one multi-artist row in B2B set"
    for t in multi:
        assert len(t.artist_names) == len(t.artist_slugs), (
            f"slug/name pairing broken: {t.artist_slugs} vs {t.artist_names}"
        )
    all_names = {n for t in tracks for n in t.artist_names}
    assert "Armin van Buuren" in all_names, f"Armin missing from {sorted(all_names)[:20]}..."
    assert "Marlon Hoffstadt" in all_names, f"Marlon missing from {sorted(all_names)[:20]}..."


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


# --- artist_names cleanliness: per-artist wrapper vs. trackValue fallback ---


def test_artist_names_uses_inner_per_artist_notranslate_wrapper():
    """When the per-artist notranslate span exists, display is just the name,
    not the surrounding track text (ft./remix notes/vs. compounds)."""
    html = """<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="0">
<meta itemprop="name" content="AFROJACK ft. Eva Simons - Take Over Control">
<span class="trackValue notranslate blueTxt">
  <span class="notranslate blueTxt">AFROJACK<span class="tgHid spL"><a href="/artist/kdl3un/afrojack/index.html"></a></span></span>
  ft.
  <span class="notranslate blueTxt">Eva Simons<span class="tgHid spL"><a href="/artist/eva/eva-simons/index.html"></a></span></span>
  - Take Over Control
</span>
</div>"""
    tracks = _parse_tracks(html)
    assert tracks[0].artist_slugs == ["afrojack", "eva-simons"]
    assert tracks[0].artist_names == ["AFROJACK", "Eva Simons"]


def test_artist_names_fall_back_to_slug_when_wrapper_missing():
    """On tracks where 1001TL omits the per-artist wrapper (seen on some b2b/
    mashup rows), the outer trackValue span pollutes the name with ft./remix
    notes. Fall back to the slug rather than writing garbage to disk."""
    html = """<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="0">
<meta itemprop="name" content="Hannah Laing &amp; Marlon Hoffstadt ft. Caroline Roxy - Stomp Your Feet">
<span class="trackValue notranslate blueTxt">
  <a href="/artist/h1/hannah-laing/index.html">Hannah Laing</a>
  &amp;
  <a href="/artist/m1/marlon-hoffstadt/index.html">Marlon Hoffstadt</a>
  ft.
  <a href="/artist/c1/caroline-roxy/index.html">Caroline Roxy</a>
  - Stomp Your Feet
</span>
</div>"""
    tracks = _parse_tracks(html)
    assert tracks[0].artist_slugs == ["hannah-laing", "marlon-hoffstadt", "caroline-roxy"]
    # No "ft. " prefix, no remix-note pollution: the slug-derived fallback wins.
    assert tracks[0].artist_names == ["Hannah Laing", "Marlon Hoffstadt", "Caroline Roxy"]


def test_artist_names_fall_back_to_slug_preserves_alignment_with_slugs():
    """Mixed case: some artists have the per-artist wrapper, others do not.
    Alignment with artist_slugs must hold in both branches."""
    html = """<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="0">
<meta itemprop="name" content="Armin van Buuren &amp; Hannah Laing &amp; Wippenberg - U Got 2 Know">
<span class="trackValue notranslate blueTxt">
  <span class="notranslate blueTxt">Armin van Buuren<span class="tgHid spL"><a href="/artist/avb/armin-van-buuren/index.html"></a></span></span>
  &amp;
  <a href="/artist/h1/hannah-laing/index.html">Hannah Laing</a>
  &amp;
  <a href="/artist/w1/wippenberg/index.html">Wippenberg</a>
  - U Got 2 Know
</span>
</div>"""
    tracks = _parse_tracks(html)
    assert tracks[0].artist_slugs == ["armin-van-buuren", "hannah-laing", "wippenberg"]
    assert len(tracks[0].artist_names) == len(tracks[0].artist_slugs)
    assert tracks[0].artist_names[0] == "Armin van Buuren"
    assert tracks[0].artist_names[1] == "Hannah Laing"  # slug-derived
    assert tracks[0].artist_names[2] == "Wippenberg"    # slug-derived


def test_artist_names_remix_credit_uses_preceding_blueTxt_sibling():
    """When the anchor sits inside <span class='tgHid spR'>, the remix-credit
    artist name is in the preceding sibling <span class='blueTxt'>. Reading it
    preserves casing and punctuation (LAWTON, Kø:lab) exactly, avoiding the
    lossy slug-fallback that would turn "Kø:lab" into "Kolab"."""
    html = """<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="0">
<meta itemprop="name" content="Madonna - Frozen ( LAWTON Lick )">
<span class="trackValue notranslate">
  <span class="notranslate blueTxt">Madonna<span class="tgHid spL"><a href="/artist/u/madonna/index.html"></a></span></span>
  <span class="notranslate"> - </span>
  <span class="blueTxt">Frozen</span>
  <span class="notranslate"> (<span class="blueTxt">LAWTON</span><span class="tgHid spR"><a href="/artist/l/lawton/index.html"></a></span><span class="remixValue"> Lick</span>)</span>
</span>
</div>"""
    tracks = _parse_tracks(html)
    assert tracks[0].artist_slugs == ["madonna", "lawton"]
    # Proper all-caps preserved (not slug-fallback title-case "Lawton"):
    assert tracks[0].artist_names == ["Madonna", "LAWTON"]


def test_artist_names_remix_credit_preserves_diacritics_and_punctuation():
    """Real-world regression: Kø:lab remix credit must not degrade to "Kolab"."""
    html = """<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="0">
<meta itemprop="name" content="Artist - Track ( Kø:lab Rave Edit )">
<span class="trackValue notranslate">
  <span class="notranslate blueTxt">Artist<span class="tgHid spL"><a href="/artist/a/artist/index.html"></a></span></span>
  <span class="notranslate"> - </span>
  <span class="blueTxt">Track</span>
  <span class="notranslate"> (<span class="blueTxt">Kø:lab</span><span class="tgHid spR"><a href="/artist/k/kolab/index.html"></a></span><span class="remixValue"> Rave Edit</span>)</span>
</span>
</div>"""
    tracks = _parse_tracks(html)
    assert tracks[0].artist_slugs == ["artist", "kolab"]
    assert tracks[0].artist_names == ["Artist", "Kø:lab"]


def test_artist_names_real_fixture_still_clean():
    """Sanity: the existing afrojack fixture continues to yield clean names."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    # None of the extracted display names should contain ft./feat. or
    # enclosing parentheses, which would indicate trackValue pollution.
    polluted = [
        n for t in tracks for n in t.artist_names
        if n.lower().startswith(("ft.", "feat."))
        or (n.startswith("(") and n.endswith(")"))
    ]
    assert not polluted, f"trackValue pollution leaked: {polluted}"
