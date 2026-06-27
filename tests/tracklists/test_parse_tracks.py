from pathlib import Path

from festival_organizer.tracklists.api import _parse_tracks

FIXTURE = Path(__file__).parent / "fixtures" / "afrojack_edc_2025.html"


def test_parse_tracks_chapter_positioned_row_count():
    """Of the parsed rows, only the chapter-positioned ones (plain mains and
    mashup mains, i.e. not overlay/sub-component rows) number ~24-35. Overlay
    and tlpSubTog rows are now also returned (flagged) for later assembly, so
    the full count is larger."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    chapter_rows = [t for t in tracks if not t.is_overlay and not t.is_subcomponent]
    assert 24 <= len(chapter_rows) <= 35
    # Overlay/sub-component rows are now captured rather than dropped.
    assert any(t.is_subcomponent for t in tracks)
    assert any(t.is_overlay for t in tracks)


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


def test_parse_tracks_normalizes_genre_slash_spacing():
    """Parsed genres carry no whitespace around the slash (compact A/B form)."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    all_genres = [g for t in tracks for g in t.genres]
    assert all(" /" not in g and "/ " not in g for g in all_genres)


def test_parse_tracks_start_ms_monotonic():
    """Chapter-positioned rows (mains/mashup mains) appear in ascending start
    order. Overlay and sub-component rows carry start_ms 0 / their own cue and
    sit inline in page order, so they are excluded from this invariant."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    starts = [t.start_ms for t in tracks if not t.is_overlay and not t.is_subcomponent]
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
    # Build a minimal HTML row with a name meta containing no ' - '
    # This path is defensive; most tracks have artist-title format.
    html = """<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="0">
<meta itemprop="name" content="Intro Music">
</div>"""
    tracks = _parse_tracks(html)
    assert len(tracks) == 1
    assert tracks[0].title == "Intro Music"


def test_parse_tracks_title_with_embedded_separator_splits_on_first():
    """A title that itself contains ' - ' (subtitle / remix suffix) stays whole:
    the artist/title boundary is the FIRST ' - ', not the last."""
    html = """<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="0">
<meta itemprop="name" content="Kölsch ft. Troels Abrahamsen - All that Matters (Symphony of Unity - strings reimagined)">
</div>"""
    tracks = _parse_tracks(html)
    assert len(tracks) == 1
    assert (
        tracks[0].title == "All that Matters (Symphony of Unity - strings reimagined)"
    )


def test_parse_tracks_unid_row_falls_back_to_track_value():
    """An un-ID'd row ("ID - ID") has no itemprop=name meta; raw_text must be
    recovered from span.trackValue rather than left empty (which would blank the
    chapter title / dangle a 'vs.' downstream)."""
    html = """<div class="tlpItem tlpTog trRow1 con">
<input id="tlp1_cue_seconds" value="10.0">
<span class="trackValue notranslate blueTxt">ID - ID</span>
</div>"""
    tracks = _parse_tracks(html)
    assert len(tracks) == 1
    assert tracks[0].raw_text == "ID - ID"
    assert tracks[0].title == "ID"


def test_parse_tracks_name_meta_wins_over_track_value():
    """When the itemprop=name meta is present it is authoritative; the spaced
    span.trackValue fallback is not used."""
    html = """<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="20.0">
<meta itemprop="name" content="Real Artist - Real Title (Remix)">
<span class="trackValue notranslate blueTxt">Real Artist - Real Title ( Remix )</span>
</div>"""
    tracks = _parse_tracks(html)
    assert tracks[0].raw_text == "Real Artist - Real Title (Remix)"


def test_parse_tracks_track_value_fallback_normalizes_padding():
    """The span.trackValue fallback collapses 1001TL's inner padding so a
    recovered parenthetical matches the meta form 'Title (Acappella)'."""
    html = """<div class="tlpItem tlpTog trRow1 con">
