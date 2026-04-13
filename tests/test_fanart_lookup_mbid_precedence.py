"""lookup_mbid precedence: override > cache > network. Override never writes cache."""
import json
from unittest.mock import patch

from festival_organizer.fanart import (
    ArtistMbidOverrides,
    MBIDCache,
    lookup_mbid,
)


def test_override_wins_over_cache(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(
        json.dumps({"Afrojack": "OVERRIDE-MBID"})
    )
    cache = MBIDCache(cache_dir=tmp_path)
    cache.put("Afrojack", "CACHED-MBID")
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)

    assert lookup_mbid("Afrojack", cache, overrides=overrides) == "OVERRIDE-MBID"


def test_override_bypasses_network(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(
        json.dumps({"Afrojack": "OVERRIDE-MBID"})
    )
    cache = MBIDCache(cache_dir=tmp_path)
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)

    with patch("festival_organizer.fanart._mb_search") as mb:
        result = lookup_mbid("Afrojack", cache, overrides=overrides)

    assert result == "OVERRIDE-MBID"
    mb.assert_not_called()


def test_override_does_not_write_cache(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(
        json.dumps({"Afrojack": "OVERRIDE-MBID"})
    )
    cache = MBIDCache(cache_dir=tmp_path)
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)

    lookup_mbid("Afrojack", cache, overrides=overrides)

    # Override must NOT leak into the disposable cache.
    assert not cache.has("Afrojack")


def test_override_case_insensitive(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(
        json.dumps({"Afrojack": "OVERRIDE-MBID"})
    )
    cache = MBIDCache(cache_dir=tmp_path)
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)

    assert lookup_mbid("AFROJACK", cache, overrides=overrides) == "OVERRIDE-MBID"


def test_no_overrides_falls_through_to_cache(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)
    cache.put("Afrojack", "CACHED-MBID")

    # overrides=None is the explicit "no overrides file" path.
    assert lookup_mbid("Afrojack", cache, overrides=None) == "CACHED-MBID"


def test_no_overrides_hits_network_on_cache_miss(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path)

    with patch("festival_organizer.fanart._mb_search", return_value="NET-MBID") as mb:
        result = lookup_mbid("Afrojack", cache, overrides=None)

    assert result == "NET-MBID"
    mb.assert_called_once_with("Afrojack")
    # Network result SHOULD be cached (that's the existing contract).
    assert cache.get("Afrojack") == "NET-MBID"


def test_missing_override_key_falls_through_to_cache(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(
        json.dumps({"SomeoneElse": "ELSE-MBID"})
    )
    cache = MBIDCache(cache_dir=tmp_path)
    cache.put("Afrojack", "CACHED-MBID")
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)

    assert lookup_mbid("Afrojack", cache, overrides=overrides) == "CACHED-MBID"


def test_backward_compatible_two_arg_call(tmp_path):
    # Existing callers in operations.py pass only (name, cache). The overrides
    # kwarg must default to None so those calls still work.
    cache = MBIDCache(cache_dir=tmp_path)
    cache.put("Afrojack", "CACHED-MBID")
    assert lookup_mbid("Afrojack", cache) == "CACHED-MBID"
