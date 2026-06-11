from festival_organizer.models import MediaFile
from pathlib import Path


def test_mediafile_has_artist_slugs_default():
    mf = MediaFile(source_path=Path("x.mkv"))
    assert mf.artist_slugs == []
