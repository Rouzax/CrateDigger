"""_mb_search: 1001TL's trailing country tag ("Yuna (US)").

1001TL adds a country code to tell same-named artists apart. It is not part of
the artist's name, so MusicBrainz is searched without it and the code picks
between same-named candidates by their MusicBrainz country.
"""

from unittest.mock import patch

from festival_organizer.fanart import MBID_RESOLVER_VERSION, MBIDCache, _mb_search


def _resp(artists):
    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"artists": artists}

    return _Resp()


def _search(name, artists):
    with patch(
        "festival_organizer.fanart.requests.get", return_value=_resp(artists)
    ) as get:
        mbid = _mb_search(name)
    return mbid, get.call_args.kwargs["params"]["query"]


def test_country_tag_is_left_out_of_the_query():
    _, query = _search("Yuna (US)", [])
    assert query == 'artist:"Yuna" OR alias:"Yuna"'


def test_same_named_candidate_from_the_tagged_country_wins():
    mbid, _ = _search(
        "Yuna (US)",
        [
            {"id": "my-yuna", "name": "Yuna", "score": 100, "country": "MY"},
            {"id": "us-yuna", "name": "Yuna", "score": 100, "country": "US"},
        ],
    )
    assert mbid == "us-yuna"


def test_uk_tag_matches_musicbrainz_gb():
    mbid, _ = _search(
        "FOLEY (UK)",
        [
            {"id": "us-foley", "name": "Foley", "score": 100, "country": "US"},
            {"id": "gb-foley", "name": "FOLEY", "score": 100, "country": "GB"},
        ],
    )
    assert mbid == "gb-foley"


def test_only_candidate_without_a_country_is_accepted():
    mbid, _ = _search("VLTRA (IT)", [{"id": "vltra", "name": "VLTRA", "score": 100}])
    assert mbid == "vltra"


def test_only_candidates_from_other_countries_are_rejected():
    mbid, _ = _search(
        "Sama (US)", [{"id": "jp-sama", "name": "Sama", "score": 100, "country": "JP"}]
    )
    assert mbid is None


def test_several_unplaced_candidates_are_too_ambiguous():
    mbid, _ = _search(
        "Ink (US)",
        [
            {"id": "ink-1", "name": "Ink", "score": 100},
            {"id": "ink-2", "name": "INK", "score": 100},
        ],
    )
    assert mbid is None


def test_parenthetical_that_is_not_a_country_stays_in_the_query():
    _, query = _search("Malaa (Alter Ego)", [])
    assert query == 'artist:"Malaa (Alter Ego)" OR alias:"Malaa (Alter Ego)"'


def test_misses_from_the_previous_resolver_are_retried(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)
    cache.put("Yuna (US)", None)
    cache._data["yuna (us)"]["rv"] = MBID_RESOLVER_VERSION - 1
    assert not cache.has("Yuna (US)")
    assert MBID_RESOLVER_VERSION >= 3


def test_candidates_placed_elsewhere_do_not_make_an_unplaced_one_ambiguous():
    # MusicBrainz search often omits an artist's country: the German AKKI
    # comes back unplaced next to a Japanese Akki.
    mbid, _ = _search(
        "AKKI (DE)",
        [
            {"id": "de-akki", "name": "AKKI", "score": 100},
            {"id": "jp-akki", "name": "Akki", "score": 95, "country": "JP"},
        ],
    )
    assert mbid == "de-akki"


def test_alias_spelling_the_tagged_name_wins():
    mbid, _ = _search(
        "AKKI (DE)",
        [
            {"id": "other", "name": "AKKI", "score": 100},
            {
                "id": "tagged",
                "name": "AKKI",
                "score": 100,
                "aliases": [{"name": "AKKI (DE)"}],
            },
        ],
    )
    assert mbid == "tagged"


def test_artist_musicbrainz_names_with_the_tag_is_found_first():
    # MusicBrainz names some artists with 1001TL's own tag ("Foley (UK)"), and
    # a search for the bare "FOLEY" does not even return them.
    by_query = {
        'artist:"FOLEY (UK)" OR alias:"FOLEY (UK)"': [
            {"id": "foley-uk", "name": "Foley (UK)", "score": 100, "country": "GB"}
        ],
        'artist:"FOLEY" OR alias:"FOLEY"': [
            {"id": "red-foley", "name": "Red Foley", "score": 100, "country": "US"}
        ],
    }
    queries = []

    def fake_get(url, params, headers, timeout):
        queries.append(params["query"])
        return _resp(by_query[params["query"]])

    with patch("festival_organizer.fanart.requests.get", side_effect=fake_get):
        mbid = _mb_search("FOLEY (UK)")
    assert mbid == "foley-uk"
    assert queries == ['artist:"FOLEY (UK)" OR alias:"FOLEY (UK)"']


def test_unplaced_candidate_matching_only_by_alias_is_not_accepted():
    # Without the tag, "VITO" reaches the songwriter Vitø only through an
    # alias; with nothing placing him in the UK that is a different artist.
    mbid, _ = _search(
        "VITO (UK)",
        [
            {
                "id": "vito-kovach",
                "name": "Vitø",
                "score": 97,
                "aliases": [{"name": "Vito"}],
            },
            {"id": "vito-it", "name": "Vito Abbonato", "score": 93, "country": "IT"},
        ],
    )
    assert mbid is None
