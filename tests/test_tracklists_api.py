"""Tests for 1001Tracklists API layer (all mocked, no real network calls)."""
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
import requests

from festival_organizer.tracklists.api import (
    TracklistSession,
    TracklistError,
    RateLimitError,
    ExportError,
    AuthenticationError,
    _parse_duration_string,
    _html_decode,
    _normalize_date,
    _is_rate_limited,
    _extract_genres,
    _extract_dj_slugs,
    _maximize_artwork_url,
    _parse_dj_profile,
    _parse_h1_structure,
)


# --- Helper function tests ---

def test_parse_duration_string_hours_minutes():
    assert _parse_duration_string("1h 15m") == 75


def test_parse_duration_string_minutes_only():
    assert _parse_duration_string("58m") == 58


def test_parse_duration_string_hours_only():
    assert _parse_duration_string("1h") == 60


def test_parse_duration_string_empty():
    assert _parse_duration_string("") is None
    assert _parse_duration_string(None) is None


def test_html_decode():
    assert _html_decode("Artist &amp; Other") == "Artist & Other"
    assert _html_decode("A &lt;B&gt;") == "A <B>"
    assert _html_decode("K&ouml;lsch") == "Kölsch"
    assert _html_decode("Salom&eacute;") == "Salomé"
    assert _html_decode("Ti&euml;sto") == "Tiësto"


def test_normalize_date_iso():
    assert _normalize_date("2025-10-19") == "2025-10-19"


def test_normalize_date_common_format():
    assert _normalize_date("Oct 19, 2025") == "2025-10-19"


def test_normalize_date_invalid():
    assert _normalize_date("not a date") is None


def test_is_rate_limited():
    assert _is_rate_limited("You have sent too many requests") is True
    assert _is_rate_limited("solve captcha to unblock") is True
    assert _is_rate_limited("Normal page content") is False


# --- Cookie caching tests ---

def test_cookie_save_restore():
    with tempfile.TemporaryDirectory() as tmp:
        cookie_path = Path(tmp) / "cookies.json"
        session = TracklistSession(cookie_cache_path=cookie_path)

        # Simulate having cookies
        session._session.cookies.set("sid", "test_sid", domain="www.1001tracklists.com")
        session._session.cookies.set("uid", "test_uid", domain="www.1001tracklists.com")
        session._save_cookies("test@example.com")

        assert cookie_path.exists()

        # Restore in a new session
        session2 = TracklistSession(cookie_cache_path=cookie_path)
        assert session2._restore_cookies("test@example.com") is True

        names = {c.name for c in session2._session.cookies}
        assert "sid" in names
        assert "uid" in names


def test_cookie_restore_wrong_email():
    with tempfile.TemporaryDirectory() as tmp:
        cookie_path = Path(tmp) / "cookies.json"
        session = TracklistSession(cookie_cache_path=cookie_path)
        session._session.cookies.set("sid", "x", domain="www.1001tracklists.com")
        session._session.cookies.set("uid", "x", domain="www.1001tracklists.com")
        session._save_cookies("user1@example.com")

        session2 = TracklistSession(cookie_cache_path=cookie_path)
        assert session2._restore_cookies("user2@example.com") is False


def test_cookie_restore_no_file():
    with tempfile.TemporaryDirectory() as tmp:
        cookie_path = Path(tmp) / "nonexistent.json"
        session = TracklistSession(cookie_cache_path=cookie_path)
        assert session._restore_cookies("test@example.com") is False


