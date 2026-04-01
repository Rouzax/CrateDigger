import json
import tempfile
from pathlib import Path
from festival_organizer.config import Config, load_config, DEFAULT_CONFIG
from tests.conftest import TEST_CONFIG


def test_default_config_has_required_keys():
    cfg = Config(DEFAULT_CONFIG)
    assert cfg.default_layout == "artist_flat"
    assert "artist_flat" in cfg.layouts
    assert "festival_flat" in cfg.layouts
    assert "artist_nested" in cfg.layouts
    assert "festival_nested" in cfg.layouts
    assert "festival_set" in cfg.filename_templates
    assert "concert_film" in cfg.filename_templates


def test_config_festival_aliases():
    cfg = Config(TEST_CONFIG)
    assert cfg.resolve_festival_alias("Amsterdam Music Festival") == "AMF"
    assert cfg.resolve_festival_alias("amf") == "AMF"
    # "EDC Las Vegas" is no longer an alias; resolved via edition decomposition
    assert cfg.resolve_festival_alias("EDC Las Vegas") == "EDC Las Vegas"
    assert cfg.resolve_festival_alias("Unknown Thing") == "Unknown Thing"


def test_config_festival_edition():
    cfg = Config(TEST_CONFIG)
    # Tomorrowland has editions configured
    assert cfg.get_festival_display("Tomorrowland", "Belgium") == "Tomorrowland Belgium"
    assert cfg.get_festival_display("Tomorrowland", "") == "Tomorrowland"
    # AMF has no editions
    assert cfg.get_festival_display("AMF", "Netherlands") == "AMF"


def test_get_festival_display_rejects_unknown_edition():
    cfg = Config(TEST_CONFIG)
    # Dreamstate has editions: [SoCal, Europe, Australia, Mexico]
    # "United States" is not in that list, should be omitted
    assert cfg.get_festival_display("Dreamstate", "United States") == "Dreamstate"
    assert cfg.get_festival_display("Dreamstate", "SoCal") == "Dreamstate SoCal"


def test_resolve_festival_with_edition():
    cfg = Config(TEST_CONFIG)
    # Edition decomposition (no alias needed)
    assert cfg.resolve_festival_with_edition("Tomorrowland Winter") == ("Tomorrowland", "Winter")
    assert cfg.resolve_festival_with_edition("Tomorrowland Belgium") == ("Tomorrowland", "Belgium")
    assert cfg.resolve_festival_with_edition("EDC Las Vegas") == ("EDC", "Las Vegas")
    assert cfg.resolve_festival_with_edition("Dreamstate SoCal") == ("Dreamstate", "SoCal")
    assert cfg.resolve_festival_with_edition("Dreamstate Europe") == ("Dreamstate", "Europe")
    # Alias prefix + edition (Ultra is alias for Ultra Music Festival)
    assert cfg.resolve_festival_with_edition("Ultra Europe") == ("Ultra Music Festival", "Europe")
    assert cfg.resolve_festival_with_edition("Ultra Music Festival Miami") == ("Ultra Music Festival", "Miami")
    # Pure alias (no edition)
    assert cfg.resolve_festival_with_edition("TML") == ("Tomorrowland", "")
    assert cfg.resolve_festival_with_edition("AMF") == ("AMF", "")
    # Alias that collapses weekends (no edition extracted)
    assert cfg.resolve_festival_with_edition("Tomorrowland Weekend 1") == ("Tomorrowland", "")
    # Genuine alternate name (not an edition)
    assert cfg.resolve_festival_with_edition("Red Rocks Amphitheatre") == ("Red Rocks", "")
    # Unknown festival
    assert cfg.resolve_festival_with_edition("Unknown Fest") == ("Unknown Fest", "")


def test_resolve_festival_with_edition_case_insensitive():
    cfg = Config(TEST_CONFIG)
    assert cfg.resolve_festival_with_edition("tomorrowland winter") == ("Tomorrowland", "Winter")
    assert cfg.resolve_festival_with_edition("EDC LAS VEGAS") == ("EDC", "Las Vegas")


def test_known_festivals_includes_edition_combos():
    cfg = Config(TEST_CONFIG)
    known = cfg.known_festivals
    # Canonical names
    assert "Tomorrowland" in known
    assert "EDC" in known
    # Edition combos (generated dynamically)
    assert "Tomorrowland Winter" in known
    assert "Tomorrowland Belgium" in known
    assert "EDC Las Vegas" in known
    # Aliases
    assert "TML" in known
    assert "Ultra" in known


