from festival_organizer import paths


class _DjCache:
    def slug_for_name(self, name):
        return {"above & beyond": "aboveandbeyond"}.get(name.lower())


def test_folder_key_prefers_explicit_slug():
    assert paths.artist_cache_folder_key("whatever", slug="fredagain..") == "fredagain"


def test_folder_key_resolves_name_via_cache():
    assert (
        paths.artist_cache_folder_key("Above & Beyond", dj_cache=_DjCache())
        == "aboveandbeyond"
    )


def test_folder_key_falls_back_to_slugify():
    assert paths.artist_cache_folder_key("Some Local DJ") == "somelocaldj"


def test_artist_cache_dir_uses_folder_key():
    d = paths.artist_cache_dir("aboveandbeyond")
    assert d.name == "aboveandbeyond"
    assert d.parent.name == "artists"
