"""Tests that guard config.example.toml against structural drift.

The example is the canonical starting point users are told to copy into
their config.toml. If it parses into a structure that does not match the
loader's expectations, users silently lose settings.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from festival_organizer.config import DEFAULT_CONFIG

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "config.example.toml"


@pytest.fixture(scope="module")
def parsed_example() -> dict:
    """Return the example config as parsed by tomllib.

    Strips commented-out sections (which appear as comments, not TOML data)
    so the structural comparison reflects what a user would get by copying
    the file unmodified.
    """
    with open(EXAMPLE_PATH, "rb") as f:
        return tomllib.load(f)


def test_skip_patterns_is_top_level(parsed_example):
    """skip_patterns must be at the top level, not nested under another section.

    Placing `skip_patterns = [...]` after a `[section]` header makes TOML
    absorb it into that section. The loader reads `_data["skip_patterns"]`
    at top level, so a nested placement is silently ignored.
    """
    assert "skip_patterns" in parsed_example, (
        "skip_patterns must be a top-level key in config.example.toml; "
        "if it is placed after a [section] header, TOML absorbs it into "
        "that section and the loader ignores it"
    )
    assert isinstance(parsed_example["skip_patterns"], list)
    # Nothing should have absorbed it
    content_rules = parsed_example.get("content_type_rules", {})
    assert "skip_patterns" not in content_rules, (
        "skip_patterns leaked into [content_type_rules]; move it above "
        "the first [section] header in config.example.toml"
    )


def test_tracklists_documents_genre_top_n(parsed_example):
    """[tracklists] must show genre_top_n so users discover the cap setting."""
    tl = parsed_example.get("tracklists", {})
    assert "genre_top_n" in tl, (
        "config.example.toml must document genre_top_n under [tracklists]; "
        "it is a real setting in DEFAULT_CONFIG that users would miss"
    )
    assert tl["genre_top_n"] == DEFAULT_CONFIG["tracklists"]["genre_top_n"]


def test_cache_ttl_section_present(parsed_example):
    """[cache_ttl] section must be present and match DEFAULT_CONFIG."""
    assert "cache_ttl" in parsed_example, (
        "config.example.toml must include a [cache_ttl] section; it is "
        "documented in docs/configuration.md and affects behaviour"
    )
    example_ttl = parsed_example["cache_ttl"]
    default_ttl = DEFAULT_CONFIG["cache_ttl"]
    for key in ("mbid_days", "dj_days", "source_days", "images_days"):
        assert key in example_ttl, f"[cache_ttl] missing key {key!r}"
        assert example_ttl[key] == default_ttl[key], (
            f"[cache_ttl].{key} drift: example={example_ttl[key]}, "
            f"DEFAULT_CONFIG={default_ttl[key]}"
        )


def test_all_example_top_level_keys_exist_in_default_config(parsed_example):
    """Every top-level key in the example must correspond to a real config key.

    Catches typos and deprecated keys that would silently be ignored.
    """
    example_keys = set(parsed_example.keys())
    default_keys = set(DEFAULT_CONFIG.keys())
    unknown = example_keys - default_keys
    assert not unknown, (
        f"config.example.toml has top-level keys unknown to DEFAULT_CONFIG: "
        f"{sorted(unknown)}. Either add them to DEFAULT_CONFIG or remove "
        f"them from the example."
    )
