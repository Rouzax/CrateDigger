import json
from unittest.mock import patch, MagicMock
from festival_organizer import mkv_attachments as att


def _proc(stdout="", rc=0):
    m = MagicMock()
    m.returncode = rc
    m.stdout = stdout
    return m


def test_classify_ratio():
    assert att.classify_ratio(1280, 720) == "landscape"
    assert att.classify_ratio(1000, 1500) == "portrait"
    assert att.classify_ratio(500, 500) == "square"
    assert att.classify_ratio(0, 10) == "unknown"


def test_list_image_attachments_filters_images(tmp_path):
    src = tmp_path / "v.mkv"
    src.touch()
    payload = json.dumps({"attachments": [
        {"id": 1, "file_name": "cover.png", "content_type": "image/png"},
        {"id": 2, "file_name": "subs.srt", "content_type": "application/x-subrip"},
    ]})
    with patch("festival_organizer.metadata.MKVMERGE_PATH", "/usr/bin/mkvmerge"), \
         patch("festival_organizer.mkv_attachments.tracked_run", return_value=_proc(payload)):
        out = att.list_image_attachments(src)
    assert out == [{"id": 1, "file_name": "cover.png", "content_type": "image/png"}]


def test_list_image_attachments_no_tool(tmp_path):
    with patch("festival_organizer.metadata.MKVMERGE_PATH", None):
        assert att.list_image_attachments(tmp_path / "v.mkv") == []