class TestCookieFilePermissions:
    def test_save_cookies_writes_0o600_on_posix(self, tmp_path):
        """Cookie file must not be world-readable. Contains live session tokens."""
        import stat
        import sys as sys_mod
        if sys_mod.platform == "win32":
            pytest.skip("POSIX-only permission semantics")

        cookie_path = tmp_path / "1001tl-cookies.json"
        api = TracklistSession(cookie_cache_path=cookie_path)
        api._session.cookies.set("sid", "fake-sid", domain=".1001tracklists.com")
        api._session.cookies.set("uid", "fake-uid", domain=".1001tracklists.com")
        api._save_cookies(email="user@example.com")

        assert cookie_path.is_file()
        mode = stat.S_IMODE(cookie_path.stat().st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_default_cookie_path_uses_paths_cookies_file(tmp_path, monkeypatch):
    """Without an explicit cookie_cache_path, the session uses paths.cookies_file()."""
    expected = tmp_path / "state" / "1001tl-cookies.json"
    monkeypatch.setattr(
        "festival_organizer.tracklists.api.paths.cookies_file", lambda: expected
    )
    session = TracklistSession()
    assert session._cookie_path == expected


def test_save_cookies_creates_parent_dir(tmp_path):
    """_save_cookies creates the parent directory on first save."""
    cookie_path = tmp_path / "freshly" / "nested" / "1001tl-cookies.json"
    session = TracklistSession(cookie_cache_path=cookie_path)
    session._session.cookies.set("sid", "s", domain="www.1001tracklists.com")
    session._session.cookies.set("uid", "u", domain="www.1001tracklists.com")
    session._save_cookies("user@example.com")
    assert cookie_path.exists()
    assert cookie_path.parent.is_dir()


# --- Search result parsing ---

def test_parse_search_results():
    html = '''
    <div class="bItm ">
        <a href="/tracklist/abc123/artist-festival.html" class="tLink">Artist @ Festival 2025</a>
        <div title="play time"><i class="fa"></i>1h 2m</div>
        <div title="tracklist date"><i class="fa"></i>2025-10-19</div>
    </div>
    <div class="bItm ">
        <a href="/tracklist/def456/other.html" class="tLink">Other Artist @ Event</a>
        <div title="play time"><i class="fa"></i>58m</div>
        <div title="tracklist date"><i class="fa"></i>2025-06-28</div>
    </div>
    '''
    session = TracklistSession()
    results = session._parse_search_results(html)
    assert len(results) == 2
    assert results[0].id == "abc123"
    assert results[0].title == "Artist @ Festival 2025"
    assert results[0].duration_mins == 62
    assert results[0].date == "2025-10-19"
    assert results[1].id == "def456"


def test_parse_search_results_deduplication():
    html = '''
    <div class="bItm ">
        <a href="/tracklist/abc123/v1.html">Title</a>
    </div>
    <div class="bItm ">
        <a href="/tracklist/abc123/v2.html">Title</a>
    </div>
    '''
    session = TracklistSession()
    results = session._parse_search_results(html)
    assert len(results) == 1


def test_parse_search_results_skip_pagination():
    html = '''
    <div class="bItm ">
        <a href="/tracklist/abc123/artist.html">Artist @ Festival</a>
    </div>
    <div class="bItm ">
        <a href="/page/2">Next</a>
    </div>
    '''
    session = TracklistSession()
    results = session._parse_search_results(html)
    assert len(results) == 1


def test_parse_search_results_new_class_format():
    """Site now uses class="bItm action oItm" instead of class="bItm "."""
    html = '''
    <div class="bItm action oItm">
        <a href="/tracklist/abc123/artist-festival.html" class="">Artist @ Festival 2025</a>
        <div title="play time"><i class="fa"></i>1h 2m</div>
        <div title="tracklist date"><i class="fa"></i>2025-10-19</div>
    </div>
    <div class="bItm action oItm">
        <a href="/tracklist/def456/other.html" class="">Other Artist @ Event</a>
        <div title="play time"><i class="fa"></i>58m</div>
        <div title="tracklist date"><i class="fa"></i>2025-06-28</div>
    </div>
    '''
    session = TracklistSession()
    results = session._parse_search_results(html)
    assert len(results) == 2
    assert results[0].id == "abc123"
    assert results[0].title == "Artist @ Festival 2025"


def test_parse_search_results_skips_header():
    """bItmH (header) class should not be parsed as a result."""
    html = '''
    <div class="bItmH">Header</div>
    <div class="bItm action oItm">
        <a href="/tracklist/abc123/artist.html">Artist @ Festival</a>
    </div>
    '''
    session = TracklistSession()
    results = session._parse_search_results(html)
    assert len(results) == 1


def test_parse_search_results_survives_class_before_href():
    """BS4 migration: the title-link regex requires href to be the first
    attribute after <a>. Real markup often has class or data-* attributes
    before href; BS4 finds the anchor regardless."""
    html = '''
    <div class="bItm action">
      <a class="tLink bigBtn" href="/tracklist/abc123/real-set.html">Real Set</a>
    </div>
    '''
    session = TracklistSession()
    results = session._parse_search_results(html)
    assert len(results) == 1
    assert results[0].id == "abc123"
    assert results[0].title == "Real Set"


def test_parse_search_results_survives_single_quoted_href():
    html = '''
    <div class="bItm">
      <a href='/tracklist/abc123/real-set.html'>Real Set</a>
    </div>
    '''
    session = TracklistSession()
    results = session._parse_search_results(html)
    assert len(results) == 1
    assert results[0].id == "abc123"


def test_parse_search_results_empty():
    session = TracklistSession()
    results = session._parse_search_results("<div>No results</div>")
    assert results == []


# --- Login tests (mocked) ---

def test_login_success():
    session = TracklistSession()

    mock_login_resp = MagicMock()
    mock_login_resp.status_code = 200

    mock_validate_resp = MagicMock()
    mock_validate_resp.text = '<a href="/logout">Logout</a>'
    mock_validate_resp.url = "https://www.1001tracklists.com/my/"

    with patch.object(session, "_restore_cookies", return_value=False):
        with patch.object(session._session, "post", return_value=mock_login_resp):
            with patch.object(session._session, "get", return_value=mock_validate_resp):
                # Add cookies that would normally be set by the server
                session._session.cookies.set("sid", "test", domain="www.1001tracklists.com")
                session._session.cookies.set("uid", "test", domain="www.1001tracklists.com")
                session.login("test@test.com", "pass")


def test_cookie_save_failure_logged(tmp_path, caplog):
    """Cookie save failure is logged at debug level."""
    # Point cookie "parent" at an existing regular file so mkdir fails with OSError.
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    session = TracklistSession(cookie_cache_path=blocker / "cookies.json")

    with caplog.at_level(logging.DEBUG, logger="festival_organizer.tracklists.api"):
        session._save_cookies("test@example.com")
    # Should not crash, should log
    assert any("save" in r.message.lower() or "cookie" in r.message.lower() for r in caplog.records)


def test_login_failure_no_cookies():
    session = TracklistSession()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch.object(session, "_restore_cookies", return_value=False), \
         patch.object(session, "_request", return_value=mock_resp):
        with pytest.raises(AuthenticationError, match="missing session cookies"):
            session.login("test@test.com", "wrong")


# --- Genre extraction (itemprop) ---

def test_extract_genres_from_itemprop():
    html = '''<meta itemprop="numTracks" content="25"><meta itemprop="genre" content="Mainstage">
    <meta itemprop="genre" content="Dance / Electro Pop">
    <meta itemprop="genre" content="Tech House">'''
    genres = _extract_genres(html)
    assert genres == ["Mainstage", "Dance / Electro Pop", "Tech House"]


def test_extract_genres_deduplication():
    html = '''<meta itemprop="genre" content="Mainstage">
    <meta itemprop="genre" content="House">
    <meta itemprop="genre" content="Mainstage">
    <meta itemprop="genre" content="House">'''
    genres = _extract_genres(html)
    assert genres == ["Mainstage", "House"]


def test_extract_genres_filters_tracklist_schema():
    html = '''<meta itemprop="genre" content="tracklist">
    <meta itemprop="genre" content="Mainstage">'''
    genres = _extract_genres(html)
    assert genres == ["Mainstage"]


def test_extract_genres_empty():
    assert _extract_genres("<html>no genres</html>") == []


def test_extract_genres_survives_attribute_reorder():
    """BS4 migration: HTML authors may emit attributes in either order.
    The pre-migration regex required itemprop before content and silently
    returned []."""
    html = '<meta content="House" itemprop="genre">'
    assert _extract_genres(html) == ["House"]


def test_extract_genres_survives_single_quotes():
    html = "<meta itemprop='genre' content='Techno'>"
    assert _extract_genres(html) == ["Techno"]


def test_extract_genres_survives_intervening_attribute():
    html = '<meta itemprop="genre" class="dark" content="Trance">'
    assert _extract_genres(html) == ["Trance"]


# --- DJ slug extraction ---

def test_extract_dj_slugs():
    html = '''<a href="/dj/martingarrix/">MG</a>
    <a href="/dj/alesso/">A</a>
    <a href="/dj/martingarrix/">MG</a>'''
    slugs = _extract_dj_slugs(html)
    assert slugs == ["martingarrix", "alesso"]


def test_extract_dj_slugs_index_html():
    """Real 1001TL pages use /dj/slug/index.html links."""
    html = '''<a href="/dj/afrojack/index.html" class="notranslate">AFROJACK</a>
    <a href="/dj/nlw/index.html">NLW</a>
    <a href="/dj/afrojack/index.html">AFROJACK</a>'''
    slugs = _extract_dj_slugs(html)
    assert slugs == ["afrojack", "nlw"]


def test_extract_dj_slugs_group():
    """Group DJs like DVLM have group slug first, then individual members."""
    html = '''<a href="/dj/dimitrivegasandlikemike/index.html">Dimitri Vegas &amp; Like Mike</a>
    <a href="/dj/dimitrivegas/index.html">Dimitri Vegas</a>
    <a href="/dj/likemike/index.html">Like Mike</a>'''
    slugs = _extract_dj_slugs(html)
    assert slugs[0] == "dimitrivegasandlikemike"
    assert len(slugs) == 3


def test_extract_dj_slugs_mixed_formats():
    """Mix of trailing-slash and index.html link formats."""
    html = '''<a href="/dj/tiesto/">Tiesto</a>
    <a href="/dj/martingarrix/index.html">Martin Garrix</a>'''
    slugs = _extract_dj_slugs(html)
    assert slugs == ["tiesto", "martingarrix"]


def test_extract_dj_slugs_empty():
    assert _extract_dj_slugs("<html>no djs</html>") == []


def test_extract_dj_slugs_survives_single_quoted_href():
    """BS4 migration: real 1001TL markup uses double quotes but nothing
    stops a future template engine from switching to single quotes.
    The old regex required exact double-quote delimiters."""
    html = "<a href='/dj/carl-cox/index.html'>Carl Cox</a>"
    slugs = _extract_dj_slugs(html)
    assert slugs == ["carl-cox"]


def test_extract_dj_slugs_ignores_unrelated_links_with_dj_in_path():
    """The regex matches any 'href=\"/dj/...' substring and rejects longer
    paths only by the closing quote. A more forgiving match would risk
    false positives. Confirm BS4 still picks up clean /dj/<slug>/ anchors
    and ignores /dj/<slug>/something/else/ paths."""
    html = '''
    <a href="/dj/tiesto/index.html">Tiesto</a>
    <a href="/dj/tiesto/tracklists/2025/">Tiesto 2025 tracklists</a>
    '''
    slugs = _extract_dj_slugs(html)
    assert slugs == ["tiesto"]


# --- _parse_h1_structure ---

def test_parse_h1_structure_basic_dj_at_source():
    """Baseline: DJ @ source with country tail."""
    h1 = (
        '<a href="/dj/afrojack/index.html">AFROJACK</a>'
        ' @ Mainstage, <a href="/source/abc/ultra-miami/index.html">Ultra Miami</a>'
        ', United States 2026-03-29'
    )
    result = _parse_h1_structure(h1)
    assert result["dj_artists"] == [("afrojack", "AFROJACK")]
    assert result["sources"] == [("abc", "ultra-miami", "Ultra Miami")]
    assert result["date"] == "2026-03-29"
    assert result["country"] == "United States"


def test_parse_h1_structure_handles_single_quoted_anchors():
    """BS4 migration: anchor tags may use single-quoted hrefs."""
    h1 = (
        "<a href='/dj/adam-beyer/index.html'>Adam Beyer</a>"
        " @ <a href='/source/99/awakenings/index.html'>Awakenings</a>"
    )
    result = _parse_h1_structure(h1)
    assert ("adam-beyer", "Adam Beyer") in result["dj_artists"]
    assert any(s[0] == "99" for s in result["sources"])


def test_parse_h1_structure_returns_empty_when_no_at_sign():
    """Documented guard: h1 without '@' returns all-empty dict."""
    result = _parse_h1_structure("<a href='/dj/someone/'>Some DJ</a>")
    assert result["dj_artists"] == []
    assert result["sources"] == []


# --- Canary integration in callers ---

def test_search_fires_canary_on_missing_skeleton(caplog):
    """When the search response has no main_search input, the canary fires."""
    session = TracklistSession()
    resp = MagicMock(
        text="<html><body>totally unrelated response</body></html>",
        status_code=200,
    )
    with patch.object(session, "_request", return_value=resp):
        with caplog.at_level(logging.WARNING,
                             logger="festival_organizer.tracklists.api"):
            results = session.search("anything")
    assert results == []
    canary_warnings = [r for r in caplog.records if "Scraping canary" in r.message]
    assert len(canary_warnings) == 1
    msg = canary_warnings[0].message
    assert "search results" in msg
    assert "search form skeleton" in msg
    assert "query='anything'" in msg


def test_fetch_source_info_fires_canary_on_broken_page(caplog):
    """When a source page lacks both the mtb5 type div and the flag img,
    the canary names both missing selectors."""
    session = TracklistSession()
    resp = MagicMock(text="<html><body>no mtb5, no flag</body></html>")
    with patch.object(session, "_request", return_value=resp):
        with caplog.at_level(logging.WARNING,
                             logger="festival_organizer.tracklists.api"):
            session.fetch_source_info("123", "some-venue")
    canary_warnings = [r for r in caplog.records if "Scraping canary" in r.message]
    assert len(canary_warnings) == 1
    msg = canary_warnings[0].message
    assert "source info" in msg
    assert "source type mtb5 div" in msg
    assert "country flag img" in msg
    assert "123/some-venue" in msg


def test_fetch_dj_profile_fires_canary_on_broken_page(caplog):
    """When a DJ page has no og:image meta, the canary fires with the URL."""
    session = TracklistSession()
    resp = MagicMock(text="<html><body>no og meta at all</body></html>")
    with patch.object(session, "_request", return_value=resp):
        with caplog.at_level(logging.WARNING,
                             logger="festival_organizer.tracklists.api"):
            session._fetch_dj_profile("someone")
    canary_warnings = [r for r in caplog.records if "Scraping canary" in r.message]
    assert len(canary_warnings) == 1
    msg = canary_warnings[0].message
    assert "DJ profile" in msg
    assert "og:image meta" in msg
    assert "someone" in msg


def test_search_does_not_fire_canary_on_zero_hits_with_skeleton(caplog):
    """Zero hits for a query is valid; must not emit a canary WARNING."""
    session = TracklistSession()
    resp = MagicMock(
        text='<html><body><input name="main_search"></body></html>',
        status_code=200,
    )
    with patch.object(session, "_request", return_value=resp):
        with caplog.at_level(logging.WARNING,
                             logger="festival_organizer.tracklists.api"):
            results = session.search("noresults")
    assert results == []
    canary_warnings = [r for r in caplog.records if "Scraping canary" in r.message]
    assert canary_warnings == []


def test_export_tracklist_fires_canary_on_structurally_broken_page(caplog):
    """When the tracklist page is missing must-exist markers, the canary
    fires before the AJAX export path even runs."""
    session = TracklistSession()
    broken_html = "<html><body>no tlpItem, no h1, no genre meta</body></html>"
    page_resp = MagicMock(text=broken_html,
                           url="https://www.1001tracklists.com/tracklist/xxx/")
    ajax_resp = MagicMock(text='{"success": true, "data": ""}')
    ajax_resp.json = lambda: {"success": True, "data": ""}

    def fake_request(method, url, **kwargs):
        return ajax_resp if "export_data.php" in url else page_resp

    with patch.object(session, "_request", side_effect=fake_request):
        with patch.object(session, "_fetch_dj_profile",
                          return_value={"artwork_url": ""}):
            with caplog.at_level(logging.WARNING,
                                 logger="festival_organizer.tracklists.api"):
                try:
                    session.export_tracklist("xxx")
                except Exception:
                    pass

    canary_warnings = [r for r in caplog.records if "Scraping canary" in r.message]
    assert len(canary_warnings) >= 1
    msg = canary_warnings[0].message
    assert "tracklist page" in msg
    assert "tlpItem row" in msg
    assert "https://www.1001tracklists.com/tracklist/xxx/" in msg


# --- _run_canary dedupe helper ---

def test_run_canary_no_op_on_healthy_result(caplog):
    session = TracklistSession()
    with caplog.at_level(logging.WARNING, logger="festival_organizer.tracklists.api"):
        session._run_canary("tracklist page", [], "https://example/t/1/")
    warnings_emitted = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings_emitted == []


def test_run_canary_emits_warning_on_missing_selectors(caplog):
    session = TracklistSession()
    with caplog.at_level(logging.WARNING, logger="festival_organizer.tracklists.api"):
        session._run_canary(
            "tracklist page", ["tlpItem row"], "https://example/t/1/"
        )
    records = [r for r in caplog.records if "Scraping canary" in r.message]
    assert len(records) == 1
    msg = records[0].message
    assert "tracklist page" in msg
    assert "tlpItem row" in msg
    assert "https://example/t/1/" in msg


def test_run_canary_dedupes_by_page_type_and_missing_set(caplog):
    """A bulk run with a site-wide break must not spam one WARNING per URL.
    The helper dedupes on (page_type, frozenset(missing)) for the lifetime
    of the session. Subsequent identical hits log at DEBUG."""
    session = TracklistSession()
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.tracklists.api"):
        session._run_canary("tracklist page", ["tlpItem row"], "https://example/t/1/")
        session._run_canary("tracklist page", ["tlpItem row"], "https://example/t/2/")
        session._run_canary("tracklist page", ["tlpItem row"], "https://example/t/3/")

    warnings_emitted = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "Scraping canary" in r.message
    ]
    debugs = [
        r for r in caplog.records
        if r.levelno == logging.DEBUG and "suppressed duplicate" in r.message
    ]
    assert len(warnings_emitted) == 1
    assert len(debugs) == 2


