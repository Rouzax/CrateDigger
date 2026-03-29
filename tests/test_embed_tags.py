import logging
from pathlib import Path
from unittest.mock import patch
from festival_organizer.embed_tags import embed_tags
from festival_organizer.models import MediaFile


def _make_mf(**kwargs):
    defaults = dict(source_path=Path("test.mkv"), artist="Test",
                    festival="TML", year="2024", content_type="festival_set")
    defaults.update(kwargs)
    return MediaFile(**defaults)


def test_embed_tags_failure_logged(tmp_path, caplog):
    """Tag embedding failure is logged via write_merged_tags."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()

    with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with patch("festival_organizer.embed_tags.write_merged_tags", return_value=False):
            result = embed_tags(mf, video)
    assert result is False


def test_embed_tags_calls_write_merged_tags(tmp_path):
    """embed_tags uses mkv_tags.write_merged_tags, not raw mkvpropedit."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf(artist="Afrojack", festival="EDC", year="2025")

    with patch("festival_organizer.embed_tags.write_merged_tags", return_value=True) as mock_wmt:
        with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
            result = embed_tags(mf, video)

    assert result is True
    mock_wmt.assert_called_once()
    call_args = mock_wmt.call_args
    assert call_args[0][0] == video
    tags_dict = call_args[0][1]
    assert 50 in tags_dict
    assert tags_dict[50]["ARTIST"] == "Afrojack"
    assert tags_dict[50]["TITLE"] == "EDC 2025"
    assert tags_dict[50]["DATE_RELEASED"] == "2025"