def test_get_festival_display_with_editions():
    cfg = Config(TEST_CONFIG)
    assert cfg.get_festival_display("Tomorrowland", "Belgium") == "Tomorrowland Belgium"
    assert cfg.get_festival_display("Tomorrowland", "Winter") == "Tomorrowland Winter"
    assert cfg.get_festival_display("Tomorrowland", "") == "Tomorrowland"
    # AMF has no editions configured
    assert cfg.get_festival_display("AMF", "Netherlands") == "AMF"
    # Unknown edition rejected
    assert cfg.get_festival_display("Dreamstate", "United States") == "Dreamstate"
    assert cfg.get_festival_display("Dreamstate", "SoCal") == "Dreamstate SoCal"


def test_config_layout_templates():
    cfg = Config(DEFAULT_CONFIG)
    # Default layout is now artist_flat
    fs = cfg.get_layout_template("festival_set")
    assert "{artist}" in fs
    cf = cfg.get_layout_template("concert_film")
    assert "{artist}" in cf
    # Nested layouts still have festival
    fs_nested = cfg.get_layout_template("festival_set", "artist_nested")
    assert "{artist}" in fs_nested
    assert "{festival}" in fs_nested


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


def test_load_config_from_file():
    data = {
        "default_layout": "festival_first",
        "festival_aliases": {"Tomorrowland": ["TML"]},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        f.flush()
        cfg = load_config(Path(f.name))
    # Custom value overrides default
    assert cfg.default_layout == "festival_nested"
    # Custom alias merged
    assert cfg.resolve_festival_alias("TML") == "Tomorrowland"
    # Default aliases still present
    assert cfg.resolve_festival_alias("AMF") == "AMF"


def test_config_media_extensions():
    cfg = Config(DEFAULT_CONFIG)
    assert ".mkv" in cfg.media_extensions
    assert ".mp4" in cfg.media_extensions
    assert ".mp3" in cfg.media_extensions
    assert ".txt" not in cfg.media_extensions


def test_config_known_festivals():
    cfg = Config(TEST_CONFIG)
    festivals = cfg.known_festivals
    assert "AMF" in festivals
    assert "Tomorrowland" in festivals
    assert "EDC" in festivals


def test_load_config_builtin_defaults():
    """Built-in defaults load when no files exist."""
    config = load_config()
    assert config.default_layout == "artist_flat"
    assert "artist_flat" in config.layouts
    assert "festival_flat" in config.layouts
    assert "artist_nested" in config.layouts
    assert "festival_nested" in config.layouts


def test_load_config_user_layer(tmp_path):
    """User config at ~/.cratedigger/config.json merges over built-in."""
    user_dir = tmp_path / ".cratedigger"
    user_dir.mkdir()
    user_config = user_dir / "config.json"
    user_config.write_text(json.dumps({
        "festival_aliases": {"My Festival": ["My Fest"]},
        "tracklists": {"email": "me@example.com", "password": "secret"},
    }))
    config = load_config(user_config_dir=user_dir)
    # User alias merged in
    assert config.resolve_festival_alias("My Fest") == "My Festival"
    # Built-in aliases still present
    assert config.resolve_festival_alias("EDC") == "EDC"
    # Credentials accessible
    assert config.tracklists_credentials == ("me@example.com", "secret")


def test_load_config_library_layer(tmp_path):
    """Library config merges over user config."""
    lib_dir = tmp_path / ".cratedigger"
    lib_dir.mkdir()
    lib_config = lib_dir / "config.json"
    lib_config.write_text(json.dumps({"default_layout": "festival_flat"}))
    config = load_config(library_config_dir=lib_dir)
    assert config.default_layout == "festival_flat"


def test_load_config_merge_order(tmp_path):
    """Library overrides user overrides built-in."""
    user_dir = tmp_path / "user" / ".cratedigger"
    user_dir.mkdir(parents=True)
    (user_dir / "config.json").write_text(json.dumps({
        "default_layout": "artist_nested",
    }))
    lib_dir = tmp_path / "lib" / ".cratedigger"
    lib_dir.mkdir(parents=True)
    (lib_dir / "config.json").write_text(json.dumps({
        "default_layout": "festival_nested",
    }))
    config = load_config(user_config_dir=user_dir, library_config_dir=lib_dir)
    assert config.default_layout == "festival_nested"


def test_new_flat_layouts():
    """Built-in defaults include flat layout templates."""
    config = load_config()
    # artist_flat
    tpl = config.get_layout_template("festival_set", "artist_flat")
    assert tpl == "{artist}"
    # festival_flat
    tpl = config.get_layout_template("festival_set", "festival_flat")
    assert tpl == "{festival}{ edition}"
    # Concerts in flat layouts fall back to {artist}
    tpl = config.get_layout_template("concert_film", "artist_flat")
    assert tpl == "{artist}"
    tpl = config.get_layout_template("concert_film", "festival_flat")
    assert tpl == "{artist}"


def test_renamed_nested_layouts():
    """Old layout names renamed: artist_first -> artist_nested, etc."""
    config = load_config()
    tpl = config.get_layout_template("festival_set", "artist_nested")
    assert tpl == "{artist}/{festival}{ edition}/{year}"
    tpl = config.get_layout_template("festival_set", "festival_nested")
    assert tpl == "{festival}{ edition}/{year}/{artist}"


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


def test_load_config_malformed_json(tmp_path, capsys):
    """Malformed user config prints warning and falls back to defaults."""
    user_dir = tmp_path / ".cratedigger"
    user_dir.mkdir()
    (user_dir / "config.json").write_text("{bad json!!!")
    config = load_config(user_config_dir=user_dir)
    assert config.default_layout == "artist_flat"  # fell back to default
    captured = capsys.readouterr()
    assert "config.json" in captured.err


def test_load_config_malformed_library_json(tmp_path, capsys):
    """Malformed library config prints warning, user config still applies."""
    user_dir = tmp_path / "user" / ".cratedigger"
    user_dir.mkdir(parents=True)
    (user_dir / "config.json").write_text('{"default_layout": "festival_flat"}')
    lib_dir = tmp_path / "lib" / ".cratedigger"
    lib_dir.mkdir(parents=True)
    (lib_dir / "config.json").write_text("not json")
    config = load_config(user_config_dir=user_dir, library_config_dir=lib_dir)
    assert config.default_layout == "festival_flat"  # user layer applied
    captured = capsys.readouterr()
    assert "config.json" in captured.err


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


def test_festival_aliases_grouped_format():
    config = Config({"festival_aliases": {
        "Tomorrowland": ["TML", "Tomorrowland Weekend 1"],
        "AMF": ["Amsterdam Music Festival"],
    }})
    assert config.resolve_festival_alias("TML") == "Tomorrowland"
    assert config.resolve_festival_alias("Tomorrowland Weekend 1") == "Tomorrowland"
    assert config.resolve_festival_alias("Tomorrowland") == "Tomorrowland"
    assert config.resolve_festival_alias("Amsterdam Music Festival") == "AMF"


def test_artist_aliases_grouped_format():
    config = Config({"artist_aliases": {
        "Martin Garrix": ["Area21", "YTRAM"],
    }})
    assert config.resolve_artist("Area21") == "Martin Garrix"
    assert config.resolve_artist("YTRAM") == "Martin Garrix"
    assert config.resolve_artist("Martin Garrix") == "Martin Garrix"


def test_festival_aliases_flat_format():
    """Flat format {alias: canonical} should be handled correctly."""
    config = Config({"festival_aliases": {
        "AMF": "AMF",
        "Amsterdam Music Festival": "AMF",
        "EDC": "EDC Las Vegas",
    }})
    assert config.resolve_festival_alias("Amsterdam Music Festival") == "AMF"
    assert config.resolve_festival_alias("AMF") == "AMF"
    assert config.resolve_festival_alias("EDC") == "EDC Las Vegas"


def test_festival_aliases_mixed_format():
    """Mixed dict with some grouped and some flat entries."""
    config = Config({"festival_aliases": {
        "Tomorrowland": ["TML", "Tomorrowland Weekend 1"],
        "AMF": "AMF",
        "Amsterdam Music Festival": "AMF",
    }})
    assert config.resolve_festival_alias("TML") == "Tomorrowland"
    assert config.resolve_festival_alias("Amsterdam Music Festival") == "AMF"
    assert config.resolve_festival_alias("AMF") == "AMF"


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


def test_load_config_unreadable_file(tmp_path, capsys):
    """Unreadable config prints warning and falls back to defaults."""
    import os
    user_dir = tmp_path / ".cratedigger"
    user_dir.mkdir()
    cfg_file = user_dir / "config.json"
    cfg_file.write_text('{"default_layout": "festival_flat"}')
    os.chmod(cfg_file, 0o000)
    try:
        config = load_config(user_config_dir=user_dir)
        assert config.default_layout == "artist_flat"  # fell back to default
        captured = capsys.readouterr()
        assert "config.json" in captured.err
    finally:
        os.chmod(cfg_file, 0o644)