def test_run_canary_distinct_missing_sets_both_emit(caplog):
    """Same page type but different missing selectors is not a duplicate."""
    session = TracklistSession()
    with caplog.at_level(logging.WARNING, logger="festival_organizer.tracklists.api"):
        session._run_canary("tracklist page", ["tlpItem row"], "https://example/a/")
        session._run_canary("tracklist page", ["cue_seconds input"], "https://example/b/")
    warnings_emitted = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "Scraping canary" in r.message
    ]
    assert len(warnings_emitted) == 2


# --- fetch_source_info ---

def test_fetch_source_info_extracts_name_type_country():
    """Baseline: the three fields extracted from a /source/ page.

    Real source pages embed a badge span with the tracklist count and a
    flag img inside div.h. Only the direct text node should be captured.
    """
    html = '''
    <div class="h"> Tomorrowland 2026
        <span class="badge spL hO" title="number of tracklists"> 842 </span>
        <img src="/flags/be.png" alt="Belgium" class="flag">
    </div>
    <div class="cRow"><div class="mtb5">Festival</div></div>
    '''
    session = TracklistSession()
    resp = MagicMock(text=html)
    with patch.object(session, "_request", return_value=resp):
        info = session.fetch_source_info("123", "tomorrowland-2026")
    assert info["name"] == "Tomorrowland 2026"
    assert info["type"] == "Festival"
    assert info["country"] == "Belgium"
    assert info["slug"] == "tomorrowland-2026"


