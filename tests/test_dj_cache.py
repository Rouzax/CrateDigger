"""Tests for DJ cache and DJ profile parsing."""
from festival_organizer.tracklists.dj_cache import DjCache
from festival_organizer.tracklists.api import _parse_dj_profile


# -- DjCache tests --


def test_dj_cache_put_get(tmp_path):
    cache = DjCache(tmp_path / "dj_cache.json")
    cache.put("tiesto", {
        "name": "Tiesto",
        "artwork_url": "https://example.com/tiesto.jpg",
        "aliases": [{"slug": "verwest", "name": "VER:WEST"}],
        "member_of": [],
    })
    entry = cache.get("tiesto")
    assert entry["name"] == "Tiesto"
    assert entry["aliases"][0]["name"] == "VER:WEST"


def test_dj_cache_persistence(tmp_path):
    path = tmp_path / "dj_cache.json"
    cache1 = DjCache(path)
    cache1.put("tiesto", {"name": "Tiesto", "artwork_url": "", "aliases": [], "member_of": []})
    cache2 = DjCache(path)
    assert cache2.get("tiesto")["name"] == "Tiesto"


def test_dj_cache_derive_aliases(tmp_path):
    cache = DjCache(tmp_path / "dj_cache.json")
    cache.put("tiesto", {
        "name": "Tiesto",
        "artwork_url": "",
        "aliases": [{"slug": "verwest", "name": "VER:WEST"}, {"slug": "allurenl", "name": "Allure"}],
        "member_of": [],
    })
    aliases = cache.derive_artist_aliases()
    assert aliases["VER:WEST"] == "Tiesto"
    assert aliases["Allure"] == "Tiesto"


def test_dj_cache_derive_groups(tmp_path):
    cache = DjCache(tmp_path / "dj_cache.json")
    cache.put("arminvanbuuren", {
        "name": "Armin van Buuren",
        "artwork_url": "",
        "aliases": [],
        "member_of": [{"slug": "gaia-nl", "name": "Gaia"}],
    })
    groups = cache.derive_artist_groups()
    assert "gaia" in groups


def test_dj_cache_empty(tmp_path):
    cache = DjCache(tmp_path / "dj_cache.json")
    assert cache.get("nonexistent") is None
    assert cache.derive_artist_aliases() == {}
    assert cache.derive_artist_groups() == set()


def test_dj_cache_expired_entry_is_miss(tmp_path):
    """Expired entry should return None on get()."""
    cache = DjCache(tmp_path / "dj_cache.json", ttl_days=0)
    cache.put("tiesto", {"name": "Tiesto", "artwork_url": "", "aliases": [], "member_of": []})
    assert cache.get("tiesto") is None


def test_dj_cache_old_entries_without_ts_expire(tmp_path):
    """Entries without ts field (from old cache) should be treated as expired."""
    import json
    path = tmp_path / "dj_cache.json"
    path.write_text(json.dumps({"tiesto": {"name": "Tiesto", "artwork_url": "", "aliases": [], "member_of": []}}))
    cache = DjCache(path, ttl_days=90)
    assert cache.get("tiesto") is None


def test_dj_cache_derive_group_members(tmp_path):
    """derive_group_members builds group -> [member] mapping."""
    cache = DjCache(tmp_path / "dj_cache.json")
    cache.put("arminvanbuuren", {
        "name": "Armin van Buuren", "artwork_url": "",
        "aliases": [], "member_of": [{"slug": "gaia-nl", "name": "Gaia"}],
    })
    cache.put("rank1", {
        "name": "Rank 1", "artwork_url": "",
        "aliases": [], "member_of": [{"slug": "gaia-nl", "name": "Gaia"}],
    })
    members = cache.derive_group_members()
    assert "Gaia" in members
    assert sorted(members["Gaia"]) == ["Armin van Buuren", "Rank 1"]


def test_dj_cache_derive_group_members_empty(tmp_path):
    """derive_group_members returns empty dict when no groups."""
    cache = DjCache(tmp_path / "dj_cache.json")
    cache.put("tiesto", {
        "name": "Tiesto", "artwork_url": "",
        "aliases": [], "member_of": [],
    })
    assert cache.derive_group_members() == {}


def test_dj_cache_derive_group_members_includes_expired(tmp_path):
    """derive_group_members uses all data including expired entries."""
    cache = DjCache(tmp_path / "dj_cache.json", ttl_days=0)
    cache.put("arminvanbuuren", {
        "name": "Armin van Buuren", "artwork_url": "",
        "aliases": [], "member_of": [{"slug": "gaia-nl", "name": "Gaia"}],
    })
    members = cache.derive_group_members()
    assert members == {"Gaia": ["Armin van Buuren"]}


