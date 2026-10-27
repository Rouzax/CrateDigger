"""Deezer client: artist lookup and telling a real photo from a stand-in.

A Deezer artist without a photo shows either a blank placeholder or one of
their own release covers. Both read as a picture to the API, so the poster
would show a grey outline or an album sleeve as the artist.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from festival_organizer import deezer
from festival_organizer.deezer import DeezerError, deezer_artist, photo_url

PHOTO_ID = "e71e56891f8a5bf21c9b78ce31d70a8c"
COVER_ID = "c7d03c6e214671a4543a2d264a96fa17"


def _picture(image_id: str) -> str:
    return f"https://cdn-images.dzcdn.net/images/artist/{image_id}/1000x1000-000000-80-0-0.jpg"


def _cover(image_id: str) -> str:
    return f"https://cdn-images.dzcdn.net/images/cover/{image_id}/1000x1000-000000-80-0-0.jpg"


def _resp(body: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


def _albums(*cover_ids: str) -> MagicMock:
    return _resp({"data": [{"cover_xl": _cover(i)} for i in cover_ids]})


@pytest.fixture(autouse=True)
def _no_sleep():
    with patch("festival_organizer.deezer.time.sleep") as sleep:
        yield sleep


def test_photo_url_accepts_a_real_photo():
    artist = {"id": 145050, "picture_xl": _picture(PHOTO_ID)}
    with patch(
        "festival_organizer.deezer.requests.get", return_value=_albums(COVER_ID)
    ):
        assert photo_url(artist) == _picture(PHOTO_ID)


def test_photo_url_rejects_md5_blank():
    artist = {
        "id": 259396492,
        "picture_xl": _picture("d41d8cd98f00b204e9800998ecf8427e"),
    }
    with patch("festival_organizer.deezer.requests.get") as get:
        assert photo_url(artist) == ""
    get.assert_not_called()


def test_photo_url_rejects_empty_id():
    artist = {
        "id": 1,
        "picture_xl": "https://cdn-images.dzcdn.net/images/artist//1000x1000-000000-80-0-0.jpg",
    }
    with patch("festival_organizer.deezer.requests.get") as get:
        assert photo_url(artist) == ""
    get.assert_not_called()


def test_photo_url_rejects_a_release_cover():
    # Bart Skils: Deezer serves the cover of one of his releases as his picture.
    artist = {"id": 468677, "picture_xl": _picture(COVER_ID)}
    with patch(
        "festival_organizer.deezer.requests.get",
        return_value=_albums(PHOTO_ID, COVER_ID),
    ):
        assert photo_url(artist) == ""


def test_photo_url_asks_for_up_to_100_releases():
    artist = {"id": 145050, "picture_xl": _picture(PHOTO_ID)}
    with patch("festival_organizer.deezer.requests.get", return_value=_albums()) as get:
        photo_url(artist)
    assert get.call_args.args[0] == "https://api.deezer.com/artist/145050/albums"
    assert get.call_args.kwargs["params"] == {"limit": 100}


def test_deezer_error_object_raises():
    quota = _resp(
        {"error": {"type": "Exception", "message": "Quota limit exceeded", "code": 4}}
    )
    with patch("festival_organizer.deezer.requests.get", return_value=quota):
        with pytest.raises(DeezerError):
            deezer_artist(145050)


def test_http_error_raises():
    bad_gateway = _resp({}, 502)
    bad_gateway.raise_for_status.side_effect = requests.HTTPError("502 Bad Gateway")
    with patch("festival_organizer.deezer.requests.get", return_value=bad_gateway):
        with pytest.raises(DeezerError):
            deezer_artist(145050)


def test_unknown_artist_is_none():
    gone = _resp(
        {"error": {"type": "DataException", "message": "no data", "code": 800}}
    )
    with patch("festival_organizer.deezer.requests.get", return_value=gone):
        assert deezer_artist(999999999) is None


def test_deezer_artist_returns_the_artist():
    body = {"id": 145050, "name": "Argy", "nb_fan": 15163}
    with patch(
        "festival_organizer.deezer.requests.get", return_value=_resp(body)
    ) as get:
        assert deezer_artist(145050) == body
    assert get.call_args.args[0] == "https://api.deezer.com/artist/145050"


def test_calls_are_throttled(_no_sleep):
    deezer._last_request = 0.0
    with patch("festival_organizer.deezer.requests.get", return_value=_resp({"id": 1})):
        deezer_artist(1)
        deezer_artist(1)
    waits = [c.args[0] for c in _no_sleep.call_args_list]
    assert waits and all(0 < w <= 0.2 for w in waits)
