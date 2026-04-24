import logging
from festival_organizer.poster import get_dominant_color_from_thumbs


def test_corrupt_thumb_logged_and_skipped(tmp_path, caplog):
    """Corrupt thumbnail is logged and skipped, returns default color."""
    bad_thumb = tmp_path / "bad-thumb.jpg"
    bad_thumb.write_bytes(b"not an image")

    with caplog.at_level(logging.DEBUG, logger="festival_organizer.poster"):
        color = get_dominant_color_from_thumbs([bad_thumb])
    assert color == (40, 80, 180)  # default blue fallback
    assert "bad-thumb.jpg" in caplog.text