def test_fetch_source_info_parses_reordered_flag_attrs():
    """BS4 migration: the alt attribute may come before src in real
    markup. The pre-migration regex required src first."""
    html = '''
    <div class="h"> Ultra Miami
        <span class="badge spL hO" title="number of tracklists"> 1,203 </span>
        <img alt="United States" class="flag" src="/flags/us.png">
    </div>
    <div class="cRow"><div class="mtb5">Open Air / Festival</div></div>
    '''
    session = TracklistSession()
    resp = MagicMock(text=html)
    with patch.object(session, "_request", return_value=resp):
        info = session.fetch_source_info("1", "ultra-miami")
    assert info["name"] == "Ultra Miami"
    assert info["country"] == "United States"
    assert info["type"] == "Open Air / Festival"


def test_fetch_source_info_falls_back_to_slug_when_name_missing():
    html = '<div class="cRow"><div class="mtb5">Club</div></div>'
    session = TracklistSession()
    resp = MagicMock(text=html)
    with patch.object(session, "_request", return_value=resp):
        info = session.fetch_source_info("99", "warehouse-project")
    assert info["name"] == "Warehouse Project"
    assert info["type"] == "Club"
    assert info["country"] == ""


def test_fetch_dj_profile_rejects_logo_url():
    """DJ profile filter rejects URLs containing 'logo' (case-insensitive)."""
    session = TracklistSession()
    html = '<meta property="og:image" content="https://www.1001tracklists.com/images/static/djLogo_placeholder.jpg">'
    mock_resp = MagicMock()
    mock_resp.text = html
    with patch.object(session, "_request", return_value=mock_resp):
        result = session._fetch_dj_profile("someartist")
    assert result["artwork_url"] == ""


