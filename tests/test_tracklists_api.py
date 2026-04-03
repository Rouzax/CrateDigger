"""Tests for 1001Tracklists API layer (all mocked, no real network calls)."""
import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from festival_organizer.tracklists.api import (
    TracklistSession,
    TracklistError,
    AuthenticationError,
    RateLimitError,
    ExportError,
    _parse_duration_string,
    _html_decode,
    _normalize_date,
    _is_rate_limited,
    _extract_genres,
    _extract_dj_slugs,
    _maximize_artwork_url,
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
    # Point cookie path to a non-existent subdirectory so write fails with OSError
    session = TracklistSession(cookie_cache_path=tmp_path / "nonexistent_subdir" / "cookies.json")

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


def test_maximize_artwork_url_youtube_s500_to_s800():
    """YouTube profile pic s500 is upgraded to s800."""
    url = "https://yt3.ggpht.com/GE5UaHPciygWU-7lj-8gfnkLJFOqQGMN0x3_eD7tlWfeLJQVMZGwIKdmxtMy0kAHb3A4xrPZEA=s500-c-k-c0x00ffffff-no-rj"
    assert _maximize_artwork_url(url) == "https://yt3.ggpht.com/GE5UaHPciygWU-7lj-8gfnkLJFOqQGMN0x3_eD7tlWfeLJQVMZGwIKdmxtMy0kAHb3A4xrPZEA=s800-c-k-c0x00ffffff-no-rj"


def test_maximize_artwork_url_unknown_cdn_passthrough():
    """Unknown CDN URLs pass through unchanged."""
    url = "https://cdn.1001tracklists.com/images/dj/someone-abc.jpg"
    assert _maximize_artwork_url(url) == url


def test_maximize_artwork_url_empty_string():
    """Empty string returns empty string."""
    assert _maximize_artwork_url("") == ""


def test_fetch_dj_profile_maximizes_squarespace_url():
    """_fetch_dj_profile applies URL maximization to Squarespace URLs."""
    session = TracklistSession()
    html = '<meta property="og:image" content="https://images.squarespace-cdn.com/content/v1/abc/image.jpg?format=300w">'
    mock_resp = MagicMock()
    mock_resp.text = html
    with patch.object(session, "_request", return_value=mock_resp):
        result = session._fetch_dj_profile("someone")
    assert result["artwork_url"] == "https://images.squarespace-cdn.com/content/v1/abc/image.jpg"
