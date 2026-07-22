import json
from unittest.mock import MagicMock, patch

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
    payload = json.dumps(
        {
            "attachments": [
                {"id": 1, "file_name": "cover.png", "content_type": "image/png"},
                {
                    "id": 2,
                    "file_name": "subs.srt",
                    "content_type": "application/x-subrip",
                },
            ]
        }
    )
    with (
        patch("festival_organizer.metadata.MKVMERGE_PATH", "/usr/bin/mkvmerge"),
        patch(
            "festival_organizer.mkv_attachments.tracked_run",
            return_value=_proc(payload),
        ),
    ):
        out = att.list_image_attachments(src)
    assert out == [{"id": 1, "file_name": "cover.png", "content_type": "image/png"}]


def test_list_image_attachments_no_tool(tmp_path):
    with patch("festival_organizer.metadata.MKVMERGE_PATH", None):
        assert att.list_image_attachments(tmp_path / "v.mkv") == []


def test_image_ratio_class_reads_real_image(tmp_path):
    from PIL import Image

    p = tmp_path / "land.png"
    Image.new("RGB", (1280, 720), (20, 20, 20)).save(str(p))
    assert att.image_ratio_class(p) == "landscape"
    q = tmp_path / "port.png"
    Image.new("RGB", (1000, 1500), (20, 20, 20)).save(str(q))
    assert att.image_ratio_class(q) == "portrait"


def test_image_ratio_class_unreadable_returns_unknown(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert att.image_ratio_class(bad) == "unknown"
    assert att.image_ratio_class(tmp_path / "missing.png") == "unknown"


def test_list_image_attachments_extension_fallback(tmp_path):
    src = tmp_path / "v.mkv"
    src.touch()
    payload = json.dumps(
        {
            "attachments": [
                {"id": 1, "file_name": "art.jpg", "content_type": ""},
            ]
        }
    )
    with (
        patch("festival_organizer.metadata.MKVMERGE_PATH", "/usr/bin/mkvmerge"),
        patch(
            "festival_organizer.mkv_attachments.tracked_run",
            return_value=_proc(payload),
        ),
    ):
        out = att.list_image_attachments(src)
    assert out == [{"id": 1, "file_name": "art.jpg", "content_type": ""}]


def test_list_image_attachments_nonzero_returncode(tmp_path):
    src = tmp_path / "v.mkv"
    src.touch()
    with (
        patch("festival_organizer.metadata.MKVMERGE_PATH", "/usr/bin/mkvmerge"),
        patch(
            "festival_organizer.mkv_attachments.tracked_run",
            return_value=_proc("", rc=1),
        ),
    ):
        assert att.list_image_attachments(src) == []


def test_write_helpers_build_correct_argv(tmp_path):
    target = tmp_path / "v.mkv"
    target.touch()
    data = tmp_path / "img.jpg"
    data.touch()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _proc("", rc=0)

    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"),
        patch("festival_organizer.mkv_attachments.tracked_run", side_effect=fake_run),
    ):
        assert att.add_attachment(target, data, "cover.jpg", "image/jpeg") is True
        assert (
            att.replace_attachment(target, "cover.png", data, "cover.jpg", "image/jpeg")
            is True
        )
        assert att.delete_attachment(target, "cover_land.png") is True

    assert calls[0] == [
        "/usr/bin/mkvpropedit",
        str(target),
        "--attachment-name",
        "cover.jpg",
        "--attachment-mime-type",
        "image/jpeg",
        "--add-attachment",
        str(data),
    ]
    assert calls[1] == [
        "/usr/bin/mkvpropedit",
        str(target),
        "--attachment-name",
        "cover.jpg",
        "--attachment-mime-type",
        "image/jpeg",
        "--replace-attachment",
        f"name:cover.png:{data}",
    ]
    assert calls[2] == [
        "/usr/bin/mkvpropedit",
        str(target),
        "--delete-attachment",
        "name:cover_land.png",
    ]


def test_write_helpers_return_false_without_tool(tmp_path):
    target = tmp_path / "v.mkv"
    target.touch()
    with patch("festival_organizer.metadata.MKVPROPEDIT_PATH", None):
        assert att.add_attachment(target, target, "cover.jpg", "image/jpeg") is False
        assert att.delete_attachment(target, "cover.jpg") is False
    with patch("festival_organizer.metadata.MKVEXTRACT_PATH", None):
        assert att.extract_attachment(target, 1, tmp_path / "o.png") is False


def test_delete_all_image_attachments_builds_single_multi_delete_call(tmp_path):
    target = tmp_path / "v.webm"
    target.touch()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _proc("", rc=0)

    atts = [
        {"id": 1, "file_name": "cover.jpg", "content_type": "image/jpeg"},
        {"id": 2, "file_name": "cover_land.png", "content_type": "image/png"},
    ]
    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"),
        patch.object(att, "list_image_attachments", return_value=atts),
        patch("festival_organizer.mkv_attachments.tracked_run", side_effect=fake_run),
    ):
        removed = att.delete_all_image_attachments(target)

    assert removed == 2
    assert len(calls) == 1  # one mkvpropedit invocation, not one per attachment
    assert calls[0] == [
        "/usr/bin/mkvpropedit",
        str(target),
        "--delete-attachment",
        "name:cover.jpg",
        "--delete-attachment",
        "name:cover_land.png",
    ]


def test_delete_all_image_attachments_noop_when_none(tmp_path):
    target = tmp_path / "v.webm"
    target.touch()
    with (
        patch.object(att, "list_image_attachments", return_value=[]),
        patch("festival_organizer.mkv_attachments.tracked_run") as run,
    ):
        assert att.delete_all_image_attachments(target) == 0
    run.assert_not_called()


def test_delete_all_image_attachments_returns_minus_one_on_write_failure(tmp_path):
    target = tmp_path / "v.webm"
    target.touch()
    atts = [{"id": 1, "file_name": "cover.jpg", "content_type": "image/jpeg"}]
    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/usr/bin/mkvpropedit"),
        patch.object(att, "list_image_attachments", return_value=atts),
        patch(
            "festival_organizer.mkv_attachments.tracked_run",
            side_effect=lambda cmd, **k: _proc("", rc=2),
        ),
    ):
        assert att.delete_all_image_attachments(target) == -1
