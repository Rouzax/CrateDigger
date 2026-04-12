from unittest.mock import MagicMock
from festival_organizer.tracklists.dj_cache import DjCache


def test_get_or_fetch_many_hits_cache(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("afrojack", {"name": "Afrojack"})
    cache.put("tiesto", {"name": "Tiesto"})
    fetcher = MagicMock()
    result = cache.get_or_fetch_many(["afrojack", "tiesto"], fetcher=fetcher)
    assert result["afrojack"]["name"] == "Afrojack"
    assert result["tiesto"]["name"] == "Tiesto"
    fetcher.assert_not_called()


def test_get_or_fetch_many_fetches_misses(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("afrojack", {"name": "Afrojack"})

    def fetcher(slug: str) -> dict:
        return {"name": slug.title()}

    result = cache.get_or_fetch_many(["afrojack", "newdj"], fetcher=fetcher)
    assert result["afrojack"]["name"] == "Afrojack"
    assert result["newdj"]["name"] == "Newdj"
    assert cache.get("newdj")["name"] == "Newdj"


def test_get_or_fetch_many_skips_failed_fetches(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)

    def fetcher(slug):
        return None if slug == "gone" else {"name": slug.title()}

    result = cache.get_or_fetch_many(["gone", "ok"], fetcher=fetcher)
    assert "gone" not in result
    assert result["ok"]["name"] == "Ok"


def test_get_or_fetch_many_dedupes_input(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    calls = []

    def fetcher(slug):
        calls.append(slug)
        return {"name": slug.title()}

    cache.get_or_fetch_many(["a", "a", "b", "a"], fetcher=fetcher)
    assert sorted(calls) == ["a", "b"]


def test_get_or_fetch_many_calls_progress(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    events = []

    def fetcher(slug):
        return {"name": slug.title()}

    def progress(slug, done, total):
        events.append((slug, done, total))

    cache.get_or_fetch_many(["a", "b"], fetcher=fetcher, progress=progress)
    assert events == [("a", 1, 2), ("b", 2, 2)]


def test_get_or_fetch_many_progress_not_called_when_all_cached(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("a", {"name": "A"})
    calls = []
    cache.get_or_fetch_many(["a"], fetcher=lambda s: {"name": s},
                            progress=lambda *args: calls.append(args))
    assert calls == []
