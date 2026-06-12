from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image
from festival_organizer import cover_embed


def _img(path, size):
    Image.new("RGB", size, (30, 30, 30)).save(str(path), "JPEG", quality=90)


def test_ensure_cover_land_skips_when_present(tmp_path):
    target = tmp_path / "v.mkv"; target.touch()
    atts = [{"id": 1, "file_name": "cover.jpg", "content_type": "image/jpeg"},
            {"id": 2, "file_name": "cover_land.png", "content_type": "image/png"}]
    with patch.object(cover_embed, "add_attachment") as add:
        cover_embed.ensure_cover_land(target, atts, tmp_path / "v-thumb.jpg")
    add.assert_not_called()


def test_ensure_cover_land_preserves_landscape_cover(tmp_path):
    target = tmp_path / "v.mkv"; target.touch()
    atts = [{"id": 1, "file_name": "cover.png", "content_type": "image/png"}]

    def fake_extract(src, att_id, dest):
        _img(Path(dest), (1280, 720))  # landscape
        return True

    with patch.object(cover_embed, "extract_attachment", side_effect=fake_extract), \
         patch.object(cover_embed, "add_attachment", return_value=True) as add:
        cover_embed.ensure_cover_land(target, atts, tmp_path / "v-thumb.jpg")
    assert add.call_args.args[2] == "cover_land.png"


def test_ensure_cover_land_recovers_from_thumb_when_no_landscape(tmp_path):
    target = tmp_path / "v.mkv"; target.touch()
    thumb = tmp_path / "v-thumb.jpg"; _img(thumb, (1280, 720))
    atts = [{"id": 1, "file_name": "cover.jpg", "content_type": "image/jpeg"}]

    def fake_extract(src, att_id, dest):
        _img(Path(dest), (1000, 1500))  # the existing cover is portrait, not a landscape
        return True

    with patch.object(cover_embed, "extract_attachment", side_effect=fake_extract), \
         patch.object(cover_embed, "add_attachment", return_value=True) as add:
        cover_embed.ensure_cover_land(target, atts, thumb)
    assert add.call_args.args[2] == "cover_land.jpg"
    assert add.call_args.args[1] == thumb


def test_set_primary_cover_renames_landscape_png_slot(tmp_path):
    target = tmp_path / "v.mkv"; target.touch()
    poster = tmp_path / "v-poster.jpg"; _img(poster, (1000, 1500))
    atts = [{"id": 1, "file_name": "cover.png", "content_type": "image/png"}]
    with patch.object(cover_embed, "replace_attachment", return_value=True) as rep, \
         patch.object(cover_embed, "add_attachment") as add:
        cover_embed.set_primary_cover(target, poster, atts)
    rep.assert_called_once_with(target, "cover.png", poster, "cover.jpg", "image/jpeg")
    add.assert_not_called()


def test_set_primary_cover_adds_when_no_cover(tmp_path):
    target = tmp_path / "v.mkv"; target.touch()
    poster = tmp_path / "v-poster.jpg"; _img(poster, (1000, 1500))
    with patch.object(cover_embed, "add_attachment", return_value=True) as add, \
         patch.object(cover_embed, "replace_attachment") as rep:
        cover_embed.set_primary_cover(target, poster, [])
    add.assert_called_once_with(target, poster, "cover.jpg", "image/jpeg")
    rep.assert_not_called()
