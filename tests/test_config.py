import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from festival_organizer.config import Config, DEFAULT_CONFIG, load_config
from festival_organizer.models import MediaFile
from tests.conftest import TEST_CONFIG


def test_default_config_has_required_keys():
    cfg = Config(DEFAULT_CONFIG)
    assert cfg.default_layout == "artist_flat"
    assert "artist_flat" in cfg.layouts
    assert "place_flat" in cfg.layouts
    assert "artist_nested" in cfg.layouts
    assert "place_nested" in cfg.layouts
    assert "festival_set" in cfg.filename_templates
    assert "concert_film" in cfg.filename_templates


def test_config_place_aliases():
    cfg = Config(TEST_CONFIG)
    assert cfg.resolve_place_alias("Amsterdam Music Festival") == "AMF"
    assert cfg.resolve_place_alias("amf") == "AMF"
    # "EDC Las Vegas" is a per-edition alias that resolves to canonical "EDC"
    assert cfg.resolve_place_alias("EDC Las Vegas") == "EDC"
    assert cfg.resolve_place_alias("Unknown Thing") == "Unknown Thing"


def test_config_place_edition():
    cfg = Config(TEST_CONFIG)
    # Tomorrowland has editions configured
    assert cfg.get_place_display("Tomorrowland", "Winter") == "Tomorrowland Winter"
    assert cfg.get_place_display("Tomorrowland", "") == "Tomorrowland"
    # AMF has no editions
    assert cfg.get_place_display("AMF", "Netherlands") == "AMF"


def test_get_place_display_rejects_unknown_edition():
    cfg = Config(TEST_CONFIG)
    # Dreamstate has editions: [SoCal, Europe, Australia, Mexico]
    # "United States" is not in that list, should be omitted
    assert cfg.get_place_display("Dreamstate", "United States") == "Dreamstate"
    assert cfg.get_place_display("Dreamstate", "SoCal") == "Dreamstate SoCal"


def test_resolve_place_with_edition():
    cfg = Config(TEST_CONFIG)
    # Edition decomposition (no alias needed)
    assert cfg.resolve_place_with_edition("Tomorrowland Winter") == ("Tomorrowland", "Winter")
    assert cfg.resolve_place_with_edition("Tomorrowland Brasil") == ("Tomorrowland", "Brasil")
    assert cfg.resolve_place_with_edition("EDC Las Vegas") == ("EDC", "Las Vegas")
    assert cfg.resolve_place_with_edition("Dreamstate SoCal") == ("Dreamstate", "SoCal")
    assert cfg.resolve_place_with_edition("Dreamstate Europe") == ("Dreamstate", "Europe")
    # Alias prefix + edition (Ultra is alias for UMF)
    assert cfg.resolve_place_with_edition("Ultra Europe") == ("UMF", "Europe")
    assert cfg.resolve_place_with_edition("Ultra Music Festival Miami") == ("UMF", "Miami")
    # Pure alias (no edition)
    assert cfg.resolve_place_with_edition("TML") == ("Tomorrowland", "")
    assert cfg.resolve_place_with_edition("AMF") == ("AMF", "")
    # Weekend aliases resolve to plain Tomorrowland (no edition)
    assert cfg.resolve_place_with_edition("Tomorrowland Weekend 1") == ("Tomorrowland", "")
    # Genuine alternate name (not an edition)
    assert cfg.resolve_place_with_edition("Red Rocks Amphitheatre") == ("Red Rocks", "")
    # Unknown place
    assert cfg.resolve_place_with_edition("Unknown Fest") == ("Unknown Fest", "")


def test_resolve_place_with_edition_case_insensitive():
    cfg = Config(TEST_CONFIG)
    assert cfg.resolve_place_with_edition("tomorrowland winter") == ("Tomorrowland", "Winter")
    assert cfg.resolve_place_with_edition("EDC LAS VEGAS") == ("EDC", "Las Vegas")


def test_known_places_includes_edition_combos():
    cfg = Config(TEST_CONFIG)
    known = cfg.known_places
    # Canonical names
    assert "Tomorrowland" in known
    assert "EDC" in known
    # Edition combos (generated dynamically)
    assert "Tomorrowland Winter" in known
    assert "Tomorrowland Brasil" in known
    assert "EDC Las Vegas" in known
    # Aliases
    assert "TML" in known
    assert "Ultra" in known


