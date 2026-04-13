"""User-curated artist MBID overrides (~/.cratedigger/artist_mbids.json)."""
import json

from festival_organizer.fanart import ArtistMbidOverrides


def test_returns_none_when_file_missing(tmp_path):
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)
    assert overrides.get("Afrojack") is None


def test_returns_pinned_mbid(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(json.dumps({
        "Afrojack": "ffe35dc6-3088-4705-9156-1cc11ab8af71",
    }))
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)
    assert overrides.get("Afrojack") == "ffe35dc6-3088-4705-9156-1cc11ab8af71"


def test_case_insensitive_match(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(json.dumps({
        "Afrojack": "ffe35dc6-3088-4705-9156-1cc11ab8af71",
    }))
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)
    assert overrides.get("AFROJACK") == "ffe35dc6-3088-4705-9156-1cc11ab8af71"
    assert overrides.get("afrojack") == "ffe35dc6-3088-4705-9156-1cc11ab8af71"


def test_returns_none_for_unknown_artist(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(json.dumps({
        "Afrojack": "ffe35dc6-3088-4705-9156-1cc11ab8af71",
    }))
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)
    assert overrides.get("Some Unknown Artist") is None


def test_malformed_json_does_not_raise(tmp_path, caplog):
    (tmp_path / "artist_mbids.json").write_text("{not json")
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)
    assert overrides.get("Afrojack") is None
    assert any("artist_mbids.json" in rec.message.lower() for rec in caplog.records)


def test_non_dict_top_level_does_not_raise(tmp_path):
    # Must tolerate a JSON file whose top level is a list or string.
    (tmp_path / "artist_mbids.json").write_text("[]")
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)
    assert overrides.get("Afrojack") is None


def test_ignores_non_string_values(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(json.dumps({
        "Afrojack": "ffe35dc6-3088-4705-9156-1cc11ab8af71",
        "Weird": 42,       # non-string, ignored
        "Blank": "",       # empty, ignored
    }))
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)
    assert overrides.get("Afrojack") == "ffe35dc6-3088-4705-9156-1cc11ab8af71"
    assert overrides.get("Weird") is None
    assert overrides.get("Blank") is None


def test_has_method_reports_presence(tmp_path):
    (tmp_path / "artist_mbids.json").write_text(json.dumps({"Afrojack": "ffe35dc6"}))
    overrides = ArtistMbidOverrides(overrides_dir=tmp_path)
    assert overrides.has("Afrojack") is True
    assert overrides.has("afrojack") is True
    assert overrides.has("Unknown") is False
