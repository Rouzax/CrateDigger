"""Tests for festival_organizer.tracklists.canary structural probes.

Each probe checks that the raw HTML returned by a 1001tracklists.com
fetch contains the must-exist markers its paired parser depends on.
An empty list means the page is structurally healthy; a non-empty
list names the missing selectors so a caller can log them.
"""

import re
from pathlib import Path

_AFROJACK_FIXTURE = Path(__file__).parent / "fixtures" / "afrojack_edc_2025.html"


def test_canary_tracklist_page_healthy_on_real_fixture():
    from festival_organizer.tracklists import canary

    html = _AFROJACK_FIXTURE.read_text(encoding="utf-8")
    assert canary.check_tracklist_page(html) == []


def test_canary_tracklist_page_flags_missing_tlpItem_row():
    from festival_organizer.tracklists import canary

    html = _AFROJACK_FIXTURE.read_text(encoding="utf-8").replace(
        "tlpItem", "tlpRenamedItem"
    )
    missing = canary.check_tracklist_page(html)
    assert "tlpItem row" in missing


def test_canary_tracklist_page_flags_missing_cue_seconds():
    from festival_organizer.tracklists import canary

    html = _AFROJACK_FIXTURE.read_text(encoding="utf-8").replace(
        "_cue_seconds", "_cue_renamed"
    )
    missing = canary.check_tracklist_page(html)
    assert "cue_seconds input" in missing


def test_canary_tracklist_page_flags_missing_h1():
    """A page without an h1 element is flagged as broken."""
    from festival_organizer.tracklists import canary

    html = _AFROJACK_FIXTURE.read_text(encoding="utf-8")
    html = re.sub(r"<h1[^>]*>.*?</h1>", "", html, flags=re.DOTALL)
    missing = canary.check_tracklist_page(html)
    assert "h1 element" in missing


def test_canary_tracklist_page_flags_missing_genre_meta():
    from festival_organizer.tracklists import canary

    html = _AFROJACK_FIXTURE.read_text(encoding="utf-8")
    html = re.sub(r'<meta\s+itemprop="genre"[^>]*>', "", html)
    missing = canary.check_tracklist_page(html)
    assert "itemprop=genre meta" in missing


def test_canary_flags_player_headers_without_tabs():
    from festival_organizer.tracklists.canary import check_tracklist_page

    html = (
        '<h1>x</h1><div class="tlpItem tlpTog"><input id="a_cue_seconds" value="0">'
        '<meta itemprop="name" content="A - B"><meta itemprop="genre" content="X"></div>'
        '<div class="bItmH flex"><span>Player 1</span></div>'
        '<div class="bItmH flex"><span>Player 2</span></div>'
    )
    # Player markers present but no mediaLinkBtn tabs -> structural drift
    assert "media player tabs" in check_tracklist_page(html)


def test_canary_clean_single_player_page_unaffected():
    from festival_organizer.tracklists.canary import check_tracklist_page

    # The row carries an artist anchor and a cue display div so those probes
    # stay quiet; this test's concern is the media-player-tab probe only.
    html = (
        '<h1>x</h1><div class="tlpItem tlpTog"><input id="a_cue_seconds" value="0">'
        '<div class="cue" onclick="toggleCue(event);">00:00</div>'
        '<a href="/artist/a/tracks.html">A</a>'
        '<meta itemprop="name" content="A - B"><meta itemprop="genre" content="X"></div>'
    )
    assert check_tracklist_page(html) == []


# --- check_search_results ---


def test_canary_search_results_healthy_on_zero_result_page():
    """Zero results for a query is a valid outcome. The probe must only
    fire when the search-page skeleton itself is missing, not when hits
    are simply absent, otherwise every no-match query would false-alarm."""
    from festival_organizer.tracklists import canary

    html = '<html><body><input name="main_search" type="text"></body></html>'
    assert canary.check_search_results(html) == []


