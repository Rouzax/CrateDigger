"""Tests for festival_organizer.tracklists.canary structural probes.

Each probe checks that the raw HTML returned by a 1001tracklists.com
fetch contains the must-exist markers its paired parser depends on.
An empty list means the page is structurally healthy; a non-empty
list names the missing selectors so a caller can log them.
"""
import re
from pathlib import Path

_AFROJACK_FIXTURE = (
    Path(__file__).parent / "fixtures" / "afrojack_edc_2025.html"
)


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


def test_canary_tracklist_page_flags_missing_h1_at_separator():
    """The h1 must contain '@' to split DJs from stage/source."""
    from festival_organizer.tracklists import canary
    html = _AFROJACK_FIXTURE.read_text(encoding="utf-8")
    html = re.sub(
        r"(<h1[^>]*>)(.*?)(</h1>)",
        lambda m: m.group(1) + m.group(2).replace("@", "--") + m.group(3),
        html,
        count=1,
        flags=re.DOTALL,
    )
    missing = canary.check_tracklist_page(html)
    assert "h1 with @" in missing


def test_canary_tracklist_page_flags_missing_genre_meta():
    from festival_organizer.tracklists import canary
    html = _AFROJACK_FIXTURE.read_text(encoding="utf-8")
    html = re.sub(r'<meta\s+itemprop="genre"[^>]*>', "", html)
    missing = canary.check_tracklist_page(html)
    assert "itemprop=genre meta" in missing


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
    html = '''
    <html><body>
      <input name="main_search" type="text">
      <div class="bItm"><a href="/tracklist/abc/x.html">A set</a></div>
    </body></html>
    '''
    assert canary.check_search_results(html) == []


def test_canary_search_results_flags_missing_skeleton():
    from festival_organizer.tracklists import canary
    html = "<html><body>totally unrelated page, no search input</body></html>"
    missing = canary.check_search_results(html)
    assert "search form skeleton" in missing
