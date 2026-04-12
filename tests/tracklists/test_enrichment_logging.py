"""Logging and progress behaviour for per-track artist fetching."""
import logging
from unittest.mock import MagicMock, patch

from festival_organizer.tracklists.api import Track
from festival_organizer.tracklists.chapters import embed_chapters
from festival_organizer.tracklists.dj_cache import DjCache


def _make_mkv(tmp_path):
    fake = tmp_path / "x.mkv"
    fake.write_bytes(b"")
    return fake


def test_no_fetches_when_all_cached(tmp_path, caplog):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("a", {"name": "A"})
    cache.put("b", {"name": "B"})

    fetcher = MagicMock()
    tracks = [
        Track(start_ms=0, raw_text="x", artist_slugs=["a"], genres=[]),
        Track(start_ms=60000, raw_text="y", artist_slugs=["b"], genres=[]),
    ]
    fake = _make_mkv(tmp_path)

    caplog.set_level(logging.INFO, logger="festival_organizer.tracklists.chapters")
    with patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"), \
         patch("festival_organizer.tracklists.chapters.write_merged_tags", return_value=True), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
        embed_chapters(fake, chapters=[], tracklist_url="https://x",
                       tracks=tracks, dj_cache=cache, fetcher=fetcher)

    fetcher.assert_not_called()
    msgs = [r.message for r in caplog.records]
    assert any("Resolved 2 per-track artists (2 cached, 0 fetched)" in m for m in msgs)


def test_fetch_loop_triggers_when_missing(tmp_path, caplog):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)

    def fetcher(slug):
        return {"name": slug.title()}

    tracks = [
        Track(start_ms=0, raw_text="x", artist_slugs=["a", "b"], genres=[]),
    ]
    fake = _make_mkv(tmp_path)

    caplog.set_level(logging.INFO, logger="festival_organizer.tracklists.chapters")
    with patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"), \
         patch("festival_organizer.tracklists.chapters.write_merged_tags", return_value=True), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
        embed_chapters(fake, chapters=[], tracklist_url="https://x",
                       tracks=tracks, dj_cache=cache, fetcher=fetcher)

    assert cache.get("a")["name"] == "A"
    assert cache.get("b")["name"] == "B"
    msgs = [r.message for r in caplog.records]
    assert any("0 cached, 2 fetched" in m for m in msgs)


def test_warning_on_failed_fetch(tmp_path, caplog):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)

    def fetcher(slug):
        return None

    tracks = [Track(start_ms=0, raw_text="x", artist_slugs=["gone"], genres=[])]
    fake = _make_mkv(tmp_path)
    caplog.set_level(logging.WARNING, logger="festival_organizer.tracklists.dj_cache")
    with patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"), \
         patch("festival_organizer.tracklists.chapters.write_merged_tags", return_value=True), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
        embed_chapters(fake, chapters=[], tracklist_url="https://x",
                       tracks=tracks, dj_cache=cache, fetcher=fetcher)
    msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("gone" in m for m in msgs)


def test_no_fetch_triggered_without_fetcher(tmp_path, caplog):
    """Back-compat: callers that don't pass fetcher don't trigger any fetch."""
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    tracks = [Track(start_ms=0, raw_text="x", artist_slugs=["uncached"], genres=[])]
    fake = _make_mkv(tmp_path)
    caplog.set_level(logging.INFO, logger="festival_organizer.tracklists.chapters")
    with patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"), \
         patch("festival_organizer.tracklists.chapters.write_merged_tags", return_value=True), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
        embed_chapters(fake, chapters=[], tracklist_url="https://x",
                       tracks=tracks, dj_cache=cache)
    msgs = [r.message for r in caplog.records]
    assert not any("Resolved" in m and "per-track artists" in m for m in msgs)