def test_dj_cache_derive_group_members_multi_group(tmp_path):
    """DJ in multiple groups appears in each group's member list."""
    cache = DjCache(tmp_path / "dj_cache.json")
    cache.put("axwell", {
        "name": "Axwell", "artwork_url": "",
        "aliases": [],
        "member_of": [
            {"slug": "swedishhousemafia", "name": "Swedish House Mafia"},
            {"slug": "axwellandingrosso", "name": "Axwell Ingrosso"},
        ],
    })
    members = cache.derive_group_members()
    assert members["Swedish House Mafia"] == ["Axwell"]
    assert members["Axwell Ingrosso"] == ["Axwell"]


def test_dj_cache_derive_aliases_includes_expired(tmp_path):
    """derive_artist_aliases uses all data including expired entries."""
    cache = DjCache(tmp_path / "dj_cache.json", ttl_days=0)
    cache.put("tiesto", {
        "name": "Tiesto", "artwork_url": "",
        "aliases": [{"name": "VER:WEST"}], "member_of": [],
    })
    # Entry is expired for get(), but derive still uses it
    aliases = cache.derive_artist_aliases()
    assert aliases["VER:WEST"] == "Tiesto"


# -- _parse_dj_profile tests --


def test_parse_dj_profile_aliases():
    html = '''<meta property="og:image" content="https://example.com/art.jpg">
    <div class="h">Aliases</div>
    <div class="c ptb5"><a href="/dj/verwest/index.html" class="notranslate ">VER:WEST</a> <img src="/images/flags/nl.png"></div>
    <div class="c ptb5"><a href="/dj/allurenl/index.html" class="notranslate ">Allure</a> <img src="/images/flags/nl.png"></div>
    <div class="h">Hosted Shows / Podcasts</div>'''
    result = _parse_dj_profile(html)
    assert result["artwork_url"] == "https://example.com/art.jpg"
    assert result["aliases"] == [{"slug": "verwest", "name": "VER:WEST"}, {"slug": "allurenl", "name": "Allure"}]
    assert result["member_of"] == []


def test_parse_dj_profile_member_of():
    html = '''<meta property="og:image" content="https://example.com/art.jpg">
    <div class="h">Member Of</div>
    <div class="c ptb5"><a href="/dj/gaia-nl/index.html" class="notranslate ">Gaia</a></div>
    <div class="h">Hosted Shows / Podcasts</div>'''
    result = _parse_dj_profile(html)
    assert result["member_of"] == [{"slug": "gaia-nl", "name": "Gaia"}]
    assert result["aliases"] == []


def test_parse_dj_profile_both():
    html = '''<meta property="og:image" content="https://example.com/art.jpg">
    <div class="h">Member Of</div>
    <div class="c ptb5"><a href="/dj/logica/index.html" class="notranslate ">Logica</a></div>
    <div class="h">Aliases</div>
    <div class="c ptb5"><a href="/dj/somethingelse-br/index.html" class="notranslate ">SOMETHING ELSE</a></div>
    <div class="h">Hosted Shows / Podcasts</div>'''
    result = _parse_dj_profile(html)
    assert result["aliases"] == [{"slug": "somethingelse-br", "name": "SOMETHING ELSE"}]
    assert result["member_of"] == [{"slug": "logica", "name": "Logica"}]


def test_parse_dj_profile_no_sections():
    html = '<meta property="og:image" content="https://example.com/art.jpg"><div class="h">Hosted Shows</div>'
    result = _parse_dj_profile(html)
    assert result["aliases"] == []
    assert result["member_of"] == []
    assert result["artwork_url"] == "https://example.com/art.jpg"


def test_parse_dj_profile_skip_placeholder_artwork():
    html = '<meta property="og:image" content="https://1001tl.com/images/static/placeholder.jpg">'
    result = _parse_dj_profile(html)
    assert result["artwork_url"] == ""


# --- Load logging tests ---


def test_dj_cache_load_logs_not_found(tmp_path, caplog):
    """New DJ cache logs 'not found' at DEBUG."""
    import logging
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.tracklists.dj_cache"):
        DjCache(tmp_path / "dj_cache.json")
    assert any("not found" in msg for msg in caplog.messages)


def test_dj_cache_load_logs_entry_count(tmp_path, caplog):
    """Existing DJ cache logs path and entry count at DEBUG."""
    import logging
    path = tmp_path / "dj_cache.json"
    c = DjCache(path)
    c.put("tiesto", {"name": "Tiesto", "artwork_url": "", "aliases": [], "member_of": []})
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.tracklists.dj_cache"):
        DjCache(path)
    assert any("Loaded DJ cache from" in msg and "1 entr" in msg for msg in caplog.messages)
