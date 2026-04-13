"""_mb_search: post-filter candidates by type.

Tests the filter that drops non-artist entities (labels, orchestras, etc.) while
keeping typeless entries (common for mid-profile DJs whose MB entry has never
been type-tagged). Previous behavior AND'd type:person OR type:group into the
query, silently excluding real artists like Hannah Laing (type:null on MB).
"""
from unittest.mock import patch

from festival_organizer.fanart import _mb_search


def _mb_response(artists):
    """Build a minimal MB /artist/ search response wrapper."""
    return {"created": "...", "count": len(artists), "offset": 0, "artists": artists}


def _fake_get(status_code=200, json_data=None):
    class _Resp:
        def __init__(self, sc, jd):
            self.status_code = sc
            self._jd = jd
        def raise_for_status(self): pass
        def json(self): return self._jd
    return _Resp(status_code, json_data)


def test_mb_search_accepts_typeless_artist_entry():
    """MB entries with type=null (e.g. Hannah Laing) must not be filtered out."""
    response = _mb_response([
        {"id": "f96e106f-3c36-4fda-9d14-82ea0753489d",
         "name": "Hannah Laing", "score": 100},  # no type key at all
    ])
    with patch("festival_organizer.fanart.requests.get",
               return_value=_fake_get(200, response)):
        mbid = _mb_search("Hannah Laing")
    assert mbid == "f96e106f-3c36-4fda-9d14-82ea0753489d"


def test_mb_search_accepts_explicit_type_none():
    """An explicit "type": None field (vs. missing key) is also accepted."""
    response = _mb_response([
        {"id": "f96e106f-3c36-4fda-9d14-82ea0753489d",
         "name": "Hannah Laing", "type": None, "score": 100},
    ])
    with patch("festival_organizer.fanart.requests.get",
               return_value=_fake_get(200, response)):
        assert _mb_search("Hannah Laing") == "f96e106f-3c36-4fda-9d14-82ea0753489d"


def test_mb_search_accepts_person_type():
    response = _mb_response([
        {"id": "886dc0c9-3351-4d2d-b762-060cf1e66929",
         "name": "FISHER", "type": "Person", "score": 100},
    ])
    with patch("festival_organizer.fanart.requests.get",
               return_value=_fake_get(200, response)):
        assert _mb_search("FISHER") == "886dc0c9-3351-4d2d-b762-060cf1e66929"


def test_mb_search_accepts_group_type():
    response = _mb_response([
        {"id": "9c9f1380-2516-4fc9-a3e6-f9f61941d12d",
         "name": "Swedish House Mafia", "type": "Group", "score": 100},
    ])
    with patch("festival_organizer.fanart.requests.get",
               return_value=_fake_get(200, response)):
        assert _mb_search("Swedish House Mafia") == "9c9f1380-2516-4fc9-a3e6-f9f61941d12d"


def test_mb_search_rejects_orchestra():
    """Orchestras are not artists in the DJ-set context; reject them."""
    response = _mb_response([
        {"id": "some-orchestra-mbid", "name": "Berlin Philharmonic",
         "type": "Orchestra", "score": 100},
    ])
    with patch("festival_organizer.fanart.requests.get",
               return_value=_fake_get(200, response)):
        assert _mb_search("Berlin Philharmonic") is None


def test_mb_search_rejects_character():
    response = _mb_response([
        {"id": "fictional", "name": "Sherlock Holmes",
         "type": "Character", "score": 100},
    ])
    with patch("festival_organizer.fanart.requests.get",
               return_value=_fake_get(200, response)):
        assert _mb_search("Sherlock Holmes") is None


def test_mb_search_falls_through_to_typeless_when_explicit_non_artist_first():
    """If the top candidate is a non-artist type but a typeless artist with
    equal score follows, the typeless artist wins."""
    response = _mb_response([
        {"id": "orchestra", "name": "Something", "type": "Orchestra", "score": 100},
        {"id": "real", "name": "Something", "score": 100},
    ])
    with patch("festival_organizer.fanart.requests.get",
               return_value=_fake_get(200, response)):
        assert _mb_search("Something") == "real"
