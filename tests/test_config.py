import json
import tempfile
from pathlib import Path
from festival_organizer.config import Config, load_config, DEFAULT_CONFIG


def test_default_config_has_required_keys():
    cfg = Config(DEFAULT_CONFIG)
    assert cfg.default_layout == "artist_first"
    assert "artist_first" in cfg.layouts
    assert "festival_first" in cfg.layouts
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
    fs = cfg.get_layout_template("festival_set")
    assert "{artist}" in fs
    assert "{festival}" in fs
    cf = cfg.get_layout_template("concert_film")
    assert "{artist}" in cf


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
    assert cfg.default_layout == "festival_first"
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
