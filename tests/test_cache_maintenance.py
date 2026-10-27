import io

from festival_organizer import cache_maintenance
from festival_organizer.cache_maintenance import (
    cache_deezer_artwork,
    cache_dj_artwork,
    fetch_deezer_artwork,
    preferred_artist_image,
    reconcile_artist_cache,
    warm_artist_cache_from_dj_cache,
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
