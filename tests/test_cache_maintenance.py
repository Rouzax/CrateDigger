import io

from festival_organizer import cache_maintenance
from festival_organizer.cache_maintenance import (
    cache_deezer_artwork,
    cache_dj_artwork,
    fetch_deezer_artwork,
    preferred_artist_image,
    reconcile_artist_cache,
    refresh_artist_images,
    warm_artist_cache_from_dj_cache,
    write_portrait,
)
from festival_organizer.normalization import folder_slug
from festival_organizer.tracklists.dj_cache import DjCache


def test_reconcile_removes_non_slug_dirs(tmp_path):
    root = tmp_path / "artists"
    for name in ["aboveandbeyond", "tiesto", "Above", "Ti�sto", "K_lsch", "fredagain"]:
        (root / name).mkdir(parents=True)
    valid = {"aboveandbeyond", "tiesto", "fredagain"}

    removed = reconcile_artist_cache(root, valid)

    remaining = {p.name for p in root.iterdir()}
    assert remaining == {"aboveandbeyond", "tiesto", "fredagain"}
    assert {p.name for p in removed} == {"Above", "Ti�sto", "K_lsch"}


def test_reconcile_idempotent_on_clean_cache(tmp_path):
    root = tmp_path / "artists"
    (root / "tiesto").mkdir(parents=True)
    assert reconcile_artist_cache(root, {"tiesto"}) == []


def test_reconcile_missing_root_is_noop(tmp_path):
    assert reconcile_artist_cache(tmp_path / "nope", {"x"}) == []


def test_reconcile_preserves_seen_fallback_dir(tmp_path):
    root = tmp_path / "artists"
    for name in ["aboveandbeyond", "somelocaldj", "Above"]:
        (root / name).mkdir(parents=True)
    # valid = dj_cache folder slugs + this-run fallback key for the non-1001TL artist
    valid = {"aboveandbeyond", "somelocaldj"}
    removed = reconcile_artist_cache(root, valid)
    remaining = {p.name for p in root.iterdir()}
    assert remaining == {"aboveandbeyond", "somelocaldj"}
    assert {p.name for p in removed} == {"Above"}


# -- cache_dj_artwork --


