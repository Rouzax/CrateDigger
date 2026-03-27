import logging
import subprocess as subprocess_mod
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
    """Tag embedding failure is logged."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()

    with patch("festival_organizer.embed_tags.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"):
        with patch("festival_organizer.embed_tags.subprocess.run",
                   side_effect=subprocess_mod.SubprocessError("nope")):
            with caplog.at_level(logging.DEBUG, logger="festival_organizer.embed_tags"):
                result = embed_tags(mf, video)
    assert result is False
    assert "nope" in caplog.text
