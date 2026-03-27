import json
import tempfile
from pathlib import Path
from festival_organizer.config import Config, load_config, DEFAULT_CONFIG


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
    cfg = Config(DEFAULT_CONFIG)
    assert cfg.resolve_festival_alias("Amsterdam Music Festival") == "AMF"
    assert cfg.resolve_festival_alias("amf") == "AMF"
    assert cfg.resolve_festival_alias("EDC Las Vegas") == "EDC Las Vegas"
    assert cfg.resolve_festival_alias("Unknown Thing") == "Unknown Thing"


def test_config_festival_location():
    cfg = Config(DEFAULT_CONFIG)
    # Tomorrowland has location_in_name: true
    assert cfg.get_festival_display("Tomorrowland", "Belgium") == "Tomorrowland Belgium"
    assert cfg.get_festival_display("Tomorrowland", "") == "Tomorrowland"
    # AMF does not have location_in_name
    assert cfg.get_festival_display("AMF", "Netherlands") == "AMF"


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
        "festival_aliases": {"TML": "Tomorrowland"},
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
    cfg = Config(DEFAULT_CONFIG)
    festivals = cfg.known_festivals
    assert "AMF" in festivals
    assert "Tomorrowland" in festivals
    assert "EDC Las Vegas" in festivals


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
        "festival_aliases": {"My Fest": "My Festival"},
        "tracklists": {"email": "me@example.com", "password": "secret"},
    }))
    config = load_config(user_config_dir=user_dir)
    # User alias merged in
    assert config.resolve_festival_alias("My Fest") == "My Festival"
    # Built-in aliases still present
    assert config.resolve_festival_alias("EDC") == "EDC Las Vegas"
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
    assert tpl == "{festival}"
    # Concerts in flat layouts fall back to {artist}
    tpl = config.get_layout_template("concert_film", "artist_flat")
    assert tpl == "{artist}"
    tpl = config.get_layout_template("concert_film", "festival_flat")
    assert tpl == "{artist}"


def test_renamed_nested_layouts():
    """Old layout names renamed: artist_first -> artist_nested, etc."""
    config = load_config()
    tpl = config.get_layout_template("festival_set", "artist_nested")
    assert tpl == "{artist}/{festival}/{year}"
    tpl = config.get_layout_template("festival_set", "festival_nested")
    assert tpl == "{festival}/{year}/{artist}"


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
