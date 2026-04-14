"""AlbumArtistMbidsOperation: extract CRATEDIGGER_1001TL_ARTISTS → resolve → write."""
from pathlib import Path
from unittest.mock import patch

from festival_organizer.models import MediaFile
from festival_organizer.operations import AlbumArtistMbidsOperation


def _make_mf():
    return MediaFile(
        source_path=Path("test.mkv"),
        artist="Test",
        festival="TML",
        year="2024",
        content_type="festival_set",
    )


def _mock_tags(existing_70: dict[str, str]):
    """Patch extract_all_tags + _tag_values_from_root to return a given TTV=70 dict."""
    sentinel_root = object()
    return (
        patch("festival_organizer.mkv_tags.extract_all_tags", return_value=sentinel_root),
        patch("festival_organizer.mkv_tags._tag_values_from_root", return_value={70: existing_70}),
    )


def test_is_needed_false_without_matroska_extension(tmp_path):
    op = AlbumArtistMbidsOperation()
    (tmp_path / "foo.mp4").write_bytes(b"")
    assert op.is_needed(tmp_path / "foo.mp4", _make_mf()) is False


def test_is_needed_true_for_mkv(tmp_path):
    op = AlbumArtistMbidsOperation()
    (tmp_path / "foo.mkv").write_bytes(b"")
    assert op.is_needed(tmp_path / "foo.mkv", _make_mf()) is True


def test_execute_skipped_when_no_1001tl_artists(tmp_path):
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    extract_p, tvals_p = _mock_tags({})
    with extract_p, tvals_p, \
         patch("festival_organizer.mkv_tags.write_merged_tags") as write_fn:
        op = AlbumArtistMbidsOperation()
        result = op.execute(mkv, _make_mf())
    assert result.status == "skipped"
    assert "1001TL_ARTISTS" in result.detail
    write_fn.assert_not_called()


def test_execute_writes_aligned_mbids(tmp_path):
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    existing_70 = {"CRATEDIGGER_1001TL_ARTISTS": "Armin van Buuren|KI/KI|Mystery"}

    def fake_lookup(name, cache, overrides=None):
        return {"Armin van Buuren": "armin-mbid", "KI/KI": "kiki-mbid"}.get(name)

    extract_p, tvals_p = _mock_tags(existing_70)
    with extract_p, tvals_p, \
         patch("festival_organizer.mkv_tags.write_merged_tags") as write_fn, \
         patch("festival_organizer.operations.lookup_mbid", side_effect=fake_lookup):
        op = AlbumArtistMbidsOperation()
        result = op.execute(mkv, _make_mf())

    assert result.status == "done"
    write_fn.assert_called_once()
    _, tags_dict = write_fn.call_args.args
    # Aligned with CRATEDIGGER_1001TL_ARTISTS, empty slot for Mystery.
    assert tags_dict == {70: {"CRATEDIGGER_ALBUMARTIST_MBIDS": "armin-mbid|kiki-mbid|"}}


def test_execute_skipped_when_all_artists_unresolvable(tmp_path):
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    existing_70 = {"CRATEDIGGER_1001TL_ARTISTS": "UnknownA|UnknownB"}

    extract_p, tvals_p = _mock_tags(existing_70)
    with extract_p, tvals_p, \
         patch("festival_organizer.mkv_tags.write_merged_tags") as write_fn, \
         patch("festival_organizer.operations.lookup_mbid", return_value=None):
        op = AlbumArtistMbidsOperation()
        result = op.execute(mkv, _make_mf())

    assert result.status == "skipped"
    assert "no resolvable" in result.detail
    write_fn.assert_not_called()


def test_execute_skipped_when_mbids_already_current(tmp_path):
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    existing_70 = {
        "CRATEDIGGER_1001TL_ARTISTS": "Armin van Buuren|KI/KI",
        "CRATEDIGGER_ALBUMARTIST_MBIDS": "armin-mbid|kiki-mbid",
    }

    def fake_lookup(name, cache, overrides=None):
        return {"Armin van Buuren": "armin-mbid", "KI/KI": "kiki-mbid"}.get(name)

    extract_p, tvals_p = _mock_tags(existing_70)
    with extract_p, tvals_p, \
         patch("festival_organizer.mkv_tags.write_merged_tags") as write_fn, \
         patch("festival_organizer.operations.lookup_mbid", side_effect=fake_lookup):
        op = AlbumArtistMbidsOperation()
        result = op.execute(mkv, _make_mf())

    assert result.status == "skipped"
    assert "already current" in result.detail
    write_fn.assert_not_called()


def test_force_rewrites_even_when_mbids_match(tmp_path):
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    existing_70 = {
        "CRATEDIGGER_1001TL_ARTISTS": "Armin van Buuren",
        "CRATEDIGGER_ALBUMARTIST_MBIDS": "armin-mbid",
    }

    extract_p, tvals_p = _mock_tags(existing_70)
    with extract_p, tvals_p, \
         patch("festival_organizer.mkv_tags.write_merged_tags") as write_fn, \
         patch("festival_organizer.operations.lookup_mbid", return_value="armin-mbid"):
        op = AlbumArtistMbidsOperation(force=True)
        result = op.execute(mkv, _make_mf())

    assert result.status == "done"
    write_fn.assert_called_once()


def test_force_rewrites_when_stale_mbids_present(tmp_path):
    mkv = tmp_path / "set.mkv"
    mkv.write_bytes(b"")
    existing_70 = {
        "CRATEDIGGER_1001TL_ARTISTS": "Armin van Buuren",
        "CRATEDIGGER_ALBUMARTIST_MBIDS": "STALE",
    }

    extract_p, tvals_p = _mock_tags(existing_70)
    with extract_p, tvals_p, \
         patch("festival_organizer.mkv_tags.write_merged_tags") as write_fn, \
         patch("festival_organizer.operations.lookup_mbid", return_value="FRESH"):
        op = AlbumArtistMbidsOperation()
        result = op.execute(mkv, _make_mf())

    assert result.status == "done"
    _, tags_dict = write_fn.call_args.args
    assert tags_dict == {70: {"CRATEDIGGER_ALBUMARTIST_MBIDS": "FRESH"}}