def _fake_image_response(width, height):
    """A requests-like stub whose .content is a PNG of the given size."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buf, "PNG")
    data = buf.getvalue()

    class _Resp:
        content = data

        def raise_for_status(self):
            return None

    return _Resp()


def test_cache_dj_artwork_downloads_crops_and_resizes(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr("requests.get", lambda *a, **k: _fake_image_response(1000, 800))
    dest = tmp_path / "artists" / "tiesto" / "dj-artwork.jpg"
    result = cache_dj_artwork("https://x/a.jpg", dest, ttl_days=90)
    assert result == dest
    assert dest.exists()
    with Image.open(dest) as img:
        assert img.size == (550, 550)  # center-cropped to square then resized


def test_cache_dj_artwork_fresh_cache_skips_download(tmp_path, monkeypatch):
    dest = tmp_path / "artists" / "tiesto" / "dj-artwork.jpg"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"existing")

    def _boom(*a, **k):
        raise AssertionError("network should not be hit for a fresh cache entry")

    monkeypatch.setattr("requests.get", _boom)
    result = cache_dj_artwork("https://x/a.jpg", dest, ttl_days=90)
    assert result == dest
    assert dest.read_bytes() == b"existing"


def test_cache_dj_artwork_empty_url_returns_none(tmp_path):
    dest = tmp_path / "artists" / "x" / "dj-artwork.jpg"
    assert cache_dj_artwork("", dest, ttl_days=90) is None
    assert not dest.exists()


# -- warm_artist_cache_from_dj_cache --


def _stub_downloader(monkeypatch):
    """Replace cache_dj_artwork with a stub that just writes the dest file."""

    def _fake(url, dest, ttl_days, *, artist_label="", log=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"img")
        return dest

    monkeypatch.setattr(cache_maintenance, "cache_dj_artwork", _fake)


def _seed_cache(tmp_path):
    cache = DjCache(tmp_path / "dj_cache.json")
    cache.put(
        "kevindevries",
        {
            "name": "Kevin de Vries",
            "artwork_url": "https://x/kdv.jpg",
            "aliases": [],
            "member_of": [],
        },
    )
    cache.put(
        "somethingelse-br",
        {
            "name": "SOMETHING ELSE",
            "artwork_url": "https://x/se.jpg",
            "aliases": [],
            "member_of": [],
        },
    )
    cache.put(
        "nourl", {"name": "No URL", "artwork_url": "", "aliases": [], "member_of": []}
    )
    return cache


def test_warm_creates_dirs_only_for_djs_with_artwork(tmp_path, monkeypatch):
    _stub_downloader(monkeypatch)
    cache = _seed_cache(tmp_path)
    root = tmp_path / "artists"

    created = warm_artist_cache_from_dj_cache(root, cache, ttl_days=90)

    assert {p.name for p in created} == {"kevindevries", "somethingelse-br"}
    assert (root / "kevindevries" / "dj-artwork.jpg").exists()
    assert (root / "somethingelse-br" / "dj-artwork.jpg").exists()
    assert not (root / "nourl").exists()


def test_warm_is_idempotent(tmp_path, monkeypatch):
    _stub_downloader(monkeypatch)
    cache = _seed_cache(tmp_path)
    root = tmp_path / "artists"

    first = warm_artist_cache_from_dj_cache(root, cache, ttl_days=90)
    second = warm_artist_cache_from_dj_cache(root, cache, ttl_days=90)

    assert len(first) == 2
    assert second == []  # dirs already populated, nothing newly created


def test_warm_keying_parity_with_reconcile(tmp_path, monkeypatch):
    """A warmed dir must survive reconcile built from the same dj_cache slugs."""
    _stub_downloader(monkeypatch)
    cache = _seed_cache(tmp_path)
    root = tmp_path / "artists"

    warm_artist_cache_from_dj_cache(root, cache, ttl_days=90)
    valid = {folder_slug(s) for s in cache.slugs()}
    removed = reconcile_artist_cache(root, valid)

    assert removed == []
    assert (root / "somethingelse-br" / "dj-artwork.jpg").exists()


def test_cache_deezer_artwork_squares_and_caps_at_550(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(
        "requests.get", lambda *a, **k: _fake_image_response(1000, 1000)
    )
    dest = tmp_path / "artists" / "argy" / "deezer-artist.jpg"
    assert cache_deezer_artwork("https://x/a.jpg", dest, ttl_days=90) == dest
    with Image.open(dest) as img:
        assert img.size == (550, 550)


def _touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_preferred_artist_image_follows_chain(tmp_path):
    deezer = _touch(tmp_path / "deezer-artist.jpg")
    dj = _touch(tmp_path / "dj-artwork.jpg")
    assert (
        preferred_artist_image(tmp_path, ["deezer", "dj_artwork", "gradient"]) == deezer
    )
    assert preferred_artist_image(tmp_path, ["dj_artwork", "deezer"]) == dj


def test_preferred_artist_image_none_when_empty(tmp_path):
    assert (
        preferred_artist_image(tmp_path, ["deezer", "dj_artwork", "fanart_tv"]) is None
    )


def test_fetch_deezer_artwork_resolves_and_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "requests.get", lambda *a, **k: _fake_image_response(1000, 1000)
    )
    dest = tmp_path / "argy" / "deezer-artist.jpg"
    seen = {}

    def fake_lookup(name, cache, overrides=None, spotify_url=""):
        seen["spotify_url"] = spotify_url
        return "mbid-argy"

    monkeypatch.setattr(cache_maintenance, "lookup_mbid", fake_lookup)
    monkeypatch.setattr(
        cache_maintenance,
        "resolve_deezer_photo",
        lambda name, mbid, cache, overrides: "https://x/argy.jpg" if mbid else "",
    )
    result = fetch_deezer_artwork(
        "Argy",
        dest,
        spotify_url="https://open.spotify.com/artist/x",
        mbid_cache=None,
        mbid_overrides=None,
        deezer_cache=None,
        deezer_overrides=None,
        ttl_days=90,
    )
    assert result == dest
    assert seen["spotify_url"] == "https://open.spotify.com/artist/x"


def test_fetch_deezer_artwork_fresh_image_makes_no_requests(tmp_path, monkeypatch):
    dest = _touch(tmp_path / "argy" / "deezer-artist.jpg")

    def boom(*a, **k):
        raise AssertionError("no lookup expected")

    monkeypatch.setattr(cache_maintenance, "lookup_mbid", boom)
    result = fetch_deezer_artwork(
        "Argy",
        dest,
        spotify_url="",
        mbid_cache=None,
        mbid_overrides=None,
        deezer_cache=None,
        deezer_overrides=None,
        ttl_days=90,
    )
    assert result == dest


def test_fetch_deezer_artwork_without_photo_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_maintenance, "lookup_mbid", lambda *a, **k: "mbid")
    monkeypatch.setattr(cache_maintenance, "resolve_deezer_photo", lambda *a, **k: "")
    result = fetch_deezer_artwork(
        "Bart Skils",
        tmp_path / "bart-skils" / "deezer-artist.jpg",
        spotify_url="",
        mbid_cache=None,
        mbid_overrides=None,
        deezer_cache=None,
        deezer_overrides=None,
        ttl_days=90,
    )
    assert result is None


def test_write_portrait_copies_chain_winner(tmp_path):
    _touch(tmp_path / "dj-artwork.jpg", b"dj")
    _touch(tmp_path / "deezer-artist.jpg", b"deezer")
    portrait = write_portrait(tmp_path, ["deezer", "dj_artwork", "gradient"])
    assert portrait == tmp_path / "portrait.jpg"
    assert (tmp_path / "portrait.jpg").read_bytes() == b"deezer"


def test_write_portrait_leaves_identical_file_untouched(tmp_path):
    import os

    _touch(tmp_path / "dj-artwork.jpg", b"dj")
    portrait = _touch(tmp_path / "portrait.jpg", b"dj")
    os.utime(portrait, (1_000_000, 1_000_000))
    write_portrait(tmp_path, ["deezer", "dj_artwork"])
    assert portrait.stat().st_mtime == 1_000_000


def test_write_portrait_removes_stale_when_no_source(tmp_path):
    _touch(tmp_path / "portrait.jpg", b"old")
    assert write_portrait(tmp_path, ["deezer", "dj_artwork", "fanart_tv"]) is None
    assert not (tmp_path / "portrait.jpg").exists()


def test_write_portrait_follows_custom_chain(tmp_path):
    # A chain without "deezer" never puts the Deezer photo on TrackSplit's cover.
    _touch(tmp_path / "deezer-artist.jpg", b"deezer")
    _touch(tmp_path / "dj-artwork.jpg", b"dj")
    portrait = write_portrait(tmp_path, ["dj_artwork", "fanart_tv", "gradient"])
    assert portrait is not None
    assert portrait.read_bytes() == b"dj"


def _deezer_config(tmp_path, enabled=True):
    from festival_organizer.config import DEFAULT_CONFIG, Config

    return Config({**DEFAULT_CONFIG, "deezer": {"enabled": enabled}})


def test_refresh_artist_images_resolves_each_cached_dj(tmp_path, monkeypatch):
    dj_cache = DjCache(tmp_path / "dj_cache.json")
    dj_cache.put("argy", {"name": "Argy", "spotify_url": "https://sp/argy"})
    dj_cache.put("anyma", {"name": "Anyma", "spotify_url": ""})
    calls = {}

    def fake_fetch(name, dest, **kwargs):
        calls[name] = (dest, kwargs["spotify_url"])
        return _touch(dest, name.encode())

    monkeypatch.setattr(cache_maintenance, "fetch_deezer_artwork", fake_fetch)
    root = tmp_path / "artists"
    refresh_artist_images(root, dj_cache, _deezer_config(tmp_path))

    assert calls == {
        "Argy": (root / "argy" / "deezer-artist.jpg", "https://sp/argy"),
        "Anyma": (root / "anyma" / "deezer-artist.jpg", ""),
    }
    assert (root / "argy" / "portrait.jpg").read_bytes() == b"Argy"


def test_refresh_artist_images_skips_deezer_when_disabled(tmp_path, monkeypatch):
    dj_cache = DjCache(tmp_path / "dj_cache.json")
    dj_cache.put("argy", {"name": "Argy"})
    root = tmp_path / "artists"
    _touch(root / "argy" / "dj-artwork.jpg", b"dj")

    def boom(*a, **k):
        raise AssertionError("Deezer must not be asked")

    monkeypatch.setattr(cache_maintenance, "fetch_deezer_artwork", boom)
    refresh_artist_images(root, dj_cache, _deezer_config(tmp_path, enabled=False))
    assert (root / "argy" / "portrait.jpg").read_bytes() == b"dj"


def test_refresh_artist_images_writes_portrait_for_every_artist_dir(
    tmp_path, monkeypatch
):
    # Artists outside the DJ cache (a non-1001TL set) get a portrait too.
    monkeypatch.setattr(cache_maintenance, "fetch_deezer_artwork", lambda *a, **k: None)
    root = tmp_path / "artists"
    _touch(root / "some-band" / "fanart.jpg", b"fanart")
    refresh_artist_images(
        root, DjCache(tmp_path / "dj_cache.json"), _deezer_config(tmp_path)
    )
    assert (root / "some-band" / "portrait.jpg").read_bytes() == b"fanart"


def test_refresh_artist_images_skips_deezer_when_not_in_chain(tmp_path, monkeypatch):
    from festival_organizer.config import DEFAULT_CONFIG, Config

    dj_cache = DjCache(tmp_path / "dj_cache.json")
    dj_cache.put("argy", {"name": "Argy"})

    def boom(*a, **k):
        raise AssertionError("Deezer must not be asked")

    monkeypatch.setattr(cache_maintenance, "fetch_deezer_artwork", boom)
    config = Config(
        {
            **DEFAULT_CONFIG,
            "poster_settings": {
                **DEFAULT_CONFIG["poster_settings"],
                "artist_background_priority": ["dj_artwork", "gradient"],
            },
        }
    )
    refresh_artist_images(tmp_path / "artists", dj_cache, config)


# --- Final review fixes: the cached Deezer photo's lifecycle ---


class _Pins:
    def __init__(self, pins: dict):
        self._pins = {k.lower(): v for k, v in pins.items()}

    def has(self, name):
        return name.lower() in self._pins

    def get(self, name):
        return self._pins.get(name.lower())


def _fetch(dest, *, overrides=None):
    return fetch_deezer_artwork(
        "Argy",
        dest,
        spotify_url="",
        mbid_cache=None,
        mbid_overrides=None,
        deezer_cache=None,
        deezer_overrides=overrides,
        ttl_days=90,
    )


def test_null_pin_removes_a_fresh_cached_photo(tmp_path, monkeypatch):
    dest = _touch(tmp_path / "argy" / "deezer-artist.jpg", b"OLD-DEEZER")
    monkeypatch.setattr(cache_maintenance, "lookup_mbid", lambda *a, **k: "mbid")
    assert _fetch(dest, overrides=_Pins({"Argy": None})) is None
    assert not dest.exists()


def test_definite_miss_removes_a_stale_cached_photo(tmp_path, monkeypatch):
    import os

    dest = _touch(tmp_path / "argy" / "deezer-artist.jpg", b"OLD-DEEZER")
    os.utime(dest, (0, 0))
    monkeypatch.setattr(cache_maintenance, "lookup_mbid", lambda *a, **k: "mbid")
    monkeypatch.setattr(cache_maintenance, "resolve_deezer_photo", lambda *a, **k: "")
    assert _fetch(dest) is None
    assert not dest.exists()


def test_unavailable_keeps_the_cached_photo_and_raises(tmp_path, monkeypatch):
    import os

    import pytest

    from festival_organizer.deezer import DeezerUnavailable

    dest = _touch(tmp_path / "argy" / "deezer-artist.jpg", b"OLD-DEEZER")
    os.utime(dest, (0, 0))
    monkeypatch.setattr(cache_maintenance, "lookup_mbid", lambda *a, **k: "mbid")
    monkeypatch.setattr(cache_maintenance, "resolve_deezer_photo", lambda *a, **k: None)
    with pytest.raises(DeezerUnavailable):
        _fetch(dest)
    assert dest.read_bytes() == b"OLD-DEEZER"


def test_no_mbid_keeps_the_cached_photo(tmp_path, monkeypatch):
    # lookup_mbid also returns None while MusicBrainz is down; that must not
    # delete a photo found on an earlier run.
    import os

    dest = _touch(tmp_path / "argy" / "deezer-artist.jpg", b"OLD-DEEZER")
    os.utime(dest, (0, 0))
    monkeypatch.setattr(cache_maintenance, "lookup_mbid", lambda *a, **k: None)
    assert _fetch(dest) == dest
    assert dest.exists()


def test_disabled_deezer_drops_its_photo_from_the_portrait(tmp_path, monkeypatch):
    root = tmp_path / "artists"
    _touch(root / "argy" / "deezer-artist.jpg", b"deezer")
    _touch(root / "argy" / "dj-artwork.jpg", b"dj")
    refresh_artist_images(
        root,
        DjCache(tmp_path / "dj_cache.json"),
        _deezer_config(tmp_path, enabled=False),
    )
    assert (root / "argy" / "portrait.jpg").read_bytes() == b"dj"


def test_refresh_stops_asking_deezer_once_it_is_unavailable(
    tmp_path, monkeypatch, caplog
):
    from festival_organizer.deezer import DeezerUnavailable

    dj_cache = DjCache(tmp_path / "dj_cache.json")
    for slug in ("a", "b", "c"):
        dj_cache.put(slug, {"name": slug.upper()})
    asked = []

    def down(name, dest, **kwargs):
        asked.append(name)
        raise DeezerUnavailable(name)

    monkeypatch.setattr(cache_maintenance, "fetch_deezer_artwork", down)
    refresh_artist_images(tmp_path / "artists", dj_cache, _deezer_config(tmp_path))
    assert asked == ["A"]
    assert any("skipped=2" in m for m in caplog.messages)


def test_refresh_survives_an_unexpected_error_per_artist(tmp_path, monkeypatch):
    dj_cache = DjCache(tmp_path / "dj_cache.json")
    dj_cache.put("a", {"name": "A"})
    dj_cache.put("b", {"name": "B"})
    root = tmp_path / "artists"

    def flaky(name, dest, **kwargs):
        if name == "A":
            raise OSError("disk full")
        return _touch(dest, b"b-photo")

    monkeypatch.setattr(cache_maintenance, "fetch_deezer_artwork", flaky)
    refresh_artist_images(root, dj_cache, _deezer_config(tmp_path))
    assert (root / "b" / "portrait.jpg").read_bytes() == b"b-photo"


def test_refresh_survives_a_portrait_that_cannot_be_written(tmp_path, monkeypatch):
    root = tmp_path / "artists"
    _touch(root / "a" / "dj-artwork.jpg", b"a")
    _touch(root / "b" / "dj-artwork.jpg", b"b")
    real = cache_maintenance.write_portrait

    def locked(artist_dir, priority):
        if artist_dir.name == "a":
            raise PermissionError("in use")
        return real(artist_dir, priority)

    monkeypatch.setattr(cache_maintenance, "write_portrait", locked)
    refresh_artist_images(
        root, DjCache(tmp_path / "dj_cache.json"), _deezer_config(tmp_path)
    )
    assert (root / "b" / "portrait.jpg").read_bytes() == b"b"