def test_fetch_dj_profile_rejects_static_image():
    """DJ profile filter rejects /images/static/ URLs."""
    session = TracklistSession()
    html = '<meta property="og:image" content="https://www.1001tracklists.com/images/static/header.jpg">'
    mock_resp = MagicMock()
    mock_resp.text = html
    with patch.object(session, "_request", return_value=mock_resp):
        result = session._fetch_dj_profile("someartist")
    assert result["artwork_url"] == ""


def test_fetch_dj_profile_accepts_real_artwork():
    """DJ profile filter accepts real DJ artwork URLs."""
    session = TracklistSession()
    html = '<meta property="og:image" content="https://cdn.1001tracklists.com/images/dj/martingarrix-abc123.jpg">'
    mock_resp = MagicMock()
    mock_resp.text = html
    with patch.object(session, "_request", return_value=mock_resp):
        result = session._fetch_dj_profile("martingarrix")
    assert result["artwork_url"] == "https://cdn.1001tracklists.com/images/dj/martingarrix-abc123.jpg"


def test_request_raises_on_persistent_5xx():
    """After all retries on 502/503/504, raise TracklistError instead of returning bad response."""
    session = TracklistSession()

    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.text = "Bad Gateway"

    with patch.object(session._session, "get", return_value=mock_resp):
        with pytest.raises(TracklistError, match="502"):
            session._request("GET", "http://example.com", max_retries=2)


# --- _maximize_artwork_url tests ---

def test_maximize_artwork_url_soundcloud_t500x500():
    """SoundCloud t500x500 is rewritten to original."""
    url = "https://i1.sndcdn.com/avatars-vjum1BRzTUg83HKy-yajRWQ-t500x500.jpg"
    assert _maximize_artwork_url(url) == "https://i1.sndcdn.com/avatars-vjum1BRzTUg83HKy-yajRWQ-original.jpg"


def test_maximize_artwork_url_soundcloud_t300x300():
    """SoundCloud t300x300 is also rewritten to original."""
    url = "https://i1.sndcdn.com/avatars-abc123-t300x300.jpg"
    assert _maximize_artwork_url(url) == "https://i1.sndcdn.com/avatars-abc123-original.jpg"


def test_maximize_artwork_url_squarespace_strips_format():
    """Squarespace format=NNNw query param is stripped."""
    url = "https://images.squarespace-cdn.com/content/v1/abc/image.jpg?format=300w"
    assert _maximize_artwork_url(url) == "https://images.squarespace-cdn.com/content/v1/abc/image.jpg"


def test_maximize_artwork_url_youtube_passthrough():
    """YouTube profile pic URLs pass through unchanged. The CDN does not
    reliably serve arbitrary size suffixes, so we keep the size 1001TL
    embeds (which YouTube has guaranteed is available)."""
    url = "https://yt3.ggpht.com/GE5UaHPciygWU-7lj-8gfnkLJFOqQGMN0x3_eD7tlWfeLJQVMZGwIKdmxtMy0kAHb3A4xrPZEA=s500-c-k-c0x00ffffff-no-rj"
    assert _maximize_artwork_url(url) == url


def test_maximize_artwork_url_unknown_cdn_passthrough():
    """Unknown CDN URLs pass through unchanged."""
    url = "https://cdn.1001tracklists.com/images/dj/someone-abc.jpg"
    assert _maximize_artwork_url(url) == url


def test_maximize_artwork_url_empty_string():
    """Empty string returns empty string."""
    assert _maximize_artwork_url("") == ""


