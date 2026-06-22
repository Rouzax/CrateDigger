from pathlib import Path

from festival_organizer.models import MediaFile


def test_mediafile_has_artist_slugs_default():
    mf = MediaFile(source_path=Path("x.mkv"))
    assert mf.artist_slugs == []