def test_canary_search_results_healthy_with_hits():
    from festival_organizer.tracklists import canary

    html = """
    <html><body>
      <input name="main_search" type="text">
      <div class="bItm"><a href="/tracklist/abc/x.html">A set</a></div>
    </body></html>
    """
    assert canary.check_search_results(html) == []


def test_canary_search_results_flags_missing_skeleton():
    from festival_organizer.tracklists import canary

    html = "<html><body>totally unrelated page, no search input</body></html>"
    missing = canary.check_search_results(html)
    assert "search form skeleton" in missing


# --- check_dj_profile ---


def test_canary_dj_profile_healthy():
    from festival_organizer.tracklists import canary

    html = '<meta property="og:image" content="https://cdn.1001tracklists.com/dj.jpg">'
    assert canary.check_dj_profile(html) == []


def test_canary_dj_profile_flags_missing_og_image():
    from festival_organizer.tracklists import canary

    html = "<html><body>no og meta tag</body></html>"
    missing = canary.check_dj_profile(html)
    assert "og:image meta" in missing


# --- check_source_info ---


def test_canary_source_info_healthy():
    from festival_organizer.tracklists import canary

    html = """
    <div class="h">Tomorrowland 2026</div>
    <div class="cRow"><div class="mtb5">Open Air / Festival</div></div>
    <img src="/flags/be.png" alt="Belgium">
    """
    assert canary.check_source_info(html) == []


def test_canary_source_info_flags_missing_type_div():
    from festival_organizer.tracklists import canary

    html = """
    <div class="h">Some Festival</div>
    <img src="/flags/nl.png" alt="Netherlands">
    """
    missing = canary.check_source_info(html)
    assert "source type mtb5 div" in missing


def test_canary_source_info_flags_missing_country_flag():
    from festival_organizer.tracklists import canary

    html = """
    <div class="h">Some Festival</div>
    <div class="cRow"><div class="mtb5">Festival</div></div>
    """
    missing = canary.check_source_info(html)
    assert "country flag img" in missing


CHALLENGE_HTML = (
    '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"></script>'
    '<h1 class="fontL flex c">Please wait, you will be forwarded to the requested page</h1>'
)


def test_canary_flags_cloudflare_challenge_page():
    from festival_organizer.tracklists import canary

    missing = canary.check_tracklist_page(CHALLENGE_HTML)
    assert missing == ["cloudflare challenge interstitial"]


def test_canary_dj_profile_flags_cloudflare_challenge_page():
    from festival_organizer.tracklists import canary

    missing = canary.check_dj_profile(CHALLENGE_HTML)
    assert missing == ["cloudflare challenge interstitial"]


def test_canary_tracklist_flags_h1_without_artist_anchors():
    """h1 exists and has an @, but no /dj/ or /artist/ anchors: exactly the
    failure mode that silently drained ARTISTS tags across the library after
    the 2026 redesign."""
    from festival_organizer.tracklists import canary

    html = (
        "<div class='tlpItem tlpTog'><a href='/artist/x/tracks.html'>x</a></div>"
        "<input id='tl1_cue_seconds'/>"
        "<h1>Martin Garrix @ <a href='/source/n4qht3/red-rocks/index.html'>Red Rocks</a></h1>"
        "<meta itemprop='genre' content='House'/>"
    )
    missing = canary.check_tracklist_page(html)
    assert "h1 artist anchor" in missing


def test_canary_tracklist_accepts_new_artist_anchor_in_h1():
    from festival_organizer.tracklists import canary

    html = (
        "<div class='tlpItem tlpTog'><a href='/artist/x/tracks.html'>x</a></div>"
        "<input id='tl1_cue_seconds'/>"
        "<h1><a href='/artist/martin-garrix/tracklists.html'>Martin Garrix</a> @ "
        "<a href='/source/n4qht3/red-rocks/index.html'>Red Rocks</a></h1>"
        "<meta itemprop='genre' content='House'/>"
    )
    missing = canary.check_tracklist_page(html)
    assert "h1 artist anchor" not in missing