def test_parse_dj_profile_extracts_aliases_and_member_of():
    """Baseline: the section walker finds aliases and group memberships."""
    html = '''
    <meta property="og:image" content="https://cdn.1001tracklists.com/dj.jpg">
    <div class="h">Aliases</div>
    <div class="c ptb5">
      <a href="/dj/alt-name/index.html">Alt Name</a>
    </div>
    <div class="h">Member Of</div>
    <div class="c ptb5">
      <a href="/dj/some-group/index.html">Some Group</a>
    </div>
    '''
    result = _parse_dj_profile(html)
    assert result["aliases"] == [{"slug": "alt-name", "name": "Alt Name"}]
    assert result["member_of"] == [{"slug": "some-group", "name": "Some Group"}]


def test_parse_dj_profile_finds_og_image_with_reordered_attrs():
    """BS4 migration: og:image meta may emit attributes in either order."""
    html = '<meta content="https://cdn.1001tracklists.com/images/dj/photo.jpg" property="og:image">'
    result = _parse_dj_profile(html)
    assert result["artwork_url"] == "https://cdn.1001tracklists.com/images/dj/photo.jpg"


def test_parse_dj_profile_survives_single_quoted_og_image():
    html = "<meta property='og:image' content='https://cdn.1001tracklists.com/images/dj/photo.jpg'>"
    result = _parse_dj_profile(html)
    assert result["artwork_url"] == "https://cdn.1001tracklists.com/images/dj/photo.jpg"


def test_parse_dj_profile_empty_when_no_markers():
    result = _parse_dj_profile("<html>nothing</html>")
    assert result == {"artwork_url": "", "aliases": [], "member_of": []}


def test_fetch_dj_profile_maximizes_squarespace_url():
    """_fetch_dj_profile applies URL maximization to Squarespace URLs."""
    session = TracklistSession()
    html = '<meta property="og:image" content="https://images.squarespace-cdn.com/content/v1/abc/image.jpg?format=300w">'
    mock_resp = MagicMock()
    mock_resp.text = html
    with patch.object(session, "_request", return_value=mock_resp):
        result = session._fetch_dj_profile("someone")
    assert result["artwork_url"] == "https://images.squarespace-cdn.com/content/v1/abc/image.jpg"


# --- Encoding fix ---

def test_request_forces_utf8_encoding(tmp_path):
    """TracklistSession._request must set resp.encoding = 'utf-8' so that
    .text decodes UTF-8 bytes correctly even when the server does not
    include charset= in Content-Type (requests defaults to ISO-8859-1 for
    text/* responses per RFC 7231, which produces mojibake on UTF-8 bodies)."""
    from festival_organizer.tracklists.api import TracklistSession
    # "Tiësto" in UTF-8 bytes: 54 69 C3 AB 73 74 6F
    utf8_bytes = "Tiësto".encode("utf-8")

    with patch.object(TracklistSession, "throttle"):
        sess = TracklistSession(cookie_cache_path=tmp_path / "cookies.json")
        # Mock the underlying session.get to return a response with no
        # charset header; requests would otherwise default to ISO-8859-1.
        resp = MagicMock()
        resp.status_code = 200
        resp.content = utf8_bytes
        resp.encoding = "ISO-8859-1"  # what requests would default to
        resp.text = utf8_bytes.decode("ISO-8859-1")  # mojibake
        # Make .text recompute when encoding is set
        def text_property(self):
            return self.content.decode(self.encoding)
        type(resp).text = PropertyMock(side_effect=lambda: resp.content.decode(resp.encoding))
        sess._session.get = MagicMock(return_value=resp)

        result = sess._request("GET", "https://example.com/page")

    assert result.encoding == "utf-8"
    assert result.text == "Tiësto"


# --- export_tracklist on_progress callback ---

_ARMIN_MARLON_FIXTURE = (
    Path(__file__).parent / "tracklists" / "fixtures" / "armin_marlon_ultra_miami_2026.html"
)


def _build_export_mock_responses(page_html: str):
    """Return a callable suitable for patching TracklistSession._request.

    First call (GET page) returns a response carrying the fixture HTML.
    Second call (POST export AJAX) returns a JSON-shaped response with a
    minimal successful export payload.
    """
    page_resp = MagicMock()
    page_resp.text = page_html
    page_resp.url = "https://www.1001tracklists.com/tracklist/abc123/armin-marlon-ultra-miami-2026.html"

    ajax_resp = MagicMock()
    ajax_resp.json.return_value = {
        "success": True,
        "data": "00:00 Track One\n01:00 Track Two\n",
    }

    responses = [page_resp, ajax_resp]
    calls = {"i": 0}

    def _side_effect(method, url, *args, **kwargs):
        i = calls["i"]
        calls["i"] += 1
        if i < len(responses):
            return responses[i]
        # Any additional calls (e.g. stray requests) get an empty response
        extra = MagicMock()
        extra.text = ""
        extra.json.return_value = {"success": False, "message": "unexpected"}
        return extra

    return _side_effect


def test_export_tracklist_invokes_on_progress_with_dj_count():
    """When on_progress is provided, it's called exactly once with the count
    of DJs to fetch (which drives the fetch loop), not just DJs parsed from h1.
    """
    page_html = _ARMIN_MARLON_FIXTURE.read_text(encoding="utf-8")
    session = TracklistSession()

    calls: list[str] = []
    with patch.object(session, "_request", side_effect=_build_export_mock_responses(page_html)):
        with patch.object(session, "_fetch_dj_profile", return_value={"artwork_url": ""}):
            session.export_tracklist(
                "abc123",
                on_progress=lambda msg: calls.append(msg),
            )

    assert len(calls) == 1
    assert "2" in calls[0]
    assert "DJ" in calls[0]


