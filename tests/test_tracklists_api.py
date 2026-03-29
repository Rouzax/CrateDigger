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

    with patch.object(session, "_restore_cookies", return_value=False):
        with patch.object(session._session, "post", return_value=mock_resp):
            with pytest.raises(AuthenticationError, match="missing session cookies"):
                session.login("test@test.com", "wrong")


def test_request_raises_on_persistent_5xx():
    """After all retries on 502/503/504, raise TracklistError instead of returning bad response."""
    session = TracklistSession()

    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.text = "Bad Gateway"

    with patch.object(session._session, "get", return_value=mock_resp):
        with pytest.raises(TracklistError, match="502"):
            session._request("GET", "http://example.com", max_retries=2)