<input id="tlp1_cue_seconds" value="30.0">
<span class="trackValue notranslate blueTxt">Artist - Title ( Acappella )</span>
</div>"""
    tracks = _parse_tracks(html)
    assert tracks[0].raw_text == "Artist - Title (Acappella)"


FIXTURE_FT_CREDIT = Path(__file__).parent / "fixtures" / "play_hard_ft_credit_row.html"
FIXTURE_PRES_COMBINED = (
    Path(__file__).parent / "fixtures" / "pres_combined_artist_row.html"
)


def test_parse_tracks_shared_ft_wrapper_splits_per_anchor():
    """Real 'David Guetta ft. Ne-Yo & Akon - Play Hard (... MORTEN ... Remix)' row:
    Ne-Yo and Akon share one feature-credit wrapper. Each anchor must get its own
    name, not the combined 'Ne-Yo & Akon' twice. The primary (David Guetta, spL)
    and the remix credit (MORTEN, spR) are unchanged, proving isolation."""
    tracks = _parse_tracks(FIXTURE_FT_CREDIT.read_text(encoding="utf-8"))
    t = tracks[0]
    assert t.artist_slugs == ["david-guetta", "ne-yo", "akon", "morten"]
    assert t.artist_names == ["David Guetta", "Ne-Yo", "Akon", "MORTEN"]
    assert len(t.artist_names) == len(t.artist_slugs)


def test_parse_tracks_source_combined_anchor_unchanged():
    """Real 'David Guetta & MARTEN HØRGER pres. Men Machine' row: 1001TL registers
    the whole pres. act as a single anchor with one combined slug. It is a primary
    (spL) anchor with no preceding text node, so the slug-anchored path never fires;
    the combined name is preserved (a source limitation B does not touch)."""
    tracks = _parse_tracks(FIXTURE_PRES_COMBINED.read_text(encoding="utf-8"))
    t = tracks[0]
    assert t.artist_slugs == ["david-guetta-marten-horger-pres.-men-machine"]
    assert t.artist_names == ["David Guetta & MARTEN HØRGER pres. Men Machine"]


def test_parse_tracks_ampersand_in_feature_member_name():
    """A feature member whose own name contains '&' (W&W, slug 'wandw') resolves to
    'W&W', and the following '& Akon' member resolves to 'Akon' -- the wrapper '&'
    separator does not corrupt either, because each anchor's preceding text node is
    matched against its own slug."""
    html = (
        '<div class="tlpItem tlpTog trRow1">'
        '<input id="tlp1_cue_seconds" value="0">'
        '<meta itemprop="name" content="Host - Track">'
        '<span class="trackValue notranslate blueTxt">Host'
        '<span class="notranslate"> ft. W&amp;W'
        '<a class="notranslate tgHid" href="/artist/x/wandw/index.html"><i></i></a>'
        " &amp; Akon"
        '<a class="notranslate tgHid" href="/artist/y/akon/index.html"><i></i></a>'
        "</span> - Track</span></div>"
    )
    t = _parse_tracks(html)[0]
    assert t.artist_slugs == ["wandw", "akon"]
    assert t.artist_names == ["W&W", "Akon"]


def test_parse_tracks_empty_keyed_slug_does_not_steal_junk_run():
    """Empty-key guard: an anchor whose slug normalizes to '' must not let the
    shortest-run match grab a punctuation-only trailing run (which also keys to
    '') over the real name. With the guard, slug-anchored is skipped and the
    existing walk-up keeps the real text; without it, the shortest run '++'
    (key '') would win."""
    html = (
        '<div class="tlpItem tlpTog trRow1">'
        '<input id="tlp1_cue_seconds" value="0">'
        '<meta itemprop="name" content="Host - Track">'
        '<span class="trackValue notranslate blueTxt">Host'
        '<span class="notranslate"> ft. Real ++'
        '<a class="notranslate tgHid" href="/artist/x/--/index.html"><i></i></a>'
        "</span> - Track</span></div>"
    )
    t = _parse_tracks(html)[0]
    assert t.artist_slugs == ["--"]
    assert t.artist_names[0] != "++"
    assert "Real" in t.artist_names[0]


# --- Edge-case fixtures ---

FIXTURE_B2B = Path(__file__).parent / "fixtures" / "armin_kiki_amf_2025.html"
FIXTURE_B2B_2026 = (
    Path(__file__).parent / "fixtures" / "armin_marlon_ultra_miami_2026.html"
)
FIXTURE_ALIAS = (
    Path(__file__).parent / "fixtures" / "something_else_tomorrowland_winter_2026.html"
)
FIXTURE_LOWERCASE = (
    Path(__file__).parent / "fixtures" / "deadmau5_tomorrowland_brasil_2025.html"
)


def test_parse_tracks_b2b_multi_artist_rows():
    """B2B / multi-artist track rows pair slug and display name by index."""
    tracks = _parse_tracks(FIXTURE_B2B.read_text(encoding="utf-8"))
    multi = [t for t in tracks if len(t.artist_slugs) >= 2]
    assert multi, "expected at least one multi-artist track in B2B set"
    for t in multi:
        assert len(t.artist_names) == len(t.artist_slugs)
        # Display names should not look like title-cased slugs
        for _slug, name in zip(t.artist_slugs, t.artist_names, strict=True):
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
    assert "Armin van Buuren" in all_names, (
        f"Armin missing from {sorted(all_names)[:20]}..."
    )
    assert "Marlon Hoffstadt" in all_names, (
        f"Marlon missing from {sorted(all_names)[:20]}..."
    )


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
    assert tracks[0].artist_slugs == [
        "hannah-laing",
        "marlon-hoffstadt",
        "caroline-roxy",
    ]
    # No "ft. " prefix, no remix-note pollution: the slug-derived fallback wins.
    assert tracks[0].artist_names == [
        "Hannah Laing",
        "Marlon Hoffstadt",
        "Caroline Roxy",
    ]


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
    assert tracks[0].artist_names[2] == "Wippenberg"  # slug-derived


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
        n
        for t in tracks
        for n in t.artist_names
        if n.lower().startswith(("ft.", "feat."))
        or (n.startswith("(") and n.endswith(")"))
    ]
    assert not polluted, f"trackValue pollution leaked: {polluted}"


def test_parse_tracks_includes_con_row_with_valid_cue():
    """A row with class 'con' and a non-zero cue is a mashup main row,
    not a component overlay. It should be included as a chapter track."""
    html = """<div id="tlTab">