def test_export_tracklist_callback_counts_dj_slugs_not_just_dj_artists(monkeypatch):
    """When dj_artists is empty but the dj_slugs fallback finds DJs on the
    page, the callback must report the dj_slugs count (which drives the
    actual fetch loop), not zero.
    """
    from festival_organizer.tracklists import api as api_module

    # Fallback path: parse finds no h1 DJ artists, but _extract_dj_slugs
    # picks up links elsewhere on the page.
    monkeypatch.setattr(
        api_module,
        "_extract_dj_slugs",
        lambda html: ["dj-one", "dj-two", "dj-three"],
    )

    # Force h1 parser to yield empty dj_artists so the fallback branch runs.
    original_parse_h1 = api_module._parse_h1_structure

    def _parse_h1_no_djs(h1_html: str) -> dict:
        info = original_parse_h1(h1_html)
        info["dj_artists"] = []
        return info

    monkeypatch.setattr(api_module, "_parse_h1_structure", _parse_h1_no_djs)

    page_html = _ARMIN_MARLON_FIXTURE.read_text(encoding="utf-8")
    session = TracklistSession()

    calls: list[str] = []
    with patch.object(session, "_request", side_effect=_build_export_mock_responses(page_html)):
        with patch.object(session, "_fetch_dj_profile", return_value={"artwork_url": ""}):
            session.export_tracklist(
                "abc123",
                on_progress=lambda msg: calls.append(msg),
            )

    assert len(calls) == 1
    assert "3" in calls[0]  # reflects dj_slugs count, not dj_artists
    assert "DJ" in calls[0]


def test_export_tracklist_no_callback_does_not_crash():
    """When on_progress is None, behaviour is unchanged."""
    page_html = _ARMIN_MARLON_FIXTURE.read_text(encoding="utf-8")
    session = TracklistSession()

    with patch.object(session, "_request", side_effect=_build_export_mock_responses(page_html)):
        with patch.object(session, "_fetch_dj_profile", return_value={"artwork_url": ""}):
            export = session.export_tracklist("abc123")

    assert export is not None
    assert len(export.dj_artists) == 2


# --- h1 location surfacing + suppression ---

def _build_minimal_page_html(h1_inner: str) -> str:
    """Wrap a bare h1 payload in a minimal HTML document that the exporter
    can parse (the exporter only needs <title> and <h1>)."""
    return (
        "<html><head><title>Fred again.. @ USB002 | 1001Tracklists</title>"
        "</head><body>"
        f'<h1 class="notranslate">{h1_inner}</h1>'
        "</body></html>"
    )


class _StubSourceCache:
    """Minimal source cache double: pre-seeded with per-id type entries."""

    def __init__(self, entries: dict[str, dict]):
        self._data = dict(entries)

    def get(self, sid: str):
        return self._data.get(sid)

    def put(self, sid: str, entry: dict) -> None:
        self._data[sid] = entry

    def group_by_type(self, source_ids: list[str]) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for sid in source_ids:
            entry = self._data.get(sid)
            if entry:
                groups.setdefault(entry["type"], []).append(entry["name"])
        return groups


def test_export_tracklist_surfaces_h1_location():
    """When the h1 tail carries a middle venue string and no linked source
    is of a location-bearing type, export.location reflects that string."""
    h1_inner = (
        '<a href="/dj/fredagain/index.html" class="notranslate ">Fred again..</a>'
        ' @ <a href="/source/abc/usb002/index.html">USB002</a>,'
        " Alexandra Palace London, United Kingdom 2026-02-27"
    )
    page_html = _build_minimal_page_html(h1_inner)

    # Event Promoter is NOT location-bearing, so suppression must not fire.
    cache = _StubSourceCache({
        "abc": {"name": "USB002", "type": "Event Promoter",
                "country": "United Kingdom"},
    })
    session = TracklistSession(source_cache=cache)

    with patch.object(session, "_request",
                      side_effect=_build_export_mock_responses(page_html)):
        with patch.object(session, "_fetch_dj_profile",
                          return_value={"artwork_url": ""}):
            export = session.export_tracklist("abc123")

    assert export.location == "Alexandra Palace London"


def test_export_tracklist_suppresses_location_when_festival_source_present():
    """Linked 'Open Air / Festival' source is authoritative; the h1
    middle location is suppressed to avoid duplicate / stale data."""
    h1_inner = (
        '<a href="/dj/fredagain/index.html" class="notranslate ">Fred again..</a>'
        ' @ <a href="/source/fest/some-festival/index.html">Some Festival</a>,'
        " Alexandra Palace London, United Kingdom 2026-02-27"
    )
    page_html = _build_minimal_page_html(h1_inner)

    cache = _StubSourceCache({
        "fest": {"name": "Some Festival", "type": "Open Air / Festival",
                 "country": "United Kingdom"},
    })
    session = TracklistSession(source_cache=cache)

    with patch.object(session, "_request",
                      side_effect=_build_export_mock_responses(page_html)):
        with patch.object(session, "_fetch_dj_profile",
                          return_value={"artwork_url": ""}):
            export = session.export_tracklist("abc123")

    assert export.location == ""


def test_export_tracklist_suppresses_location_when_event_location_source_present():
    """Linked 'Event Location' source suppresses the h1 location too."""
    h1_inner = (
        '<a href="/dj/fredagain/index.html" class="notranslate ">Fred again..</a>'
        ' @ <a href="/source/venue/alexandra-palace/index.html">Alexandra Palace</a>,'
        " Alexandra Palace London, United Kingdom 2026-02-27"
    )
    page_html = _build_minimal_page_html(h1_inner)

    cache = _StubSourceCache({
        "venue": {"name": "Alexandra Palace", "type": "Event Location",
                  "country": "United Kingdom"},
    })
    session = TracklistSession(source_cache=cache)

    with patch.object(session, "_request",
                      side_effect=_build_export_mock_responses(page_html)):
        with patch.object(session, "_fetch_dj_profile",
                          return_value={"artwork_url": ""}):
            export = session.export_tracklist("abc123")

    assert export.location == ""


