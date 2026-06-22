from festival_organizer.tracklists.api import _parse_dj_profile
from festival_organizer.tracklists.dj_cache import DjCache

GROUP_HTML = """
<div class="h">Group Members</div>
<div><a href="/dj/jonogrant/index.html">Jono Grant</a></div>
<div><a href="/dj/tonymcguinness/index.html">Tony McGuinness</a></div>
<div class="h">Likes</div>
"""


def test_parse_captures_group_members():
    prof = _parse_dj_profile(GROUP_HTML)
    assert prof["members"] == [
        {"slug": "jonogrant", "name": "Jono Grant"},
        {"slug": "tonymcguinness", "name": "Tony McGuinness"},
    ]


def test_derive_group_members_uses_stored_members(tmp_path):
    c = DjCache(cache_path=tmp_path / "dj_cache.json")
    c._data = {
        "aboveandbeyond": {
            "name": "Above & Beyond",
            "members": [
                {"slug": "jonogrant", "name": "Jono Grant"},
                {"slug": "tonymcguinness", "name": "Tony McGuinness"},
            ],
            "ts": 9e9,
            "ttl": 9e9,
        },
    }
    gm = c.derive_group_members()
    assert gm["aboveandbeyond"] == ["Jono Grant", "Tony McGuinness"]


def test_derive_group_members_falls_back_to_member_of(tmp_path):
    c = DjCache(cache_path=tmp_path / "dj_cache.json")
    c._data = {
        "armin": {
            "name": "Armin van Buuren",
            "member_of": [{"slug": "gaia", "name": "Gaia"}],
            "ts": 9e9,
            "ttl": 9e9,
        },
        "gaia": {"name": "Gaia", "ts": 9e9, "ttl": 9e9},
    }
    gm = c.derive_group_members()
    assert gm["gaia"] == ["Armin van Buuren"]