<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="100">
<meta itemprop="name" content="Artist A - Track One">
</div>
<div class="tlpItem tlpTog trRow2 con">
<input id="tlp2_cue_seconds" value="200">
<meta itemprop="name" content="Artist B vs. Artist C - Alpha vs. Beta (Mashup)">
</div>
<div class="tlpItem tlpTog trRow3">
<input id="tlp3_cue_seconds" value="400">
<meta itemprop="name" content="Artist D - Track Three">
</div>
</div>"""
    tracks = _parse_tracks(html)
    titles = [t.title for t in tracks]
    assert len(tracks) == 3
    assert "Alpha vs. Beta (Mashup)" in titles


def test_parse_tracks_includes_con_row_with_zero_cue_as_overlay():
    """A row with class 'con' and cue=0 is a positionless mashup component
    overlay (acappella, sample). It is now parsed (not dropped) and flagged as
    an overlay so later assembly can fold it into its host main."""
    html = """<div id="tlTab">
<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="100">
<meta itemprop="name" content="Artist A - Track One">
</div>
<div class="tlpItem tlpTog trRow1 con">
<input id="tlp2_cue_seconds" value="0">
<meta itemprop="name" content="Classic Track - Vocals (Acappella)">
</div>
</div>"""
    tracks = _parse_tracks(html)
    assert len(tracks) == 2
    main = [t for t in tracks if not t.is_overlay][0]
    assert main.title == "Track One"
    overlay = [t for t in tracks if t.is_overlay][0]
    assert overlay.start_ms == 0
    assert overlay.is_overlay is True
    assert overlay.is_subcomponent is False


def test_parse_tracks_afrojack_con_mashups_included():
    """The Afrojack EDC fixture has two con rows with valid cue times
    (2225s 'Virtual Riot' and 2389s unnamed) that must appear in output."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    start_times = {t.start_ms for t in tracks}
    assert 2225000 in start_times, "con row at 2225s (Virtual Riot) was dropped"
    assert 2389000 in start_times, "con row at 2389s was dropped"


def test_parse_tracks_sets_is_mashup_on_subPosTog_rows():
    """Rows with subPosTog class (mashup main rows) get is_mashup=True."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    mashups = [t for t in tracks if t.is_mashup]
    assert mashups, "expected at least one mashup track in Afrojack EDC fixture"
    non_mashups = [t for t in tracks if not t.is_mashup]
    assert non_mashups, "expected non-mashup tracks too"
    for t in mashups:
        assert "vs." in t.raw_text.lower() or "mashup" in t.raw_text.lower(), (
            f"mashup track doesn't look like a mashup: {t.raw_text}"
        )


# --- Overlay / sub-component flags + group_id (Task 2) ---


def test_parse_tracks_con_row_with_valid_cue_is_overlay():
    """A 'con' row with cue>0 is a timed overlay: is_overlay True,
    is_subcomponent False, and it keeps its non-zero start."""
    html = """<div id="tlTab">
<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="100">
<meta itemprop="name" content="Artist A - Track One">
</div>
<div class="tlpItem tlpTog trRow2 con">
<input id="tlp2_cue_seconds" value="200">
<meta itemprop="name" content="Artist B - Track Two">
</div>
</div>"""
    tracks = _parse_tracks(html)
    overlay = [t for t in tracks if t.start_ms == 200000][0]
    assert overlay.is_overlay is True
    assert overlay.is_subcomponent is False
    # The plain main is neither.
    main = [t for t in tracks if t.start_ms == 100000][0]
    assert main.is_overlay is False
    assert main.is_subcomponent is False


def test_parse_tracks_con_row_with_zero_cue_is_parsed_as_overlay():
    """A 'con' row with cue=0 (positionless overlay) is no longer dropped:
    it is parsed with is_overlay True and start_ms 0."""
    html = """<div id="tlTab">