def test_export_tracklist_captures_h1_event_date():
    """The trailing ISO date in the h1 tail is surfaced on export.date so
    downstream callers can write CRATEDIGGER_1001TL_DATE even when the search
    result date was missing (Red Rocks reproduction)."""
    h1_inner = (
        '<a href="/dj/martingarrix/index.html" class="notranslate ">Martin Garrix</a>'
        " &amp; "
        '<a href="/dj/alesso/index.html" class="notranslate ">Alesso</a>'
        ' @ <a href="/source/venue/red-rocks/index.html">Red Rocks Amphitheatre</a>,'
        " United States 2025-10-24"
    )
    page_html = _build_minimal_page_html(h1_inner)

    cache = _StubSourceCache({
        "venue": {"name": "Red Rocks Amphitheatre", "type": "Event Location",
                  "country": "United States"},
    })
    session = TracklistSession(source_cache=cache)

    with patch.object(session, "_request",
                      side_effect=_build_export_mock_responses(page_html)):
        with patch.object(session, "_fetch_dj_profile",
                          return_value={"artwork_url": ""}):
            export = session.export_tracklist("abc123")

    assert export.date == "2025-10-24"


def test_export_tracklist_date_empty_when_h1_has_no_date():
    """When the h1 has no trailing ISO date, export.date stays empty."""
    h1_inner = (
        '<a href="/dj/tiesto/index.html" class="notranslate ">Tiesto</a>'
        ' @ Mainstage, <a href="/source/fgcfkm/tomorrowland/index.html">Tomorrowland</a>'
    )
    page_html = _build_minimal_page_html(h1_inner)
    session = TracklistSession()

    with patch.object(session, "_request",
                      side_effect=_build_export_mock_responses(page_html)):
        with patch.object(session, "_fetch_dj_profile",
                          return_value={"artwork_url": ""}):
            export = session.export_tracklist("abc123")

    assert export.date == ""


# --- Tier 2 DEBUG logging for retry loop and export JSON decode ---

def test_request_retry_429_logs_debug_with_reason_and_wait(caplog):
    """A 429 retry logs DEBUG naming the rate-limit reason, attempt, and wait."""
    session = TracklistSession()

    mock_resp_bad = MagicMock()
    mock_resp_bad.status_code = 429
    mock_resp_bad.text = ""
    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.text = "ok"

    with patch.object(session._session, "get",
                      side_effect=[mock_resp_bad, mock_resp_ok]):
        with patch("festival_organizer.tracklists.api.time.sleep") as sleep_mock:
            with caplog.at_level(logging.DEBUG,
                                 logger="festival_organizer.tracklists.api"):
                resp = session._request("GET", "http://example.com", max_retries=3)

    assert resp is mock_resp_ok
    sleep_mock.assert_called_once_with(30)
    joined = "\n".join(r.message for r in caplog.records)
    assert "429" in joined
    assert "rate limit" in joined.lower()
    assert "1/3" in joined
    assert "30" in joined


def test_request_retry_5xx_logs_debug_with_status_and_wait(caplog):
    """A 502/503/504 retry logs DEBUG naming the HTTP status, attempt, and wait."""
    session = TracklistSession()

    mock_resp_bad = MagicMock()
    mock_resp_bad.status_code = 503
    mock_resp_bad.text = "Service Unavailable"
    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.text = "ok"

    with patch.object(session._session, "get",
                      side_effect=[mock_resp_bad, mock_resp_ok]):
        with patch("festival_organizer.tracklists.api.time.sleep"):
            with caplog.at_level(logging.DEBUG,
                                 logger="festival_organizer.tracklists.api"):
                session._request("GET", "http://example.com", max_retries=3)

    joined = "\n".join(r.message for r in caplog.records)
    assert "HTTP 503" in joined
    assert "1/3" in joined


def test_request_retry_network_exception_logs_debug_with_exc_and_wait(caplog):
    """A RequestException retry logs DEBUG naming the network error and wait."""
    session = TracklistSession()

    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.text = "ok"

    with patch.object(session._session, "get",
                      side_effect=[requests.ConnectionError("conn reset"),
                                   mock_resp_ok]):
        with patch("festival_organizer.tracklists.api.time.sleep"):
            with caplog.at_level(logging.DEBUG,
                                 logger="festival_organizer.tracklists.api"):
                session._request("GET", "http://example.com", max_retries=3)

    joined = "\n".join(r.message for r in caplog.records)
    assert "network" in joined.lower()
    assert "conn reset" in joined
    assert "1/3" in joined


def test_export_tracklist_logs_debug_on_invalid_json(caplog):
    """ExportError on malformed JSON response includes a DEBUG trail before raise."""
    session = TracklistSession()

    page_resp = MagicMock()
    page_resp.url = "https://www.1001tracklists.com/tracklist/abc123/"
    page_resp.text = "<html><title>Test</title></html>"

    export_resp = MagicMock()
    export_resp.url = "https://www.1001tracklists.com/ajax/export_data.php"
    export_resp.json.side_effect = ValueError("malformed")

    with patch.object(session, "_request",
                      side_effect=[page_resp, export_resp]):
        with patch.object(session, "_run_canary"):
            with caplog.at_level(logging.DEBUG,
                                 logger="festival_organizer.tracklists.api"):
                with pytest.raises(ExportError, match="Invalid JSON"):
                    session.export_tracklist("abc123")

    joined = "\n".join(r.message for r in caplog.records)
    assert "Export JSON decode failed" in joined
    assert "malformed" in joined
    # The log must identify the actual failing request (the AJAX export
    # endpoint + tracklist id), NOT the incoming tracklist page URL. The
    # tracklist page HTML was already parsed successfully before this
    # point; attributing the JSON decode failure to the page would mislead
    # anyone reading the log.
    assert "abc123" in joined
    assert "export_data.php" in joined
    assert "tracklist/abc123/" not in joined
