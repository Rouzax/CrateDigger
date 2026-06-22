import io

from PIL import Image

from festival_organizer.notify.thumbnails import make_thumbnail


def _make_poster(tmp_path, w=1920, h=1080):
    p = tmp_path / "set-poster.jpg"
    Image.new("RGB", (w, h), (40, 40, 60)).save(p, format="JPEG")
    return p


def test_make_thumbnail_resizes_to_2x_width_and_keeps_aspect(tmp_path):
    poster = _make_poster(tmp_path)
    data = make_thumbnail(poster, 140)
    img = Image.open(io.BytesIO(data))
    assert img.width == 280  # 2x of 140 for retina
    assert img.height == 158  # 1080 * (280/1920) rounded
    assert img.format == "JPEG"


def test_make_thumbnail_handles_non_rgb(tmp_path):
    p = tmp_path / "p.png"
    Image.new("RGBA", (400, 200), (10, 20, 30, 255)).save(p)
    data = make_thumbnail(p, 100)
    assert Image.open(io.BytesIO(data)).width == 200
