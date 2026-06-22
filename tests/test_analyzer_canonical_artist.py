"""Analyzer derives the untruncated canonical artist from slugs.

Two long-standing truncation bugs corrupted the primary artist:
  - normalise_name() strips trailing dots ("Fred again.." -> "Fred again")
  - resolve_artist() used to &-split known acts ("Above & Beyond" -> "Above")

The authoritative, untruncated name is available straight from the slug via
DjCache.canonical_name(slug). When the 1001TL slug list is present, the
analyzer must derive both the primary artist and the artists list from those
canonical names instead of from the truncation-prone display tag.
"""

import json
from pathlib import Path
from unittest.mock import patch

from festival_organizer.analyzer import analyse_file
from festival_organizer.config import Config
from festival_organizer.tracklists.dj_cache import DjCache
from tests.conftest import TEST_CONFIG


def _config_with_dj_cache(tmp_path: Path, entries: dict[str, str]) -> Config:
    """Build a Config whose dj_cache resolves the given slug -> name entries.

    Writes a real dj_cache.json to tmp_path, points a real DjCache at it, and
    pins it onto the Config's cached_property slot so the analyzer reads it.
    """
    cache_path = tmp_path / "dj_cache.json"
    cache_path.write_text(
        json.dumps({slug: {"name": name} for slug, name in entries.items()}),
        encoding="utf-8",
    )
    cfg = Config(dict(TEST_CONFIG))
    cfg.__dict__["dj_cache"] = DjCache(cache_path=cache_path)
    return cfg


def test_primary_artist_from_slug_not_amp_truncated(tmp_path):
    """A known '&' act resolves to its full name via the slug, not 'Above'."""
    cfg = _config_with_dj_cache(tmp_path, {"aboveandbeyond": "Above & Beyond"})
    fake_meta = {
        "tracklists_artists": "Above & Beyond",
        "tracklists_artist_slugs": "aboveandbeyond",
        "tracklists_festival": "Tomorrowland",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("/library/2025 - Tomorrowland - Above & Beyond.mkv"),
            Path("/library"),
            cfg,
        )
    assert mf.artist == "Above & Beyond"  # NOT "Above"
    assert mf.artist_slugs == ["aboveandbeyond"]


def test_primary_and_artists_from_slug_preserve_dots(tmp_path):
    """B2B slugs derive both primary and the artists list with dots preserved."""
    cfg = _config_with_dj_cache(
        tmp_path,
        {"fredagain..": "Fred again..", "thomasbangalter": "Thomas Bangalter"},
    )
    fake_meta = {
        "tracklists_artists": "Fred again..|Thomas Bangalter",
        "tracklists_artist_slugs": "fredagain..|thomasbangalter",
        "tracklists_festival": "Coachella",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("/library/2025 - Coachella - Fred again.. & Thomas Bangalter.mkv"),
            Path("/library"),
            cfg,
        )
    assert mf.artist == "Fred again.."  # dots preserved, not "Fred again"
    assert mf.artists == ["Fred again..", "Thomas Bangalter"]
    assert mf.artist_slugs == ["fredagain..", "thomasbangalter"]