def test_get_place_display_with_editions():
    cfg = Config(TEST_CONFIG)
    assert cfg.get_place_display("Tomorrowland", "Winter") == "Tomorrowland Winter"
    assert cfg.get_place_display("Tomorrowland", "Brasil") == "Tomorrowland Brasil"
    assert cfg.get_place_display("Tomorrowland", "") == "Tomorrowland"
    # AMF has no editions configured
    assert cfg.get_place_display("AMF", "Netherlands") == "AMF"
    # Unknown edition rejected
    assert cfg.get_place_display("Dreamstate", "United States") == "Dreamstate"
    assert cfg.get_place_display("Dreamstate", "SoCal") == "Dreamstate SoCal"


def test_config_layout_templates():
    cfg = Config(DEFAULT_CONFIG)
    # Default layout is now artist_flat
    fs = cfg.get_layout_template("festival_set")
    assert "{artist}" in fs
    cf = cfg.get_layout_template("concert_film")
    assert "{artist}" in cf
    # Nested layouts still include the place token
    fs_nested = cfg.get_layout_template("festival_set", "artist_nested")
    assert "{artist}" in fs_nested
    assert "{place}" in fs_nested


def test_config_skip_patterns():
    cfg = Config(DEFAULT_CONFIG)
    assert cfg.should_skip("Dolby.UHD/BDMV/STREAM/00001.m2ts")
    assert cfg.should_skip("anything/BDMV/something.m2ts")
    assert not cfg.should_skip("AMF/2024/Martin Garrix.mkv")


def test_config_force_concert_patterns():
    cfg = Config(DEFAULT_CONFIG)
    assert cfg.is_forced_concert("Adele/2011 - Live/file.mkv")
    assert cfg.is_forced_concert("Coldplay/2016/file.mkv")
    assert cfg.is_forced_concert("U2/360/file.mkv")
    assert not cfg.is_forced_concert("AMF/2024/file.mkv")