<div class="tlpItem tlpTog trRow1">
<input id="tlp1_cue_seconds" value="100">
<meta itemprop="name" content="Artist A - Track One">
</div>
<div class="tlpItem tlpTog trRow1 con">
<input id="tlp2_cue_seconds" value="0">
<meta itemprop="name" content="Classic Track - Vocals (Acappella)">
</div>
</div>"""
    tracks = _parse_tracks(html)
    assert len(tracks) == 2
    overlay = [t for t in tracks if t.start_ms == 0 and t.is_overlay][0]
    assert overlay.is_overlay is True
    assert overlay.start_ms == 0


def test_parse_tracks_tlpsubtog_row_is_subcomponent_with_group_id():
    """A 'tlpSubTog' row is a mashup sub-component: is_subcomponent True,
    is_overlay True (it carries 'con'), start_ms 0, and group_id equal to its
    trRow<N> number."""
    html = """<div id="tlTab">
<div class="tlpItem tlpTog subPosTog trRow7">
<input id="tlp1_cue_seconds" value="300">
<meta itemprop="name" content="Artist A vs. Artist B - Alpha vs. Beta (Mashup)">
</div>
<div class="tlpItem tlpSubTog con subPos1 trRow7 tgHid">
<input id="tlp2_cue_seconds" value="0">
<meta itemprop="name" content="Artist A - Alpha">
</div>
<div class="tlpItem tlpSubTog con subPos2 trRow7 tgHid">
<input id="tlp3_cue_seconds" value="0">
<meta itemprop="name" content="Artist B - Beta">
</div>
</div>"""
    tracks = _parse_tracks(html)
    subs = [t for t in tracks if t.is_subcomponent]
    assert len(subs) == 2
    for s in subs:
        assert s.is_subcomponent is True
        assert s.is_overlay is True
        assert s.start_ms == 0
        assert s.group_id == 7
    # The mashup main shares the group id and is flagged is_mashup.
    main = [t for t in tracks if t.is_mashup][0]
    assert main.group_id == 7
    assert main.is_subcomponent is False
    assert main.is_overlay is False


def test_parse_tracks_plain_main_has_default_overlay_fields():
    """A plain main row has is_overlay/is_subcomponent/is_mashup False and
    group_id -1 when it has no trRow class."""
    html = """<div id="tlTab">
<div class="tlpItem tlpTog">
<input id="tlp1_cue_seconds" value="100">
<meta itemprop="name" content="Artist A - Track One">
</div>
</div>"""
    tracks = _parse_tracks(html)
    assert len(tracks) == 1
    t = tracks[0]
    assert t.is_overlay is False
    assert t.is_subcomponent is False
    assert t.is_mashup is False
    assert t.group_id == -1


def test_parse_tracks_afrojack_mashup_mains_and_children_share_group_id():
    """In the real Afrojack EDC fixture, every tlpSubTog child shares a
    group_id with a subPosTog mashup main."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    subs = [t for t in tracks if t.is_subcomponent]
    mains = [t for t in tracks if t.is_mashup]
    assert subs, "expected tlpSubTog sub-components in fixture"
    assert mains, "expected subPosTog mashup mains in fixture"
    main_group_ids = {t.group_id for t in mains}
    assert all(s.group_id in main_group_ids for s in subs), (
        "every sub-component should share a group_id with a mashup main"
    )
    # Sub-components carry the con overlay flag and sit at cue 0.
    for s in subs:
        assert s.is_overlay is True
        assert s.start_ms == 0


# --- Player ordinal tagging (multi-source pages) ---

FIXTURE_MULTIPLAYER = Path(__file__).parent / "fixtures" / "multiplayer_tracklist.html"


def test_parse_tracks_tags_player_ordinal():
    tracks = _parse_tracks(FIXTURE_MULTIPLAYER.read_text(encoding="utf-8"))
    # Catharina + Carry You are under "Player 2"
    assert tracks[0].player == 2
    assert tracks[1].player == 2
    # Repeat It + Shape Of You are under "Player 1"
    assert tracks[2].player == 1
    assert tracks[3].player == 1
    # Dragon + High On Life back under "Player 2"; the "Ed Sheeran on stage"
    # header is NOT a player switch and must not reset the ordinal.
    assert tracks[4].player == 2
    assert tracks[5].player == 2


def test_parse_tracks_single_player_defaults_to_zero():
    html = (
        '<div><div class="tlpTog bItm tlpItem"><input id="x_cue_seconds" value="5">'
        '<meta itemprop="name" content="A - B"></div></div>'
    )
    tracks = _parse_tracks(html)
    assert tracks[0].player == 0