def test_canary_tracklist_flags_rows_without_artist_anchors():
    from festival_organizer.tracklists import canary

    html = (
        "<div class='tlpItem tlpTog'>no artist link here</div>"
        "<input id='tl1_cue_seconds'/>"
        "<h1><a href='/artist/mg/tracklists.html'>MG</a> @ x</h1>"
        "<meta itemprop='genre' content='House'/>"
    )
    missing = canary.check_tracklist_page(html)
    assert "track artist anchor" in missing


def test_tracklist_page_missing_cue_display_div_is_flagged():
    from festival_organizer.tracklists import canary

    html = (
        '<html><body><h1><a href="/artist/x/">X</a> @ Y</h1>'
        '<div class="tlpItem tlpTog">'
        '<input id="tlp1_cue_seconds" value="145">'
        '<a href="/artist/x/">X</a>'
        '<meta itemprop="name" content="A - B">'
        "</div></body></html>"
    )
    assert "cue display div" in canary.check_tracklist_page(html)


def test_tracklist_page_with_cue_display_div_passes():
    from festival_organizer.tracklists import canary

    html = (
        '<html><body><h1><a href="/artist/x/">X</a> @ Y</h1>'
        '<div class="tlpItem tlpTog">'
        '<input id="tlp1_cue_seconds" value="145">'
        '<div class="cue" onclick="toggleCue(event);">02:25</div>'
        '<a href="/artist/x/">X</a>'
        '<meta itemprop="name" content="A - B">'
        "</div></body></html>"
    )
    assert "cue display div" not in canary.check_tracklist_page(html)


def test_canary_cue_display_probe_quiet_on_page_without_rows():
    """The probe keys off track rows; a page with no tlpItem row (already
    flagged by the tlpItem probe) must not also report a missing cue
    display div."""
    from festival_organizer.tracklists import canary

    html = (
        '<html><body><h1><a href="/artist/x/">X</a> @ Y</h1>'
        "<p>no track rows on this page</p></body></html>"
    )
    assert "cue display div" not in canary.check_tracklist_page(html)


def test_tracklist_page_rows_without_any_name_source_are_flagged():
    """_parse_tracks reads the track name from meta itemprop=name, falling
    back to span.trackValue. Rows carrying neither would silently yield
    nameless chapters, so the probe must fire."""
    from festival_organizer.tracklists import canary

    html = (
        '<html><body><h1><a href="/artist/x/">X</a> @ Y</h1>'
        '<div class="tlpItem tlpTog">'
        '<input id="tlp1_cue_seconds" value="145">'
        '<div class="cue" onclick="toggleCue(event);">02:25</div>'
        '<a href="/artist/x/">X</a>'
        "</div></body></html>"
    )
    assert "track name source" in canary.check_tracklist_page(html)


def test_tracklist_page_with_meta_name_passes_name_source_probe():
    from festival_organizer.tracklists import canary

    html = (
        '<html><body><h1><a href="/artist/x/">X</a> @ Y</h1>'
        '<div class="tlpItem tlpTog">'
        '<input id="tlp1_cue_seconds" value="145">'
        '<div class="cue" onclick="toggleCue(event);">02:25</div>'
        '<a href="/artist/x/">X</a>'
        '<meta itemprop="name" content="A - B">'
        "</div></body></html>"
    )
    assert "track name source" not in canary.check_tracklist_page(html)


def test_canary_name_source_probe_quiet_on_page_without_rows():
    """Like the cue-display probe, this one keys off track rows so a
    row-less page reports "tlpItem row" alone."""
    from festival_organizer.tracklists import canary

    html = (
        '<html><body><h1><a href="/artist/x/">X</a> @ Y</h1>'
        "<p>no track rows on this page</p></body></html>"
    )
    assert "track name source" not in canary.check_tracklist_page(html)