def test_load_config_from_toml_file():
    """load_config(config_path=...) merges a TOML file over built-in defaults."""
    toml_text = (
        'default_layout = "festival_first"\n'
        '\n'
        '[place_aliases]\n'
        'Tomorrowland = ["TML"]\n'
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(toml_text)
        f.flush()
        cfg = load_config(Path(f.name))
    # Custom value overrides default (and triggers legacy rename)
    assert cfg.default_layout == "festival_nested"
    # Custom alias merged
    assert cfg.resolve_place_alias("TML") == "Tomorrowland"
    # Default aliases still present
    assert cfg.resolve_place_alias("AMF") == "AMF"


def test_config_media_extensions():
    cfg = Config(DEFAULT_CONFIG)
    assert ".mkv" in cfg.media_extensions
    assert ".mp4" in cfg.media_extensions
    assert ".mp3" in cfg.media_extensions
    assert ".txt" not in cfg.media_extensions


def test_config_known_places():
    cfg = Config(TEST_CONFIG)
    places = cfg.known_places
    assert "AMF" in places
    assert "Tomorrowland" in places
    assert "EDC" in places


def test_load_config_builtin_defaults(tmp_path):
    """Built-in defaults load when no files exist."""
    # Point paths.config_file() at a non-existent file so nothing from the
    # developer's real ~/CrateDigger/config.toml leaks in.
    with patch("festival_organizer.config.paths") as mock_paths:
        mock_paths.config_file.return_value = tmp_path / "nonexistent.toml"
        config = load_config()
    assert config.default_layout == "artist_flat"
    assert "artist_flat" in config.layouts
    assert "place_flat" in config.layouts
    assert "artist_nested" in config.layouts
    assert "place_nested" in config.layouts


def test_load_config_user_layer(tmp_path):
    """User TOML at paths.config_file() merges over built-in."""
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    user_config = user_dir / "config.toml"
    user_config.write_text(
        '[place_aliases]\n'
        '"My Festival" = ["My Fest"]\n'
        '\n'
        '[tracklists]\n'
        'email = "me@example.com"\n'
        'password = "secret"\n'
    )
    config = load_config(user_config_file=user_config)
    # User alias merged in
    assert config.resolve_place_alias("My Fest") == "My Festival"
    # Built-in aliases still present
    assert config.resolve_place_alias("EDC") == "EDC"
    # Credentials accessible
    assert config.tracklists_credentials == ("me@example.com", "secret")


def test_load_config_library_layer(tmp_path):
    """Library config.toml merges over user config."""
    lib_dir = tmp_path / ".cratedigger"
    lib_dir.mkdir()
    lib_config = lib_dir / "config.toml"
    lib_config.write_text('default_layout = "festival_flat"\n')
    # Point the user layer at a non-existent file.
    with patch("festival_organizer.config.paths") as mock_paths:
        mock_paths.config_file.return_value = tmp_path / "nonexistent.toml"
        config = load_config(library_config_dir=lib_dir)
    assert config.default_layout == "festival_flat"


def test_load_config_merge_order(tmp_path):
    """Library overrides user overrides built-in."""
    user_dir = tmp_path / "user"
    user_dir.mkdir(parents=True)
    user_file = user_dir / "config.toml"
    user_file.write_text('default_layout = "artist_nested"\n')
    lib_dir = tmp_path / "lib" / ".cratedigger"
    lib_dir.mkdir(parents=True)
    (lib_dir / "config.toml").write_text('default_layout = "festival_nested"\n')
    config = load_config(user_config_file=user_file, library_config_dir=lib_dir)
    assert config.default_layout == "festival_nested"


def test_new_flat_layouts(tmp_path):
    """Built-in defaults include flat layout templates."""
    with patch("festival_organizer.config.paths") as mock_paths:
        mock_paths.config_file.return_value = tmp_path / "nonexistent.toml"
        config = load_config()
    # artist_flat
    tpl = config.get_layout_template("festival_set", "artist_flat")
    assert tpl == "{artist}"
    # place_flat (festival_flat is a deprecated alias and resolves identically)
    tpl = config.get_layout_template("festival_set", "place_flat")
    assert tpl == "{place}{ edition}"
    tpl = config.get_layout_template("festival_set", "festival_flat")
    assert tpl == "{place}{ edition}"
    # Concerts in flat layouts fall back to {artist}
    tpl = config.get_layout_template("concert_film", "artist_flat")
    assert tpl == "{artist}"
    tpl = config.get_layout_template("concert_film", "place_flat")
    assert tpl == "{artist}"


def test_renamed_nested_layouts(tmp_path):
    """Old layout names renamed: artist_first -> artist_nested, etc."""
    with patch("festival_organizer.config.paths") as mock_paths:
        mock_paths.config_file.return_value = tmp_path / "nonexistent.toml"
        config = load_config()
    tpl = config.get_layout_template("festival_set", "artist_nested")
    assert tpl == "{artist}/{place}{ edition}/{year}"
    tpl = config.get_layout_template("festival_set", "festival_nested")
    assert tpl == "{place}{ edition}/{year}/{artist}"


def test_place_flat_layout_present():
    cfg = Config({})
    assert cfg.get_layout_template("festival_set", "place_flat") == "{place}{ edition}"


def test_festival_flat_aliases_to_place_flat(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    cfg = Config({})
    assert cfg.get_layout_template("festival_set", "festival_flat") == cfg.get_layout_template("festival_set", "place_flat")
    assert any("festival_flat" in r.getMessage() and "deprecat" in r.getMessage().lower()
               for r in caplog.records)


def test_place_nested_layout_present():
    cfg = Config({})
    assert cfg.get_layout_template("festival_set", "place_nested") == "{place}{ edition}/{year}/{artist}"


def test_festival_nested_aliases_to_place_nested(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    cfg = Config({})
    assert cfg.get_layout_template("festival_set", "festival_nested") == cfg.get_layout_template("festival_set", "place_nested")
    assert any("festival_nested" in r.getMessage() for r in caplog.records)


def test_tracklists_credentials_from_config():
    """Credentials loaded from tracklists section."""
    config = Config({
        "tracklists": {"email": "a@b.com", "password": "pw123"}
    })
    assert config.tracklists_credentials == ("a@b.com", "pw123")


def test_tracklists_credentials_env_override(monkeypatch):
    """Environment variables override config credentials."""
    monkeypatch.setenv("TRACKLISTS_EMAIL", "env@b.com")
    monkeypatch.setenv("TRACKLISTS_PASSWORD", "envpw")
    config = Config({
        "tracklists": {"email": "config@b.com", "password": "configpw"}
    })
    assert config.tracklists_credentials == ("env@b.com", "envpw")


def test_load_config_malformed_toml(tmp_path, caplog):
    """Malformed user TOML logs warning and falls back to defaults."""
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    user_file = user_dir / "config.toml"
    user_file.write_text("this is not [valid toml")
    with caplog.at_level("WARNING", logger="festival_organizer.config"):
        config = load_config(user_config_file=user_file)
    assert config.default_layout == "artist_flat"  # fell back to default
    assert any("config.toml" in r.getMessage() for r in caplog.records)


def test_load_config_malformed_library_toml(tmp_path, caplog):
    """Malformed library TOML logs warning, user config still applies."""
    user_dir = tmp_path / "user"
    user_dir.mkdir(parents=True)
    user_file = user_dir / "config.toml"
    user_file.write_text('default_layout = "festival_flat"\n')
    lib_dir = tmp_path / "lib" / ".cratedigger"
    lib_dir.mkdir(parents=True)
    (lib_dir / "config.toml").write_text("not = valid = toml = syntax")
    with caplog.at_level("WARNING", logger="festival_organizer.config"):
        config = load_config(user_config_file=user_file, library_config_dir=lib_dir)
    assert config.default_layout == "festival_flat"  # user layer applied
    assert any("config.toml" in r.getMessage() for r in caplog.records)


# --- Load logging tests ---


def test_load_config_journals_user_layer_loaded(tmp_path, caplog):
    """log_load_summary replays 'loaded' for a present user config.toml."""
    user_file = tmp_path / "config.toml"
    user_file.write_text('default_layout = "artist_flat"\n')
    cfg = load_config(user_config_file=user_file)
    with caplog.at_level("DEBUG", logger="festival_organizer.config"):
        cfg.log_load_summary()
    assert any("config.toml" in msg and "loaded" in msg for msg in caplog.messages)


def test_load_config_journals_user_layer_not_found(tmp_path, caplog):
    """log_load_summary replays 'not found' when user config.toml is absent."""
    missing = tmp_path / "config.toml"
    cfg = load_config(user_config_file=missing)
    with caplog.at_level("DEBUG", logger="festival_organizer.config"):
        cfg.log_load_summary()
    assert any("not found" in msg for msg in caplog.messages)


def test_load_config_journals_library_layer(tmp_path, caplog):
    """log_load_summary includes the library config.toml entry."""
    lib_dir = tmp_path / ".cratedigger"
    lib_dir.mkdir()
    (lib_dir / "config.toml").write_text('default_layout = "festival_flat"\n')
    with patch("festival_organizer.config.paths") as mock_paths:
        mock_paths.config_file.return_value = tmp_path / "nonexistent.toml"
        cfg = load_config(library_config_dir=lib_dir)
    with caplog.at_level("DEBUG", logger="festival_organizer.config"):
        cfg.log_load_summary()
    messages = " ".join(caplog.messages)
    assert "config.toml" in messages and "loaded" in messages


def test_load_config_journal_clears_after_replay(tmp_path, caplog):
    """log_load_summary clears the journal so a second call is a no-op."""
    cfg = load_config(user_config_file=tmp_path / "config.toml")
    with caplog.at_level("DEBUG", logger="festival_organizer.config"):
        cfg.log_load_summary()
    first_count = len(caplog.records)
    assert first_count > 0
    caplog.clear()
    cfg.log_load_summary()
    assert len(caplog.records) == 0


def test_external_config_logs_candidates(tmp_path, caplog):
    """_load_external_config logs the candidate paths searched."""
    cfg = Config(DEFAULT_CONFIG, config_dir=tmp_path)
    with caplog.at_level("DEBUG", logger="festival_organizer.config"):
        cfg._load_external_config("festivals.json", {})
    assert any("festivals.json" in msg and "candidates" in msg for msg in caplog.messages)


def test_external_config_logs_loaded(tmp_path, caplog):
    """_load_external_config logs which path was loaded."""
    (tmp_path / "festivals.json").write_text("{}")
    cfg = Config(DEFAULT_CONFIG, config_dir=tmp_path)
    with caplog.at_level("DEBUG", logger="festival_organizer.config"):
        cfg._load_external_config("festivals.json", {})
    assert any("Loaded festivals.json from" in msg for msg in caplog.messages)


def test_external_config_logs_not_found(tmp_path, caplog):
    """_load_external_config logs when file is not found anywhere."""
    cfg = Config(DEFAULT_CONFIG, config_dir=tmp_path)
    with caplog.at_level("DEBUG", logger="festival_organizer.config"):
        with patch("festival_organizer.config.paths") as mock_paths:
            mock_paths.data_dir.return_value = tmp_path / "nonexistent"
            cfg._load_external_config("nope.json", {})
    assert any("not found" in msg for msg in caplog.messages)


def test_external_config_warns_on_malformed(tmp_path, caplog):
    """_load_external_config warns when a candidate file exists but fails to parse, and falls back to defaults."""
    (tmp_path / "festivals.json").write_text("{broken json")
    cfg = Config(DEFAULT_CONFIG, config_dir=tmp_path)
    defaults = {"sentinel": True}
    with caplog.at_level("WARNING", logger="festival_organizer.config"):
        result = cfg._load_external_config("festivals.json", defaults)
    assert result == defaults
    assert any(
        "festivals.json" in r.getMessage() and r.levelname == "WARNING"
        for r in caplog.records
    )


def test_places_json_loads_when_present(tmp_path):
    (tmp_path / "places.json").write_text('{"Printworks": {"color": "#000"}}')
    cfg = Config({}, config_dir=tmp_path)
    assert "Printworks" in cfg.place_config


def test_festivals_json_migrates_to_places_on_config_init(tmp_path, monkeypatch):
    """Legacy festivals.json is copied to places.json by the auto-migration
    helper that runs on Config construction, and place_config reads from it."""
    user_data = tmp_path / "user_data"
    user_data.mkdir()
    (user_data / "festivals.json").write_text('{"Tomorrowland": {"color": "#9B1B5A"}}')

    from festival_organizer import paths as paths_module
    monkeypatch.setattr(paths_module, "data_dir", lambda: user_data)

    cfg = Config({}, config_dir=user_data)

    assert (user_data / "places.json").is_file()
    assert "Tomorrowland" in cfg.place_config
    assert (user_data / "festivals.json").is_file(), "legacy file kept"


def test_places_wins_when_both_present(tmp_path):
    (tmp_path / "places.json").write_text('{"Printworks": {}}')
    (tmp_path / "festivals.json").write_text('{"Tomorrowland": {}}')
    cfg = Config({}, config_dir=tmp_path)
    assert "Printworks" in cfg.place_config
    assert "Tomorrowland" not in cfg.place_config


def test_place_aliases_includes_registry_aliases(tmp_path):
    (tmp_path / "places.json").write_text(
        '{"Tomorrowland": {"aliases": ["TML", "Tomorrowland Weekend 1"]}}'
    )
    cfg = Config({}, config_dir=tmp_path)
    assert cfg.place_aliases.get("TML") == "Tomorrowland"
    assert cfg.place_aliases.get("Tomorrowland Weekend 1") == "Tomorrowland"


def test_resolve_place_alias_returns_canonical(tmp_path):
    (tmp_path / "places.json").write_text(
        '{"Tomorrowland": {"aliases": ["TML"]}}'
    )
    cfg = Config({}, config_dir=tmp_path)
    assert cfg.resolve_place_alias("TML") == "Tomorrowland"
    assert cfg.resolve_place_alias("unknown") == "unknown"


def test_known_places_includes_canonicals_and_aliases(tmp_path):
    (tmp_path / "places.json").write_text(
        '{"Tomorrowland": {"aliases": ["TML"]}, "Printworks": {}}'
    )
    cfg = Config({}, config_dir=tmp_path)
    assert {"Tomorrowland", "TML", "Printworks"} <= cfg.known_places


def test_place_background_priority_default():
    cfg = Config({})
    assert cfg.poster_settings["place_background_priority"] == ["curated_logo", "gradient"]


def test_festival_background_priority_still_readable_with_deprecation(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    cfg = Config({"poster_settings": {"festival_background_priority": ["gradient"]}})
    assert cfg.poster_settings["place_background_priority"] == ["gradient"]
    assert any("festival_background_priority" in r.getMessage() for r in caplog.records)


def test_unknown_place_default():
    cfg = Config({})
    assert cfg.fallback_values["unknown_place"] == "_Needs Review"


def test_unknown_festival_still_readable_with_deprecation(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    cfg = Config({"fallback_values": {"unknown_festival": "_Custom"}})
    assert cfg.fallback_values["unknown_place"] == "_Custom"
    assert any("unknown_festival" in r.getMessage() for r in caplog.records)


def test_place_background_priority_user_value_wins_no_deprecation(caplog):
    """If user TOML sets BOTH keys, new wins and no deprecation log fires."""
    import logging
    caplog.set_level(logging.WARNING)
    cfg = Config({"poster_settings": {
        "festival_background_priority": ["gradient"],
        "place_background_priority": ["curated_logo"],
    }})
    assert cfg.poster_settings["place_background_priority"] == ["curated_logo"]
    assert not any("festival_background_priority" in r.getMessage() for r in caplog.records)


def test_unknown_place_user_value_wins_no_deprecation(caplog):
    """If user TOML sets BOTH keys, new wins and no deprecation log fires."""
    import logging
    caplog.set_level(logging.WARNING)
    cfg = Config({"fallback_values": {
        "unknown_festival": "_Old",
        "unknown_place": "_New",
    }})
    assert cfg.fallback_values["unknown_place"] == "_New"
    assert not any("unknown_festival" in r.getMessage() for r in caplog.records)


def test_resolve_artist_alias():
    config = Config({"artist_aliases": {"Dimitri Vegas & Like Mike": ["DVLM"], "Martin Garrix": ["Area21"]}})
    assert config.resolve_artist("DVLM") == "Dimitri Vegas & Like Mike"
    assert config.resolve_artist("Area21") == "Martin Garrix"
    assert config.resolve_artist("Hardwell") == "Hardwell"


def test_resolve_artist_case_insensitive():
    config = Config({"artist_aliases": {"Dimitri Vegas & Like Mike": ["dvlm"]}})
    assert config.resolve_artist("DVLM") == "Dimitri Vegas & Like Mike"


def test_resolve_artist_b2b_not_in_groups():
    config = Config({"artist_groups": ["Dimitri Vegas & Like Mike"]})
    assert config.resolve_artist("Armin van Buuren & KIKI") == "Armin van Buuren"


def test_resolve_artist_group_stays_intact():
    config = Config({"artist_groups": ["Dimitri Vegas & Like Mike"]})
    assert config.resolve_artist("Dimitri Vegas & Like Mike") == "Dimitri Vegas & Like Mike"


def test_resolve_artist_alias_then_group():
    config = Config({
        "artist_aliases": {"Dimitri Vegas & Like Mike": ["DVLM"]},
        "artist_groups": ["Dimitri Vegas & Like Mike"],
    })
    assert config.resolve_artist("DVLM") == "Dimitri Vegas & Like Mike"


def test_place_aliases_grouped_format():
    config = Config({"place_aliases": {
        "Tomorrowland": ["TML", "Tomorrowland Weekend 1"],
        "AMF": ["Amsterdam Music Festival"],
    }})
    assert config.resolve_place_alias("TML") == "Tomorrowland"
    assert config.resolve_place_alias("Tomorrowland Weekend 1") == "Tomorrowland"
    assert config.resolve_place_alias("Tomorrowland") == "Tomorrowland"
    assert config.resolve_place_alias("Amsterdam Music Festival") == "AMF"


def test_artist_aliases_grouped_format():
    config = Config({"artist_aliases": {
        "Martin Garrix": ["Area21", "YTRAM"],
    }})
    assert config.resolve_artist("Area21") == "Martin Garrix"
    assert config.resolve_artist("YTRAM") == "Martin Garrix"
    assert config.resolve_artist("Martin Garrix") == "Martin Garrix"


def test_place_aliases_flat_format():
    """Flat format {alias: canonical} should be handled correctly."""
    config = Config({"place_aliases": {
        "AMF": "AMF",
        "Amsterdam Music Festival": "AMF",
        "EDC": "EDC Las Vegas",
    }})
    assert config.resolve_place_alias("Amsterdam Music Festival") == "AMF"
    assert config.resolve_place_alias("AMF") == "AMF"
    assert config.resolve_place_alias("EDC") == "EDC Las Vegas"


def test_place_aliases_mixed_format():
    """Mixed dict with some grouped and some flat entries."""
    config = Config({"place_aliases": {
        "Tomorrowland": ["TML", "Tomorrowland Weekend 1"],
        "AMF": "AMF",
        "Amsterdam Music Festival": "AMF",
    }})
    assert config.resolve_place_alias("TML") == "Tomorrowland"
    assert config.resolve_place_alias("Amsterdam Music Festival") == "AMF"
    assert config.resolve_place_alias("AMF") == "AMF"


def test_invert_alias_map_flat_does_not_iterate_characters():
    """Flat format 'AMF': 'AMF' must NOT create entries for 'A', 'M', 'F'."""
    from festival_organizer.config import _invert_alias_map
    result = _invert_alias_map({"AMF": "AMF", "Amsterdam Music Festival": "AMF"})
    assert "A" not in result
    assert "M" not in result
    assert "F" not in result
    assert result["AMF"] == "AMF"
    assert result["Amsterdam Music Festival"] == "AMF"


def test_invert_alias_map_invalid_value_type_skipped():
    """Non-string, non-list values should be skipped with warning."""
    from festival_organizer.config import _invert_alias_map
    result = _invert_alias_map({
        "AMF": ["Amsterdam Music Festival"],
        "bad": 42,
        "also_bad": None,
    })
    assert result["AMF"] == "AMF"
    assert result["Amsterdam Music Festival"] == "AMF"
    assert "bad" not in result
    assert "also_bad" not in result


def test_invert_alias_map_circular_flat_warns(caplog):
    """Circular flat aliases should log a warning."""
    import logging
    from festival_organizer.config import _invert_alias_map
    with caplog.at_level(logging.WARNING):
        result = _invert_alias_map({
            "AMF": "Amsterdam Music Festival",
            "Amsterdam Music Festival": "AMF",
        })
    assert result["AMF"] == "Amsterdam Music Festival"
    assert result["Amsterdam Music Festival"] == "AMF"
    assert any("ircular" in msg for msg in caplog.messages)


def test_load_config_unreadable_file(tmp_path, caplog):
    """Unreadable config logs warning and falls back to defaults."""
    import os
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    cfg_file = user_dir / "config.toml"
    cfg_file.write_text('default_layout = "festival_flat"\n')
    os.chmod(cfg_file, 0o000)
    try:
        with caplog.at_level("WARNING", logger="festival_organizer.config"):
            config = load_config(user_config_file=cfg_file)
        assert config.default_layout == "artist_flat"  # fell back to default
        assert any("config.toml" in r.getMessage() for r in caplog.records)
    finally:
        os.chmod(cfg_file, 0o644)


class TestTomlConfigLoading:
    """Focused tests for the TOML loader contract (uses paths module)."""

    def test_loads_toml_config_from_user_dir(self, tmp_path):
        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "config.toml").write_text(
            'default_layout = "festival_nested"\n'
            '\n'
            '[kodi]\n'
            'enabled = true\n'
            'host = "192.168.1.10"\n'
        )
        with patch("festival_organizer.config.paths") as mock_paths:
            mock_paths.config_file.return_value = user_dir / "config.toml"
            cfg = load_config()
        assert cfg.default_layout == "festival_nested"
        assert cfg._data["kodi"]["enabled"] is True
        assert cfg._data["kodi"]["host"] == "192.168.1.10"

    def test_library_overrides_user(self, tmp_path):
        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "config.toml").write_text(
            'default_layout = "artist_nested"\n[kodi]\nenabled = false\n'
        )
        library_dir = tmp_path / "library" / ".cratedigger"
        library_dir.mkdir(parents=True)
        (library_dir / "config.toml").write_text(
            '[kodi]\nenabled = true\nhost = "library.local"\n'
        )
        with patch("festival_organizer.config.paths") as mock_paths:
            mock_paths.config_file.return_value = user_dir / "config.toml"
            cfg = load_config(library_config_dir=library_dir)
        assert cfg.default_layout == "artist_nested"
        assert cfg._data["kodi"]["enabled"] is True
        assert cfg._data["kodi"]["host"] == "library.local"

    def test_missing_config_uses_defaults(self, tmp_path):
        with patch("festival_organizer.config.paths") as mock_paths:
            mock_paths.config_file.return_value = tmp_path / "nonexistent.toml"
            cfg = load_config()
        assert cfg is not None
        assert cfg.default_layout

    def test_malformed_toml_logs_warning_and_uses_defaults(self, tmp_path, caplog):
        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "config.toml").write_text("this is not [valid toml")
        with patch("festival_organizer.config.paths") as mock_paths:
            mock_paths.config_file.return_value = user_dir / "config.toml"
            with caplog.at_level("WARNING", logger="festival_organizer.config"):
                cfg = load_config()
        assert any("could not read" in r.getMessage().lower() for r in caplog.records)
        assert cfg is not None


def test_legacy_library_config_json_logs_warning(tmp_path, caplog):
    """A legacy config.json in the library marker dir emits a single WARNING."""
    from festival_organizer.config import load_config

    library_dir = tmp_path / "library" / ".cratedigger"
    library_dir.mkdir(parents=True)
    (library_dir / "config.json").write_text(
        '{"default_layout": "festival_nested"}', encoding="utf-8"
    )

    with patch("festival_organizer.config.paths") as mock_paths:
        mock_paths.config_file.return_value = tmp_path / "nonexistent.toml"
        with caplog.at_level("WARNING", logger="festival_organizer.config"):
            load_config(library_config_dir=library_dir)

    messages = [r.getMessage() for r in caplog.records
                if r.name == "festival_organizer.config"]
    assert any("config.json" in m and "config.toml" in m for m in messages), (
        f"expected a WARNING mentioning both config.json and config.toml, got: {messages}"
    )


def test_legacy_library_config_json_silent_when_toml_absent_too(tmp_path, caplog):
    """No warning when the marker dir contains neither legacy nor new config."""
    from festival_organizer.config import load_config

    library_dir = tmp_path / "library" / ".cratedigger"
    library_dir.mkdir(parents=True)

    with patch("festival_organizer.config.paths") as mock_paths:
        mock_paths.config_file.return_value = tmp_path / "nonexistent.toml"
        with caplog.at_level("WARNING", logger="festival_organizer.config"):
            load_config(library_config_dir=library_dir)

    ours = [r for r in caplog.records if r.name == "festival_organizer.config"]
    assert not ours, f"expected no warnings, got: {[r.getMessage() for r in ours]}"


def test_artist_aliases_loads_dj_cache_once(monkeypatch):
    """Multiple accesses to config.artist_aliases must instantiate DjCache once."""
    from festival_organizer import config as config_mod
    from festival_organizer.tracklists import dj_cache as dj_cache_mod

    init_calls = []
    real_init = dj_cache_mod.DjCache.__init__

    def counting_init(self, *args, **kwargs):
        init_calls.append(1)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(dj_cache_mod.DjCache, "__init__", counting_init)

    cfg = config_mod.Config({})

    _ = cfg.artist_aliases
    _ = cfg.artist_aliases
    _ = cfg.artist_aliases

    assert len(init_calls) == 1, (
        f"expected DjCache to be constructed once, got {len(init_calls)}"
    )


def test_artist_groups_loads_dj_cache_once(monkeypatch):
    """Multiple accesses to config.artist_groups must instantiate DjCache once."""
    from festival_organizer import config as config_mod
    from festival_organizer.tracklists import dj_cache as dj_cache_mod

    init_calls = []
    real_init = dj_cache_mod.DjCache.__init__

    def counting_init(self, *args, **kwargs):
        init_calls.append(1)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(dj_cache_mod.DjCache, "__init__", counting_init)

    cfg = config_mod.Config({})

    _ = cfg.artist_groups
    _ = cfg.artist_groups
    _ = cfg.artist_groups

    assert len(init_calls) == 1, (
        f"expected DjCache to be constructed once, got {len(init_calls)}"
    )


@pytest.fixture
def cfg_with_places(tmp_path):
    (tmp_path / "places.json").write_text(
        '{"Tomorrowland": {"aliases": ["TML"]}, '
        '"Alexandra Palace": {"aliases": ["alexandra palace, london"]}}'
    )
    return Config({}, config_dir=tmp_path)


def test_resolve_place_chain_festival(cfg_with_places):
    mf = MediaFile(source_path=Path("/tmp/x.mkv"), festival="Tomorrowland")
    name, kind = cfg_with_places.resolve_place_for_media(mf)
    assert (name, kind) == ("Tomorrowland", "festival")


def test_resolve_place_chain_venue_canonical(cfg_with_places):
    mf = MediaFile(source_path=Path("/tmp/x.mkv"), venue="Alexandra Palace")
    name, kind = cfg_with_places.resolve_place_for_media(mf)
    assert (name, kind) == ("Alexandra Palace", "venue")


def test_resolve_place_chain_venue_raw(cfg_with_places):
    mf = MediaFile(source_path=Path("/tmp/x.mkv"), venue="Some Uncurated Bar")
    name, kind = cfg_with_places.resolve_place_for_media(mf)
    assert (name, kind) == ("Some Uncurated Bar", "venue")


def test_resolve_place_chain_location_resolves_through_alias(cfg_with_places):
    mf = MediaFile(source_path=Path("/tmp/x.mkv"), location="alexandra palace, london")
    name, kind = cfg_with_places.resolve_place_for_media(mf)
    assert (name, kind) == ("Alexandra Palace", "location")


def test_resolve_place_chain_location_raw(cfg_with_places):
    mf = MediaFile(source_path=Path("/tmp/x.mkv"),
                   location="Random Bar, Berlin, Germany")
    name, kind = cfg_with_places.resolve_place_for_media(mf)
    assert (name, kind) == ("Random Bar, Berlin, Germany", "location")


def test_resolve_place_chain_artist_fallback(cfg_with_places):
    mf = MediaFile(source_path=Path("/tmp/x.mkv"), artist="Fred again..")
    name, kind = cfg_with_places.resolve_place_for_media(mf)
    assert (name, kind) == ("Fred again..", "artist")


def test_resolve_place_chain_strips_whitespace_only_festival(cfg_with_places):
    """A whitespace-only festival field falls through to the next chain position."""
    mf = MediaFile(source_path=Path("/tmp/x.mkv"),
                   festival="   ", venue="Alexandra Palace",
                   artist="Fred again..")
    name, kind = cfg_with_places.resolve_place_for_media(mf)
    assert (name, kind) == ("Alexandra Palace", "venue")


def test_resolve_place_chain_strips_whitespace_only_venue(cfg_with_places):
    """A whitespace-only venue field falls through to the next chain position."""
    mf = MediaFile(source_path=Path("/tmp/x.mkv"),
                   venue="\t \n", location="Some Bar, Berlin",
                   artist="DJ Example")
    name, kind = cfg_with_places.resolve_place_for_media(mf)
    assert (name, kind) == ("Some Bar, Berlin", "location")


def test_resolve_place_chain_strips_whitespace_only_artist(cfg_with_places):
    """All-whitespace fields produce an empty result, not a whitespace folder."""
    mf = MediaFile(source_path=Path("/tmp/x.mkv"),
                   festival=" ", venue="  ", location="\t", artist="   ")
    name, kind = cfg_with_places.resolve_place_for_media(mf)
    assert (name, kind) == ("", "")


def test_resolve_place_chain_returns_stripped_value(cfg_with_places):
    """When a field has padding, the returned name is stripped."""
    mf = MediaFile(source_path=Path("/tmp/x.mkv"),
                   festival="  Tomorrowland  ")
    name, kind = cfg_with_places.resolve_place_for_media(mf)
    assert (name, kind) == ("Tomorrowland", "festival")
