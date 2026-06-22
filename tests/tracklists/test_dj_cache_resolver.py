from festival_organizer.tracklists.dj_cache import DjCache


def _cache(tmp_path):
    c = DjCache(cache_path=tmp_path / "dj_cache.json")
    c._data = {
        "aboveandbeyond": {
            "name": "Above & Beyond",
            "aliases": [],
            "ts": 9e9,
            "ttl": 9e9,
        },
        "tiesto": {
            "name": "Tiësto",
            "aliases": [{"slug": "verwest", "name": "VER:WEST"}],
            "ts": 9e9,
            "ttl": 9e9,
        },
        "fredagain..": {"name": "Fred again..", "aliases": [], "ts": 9e9, "ttl": 9e9},
    }
    return c


def test_slug_for_name_resolves_canonical_and_variants(tmp_path):
    c = _cache(tmp_path)
    assert c.slug_for_name("Above & Beyond") == "aboveandbeyond"
    assert c.slug_for_name("Tiësto") == "tiesto"
    assert c.slug_for_name("Tiesto") == "tiesto"
    assert c.slug_for_name("Fred again") == "fredagain.."
    assert c.slug_for_name("VER:WEST") == "tiesto"
    assert c.slug_for_name("Unknown DJ") is None


def test_derive_entry_names_lowercased(tmp_path):
    c = _cache(tmp_path)
    names = c.derive_entry_names()
    assert "above & beyond" in names
    assert "fred again.." in names


def test_slugs_returns_keys(tmp_path):
    c = _cache(tmp_path)
    assert c.slugs() == {"aboveandbeyond", "tiesto", "fredagain.."}
