"""NFO group-member expansion via slug-keyed DJ cache lookup."""
import xml.etree.ElementTree as ET
from pathlib import Path

from festival_organizer.models import MediaFile
from festival_organizer.config import load_config
from festival_organizer.nfo import generate_nfo
from festival_organizer.tracklists.dj_cache import DjCache


def _parse_nfo(nfo_path: Path) -> ET.Element:
    return ET.fromstring(nfo_path.read_text(encoding="utf-8"))


def test_nfo_group_members_via_slug(tmp_path):
    """Group members resolve through the file's album-artist slug.

    The group entry carries a directly captured ``members`` list, so
    ``derive_group_members()`` returns ``{"aboveandbeyond": [...]}``. The
    MediaFile's ``artist_slugs`` line up with ``artists`` so the slug path
    matches exactly and the full lineup is emitted as ``<tag>`` elements.
    """
    dj_cache = DjCache(tmp_path / "dj_cache.json")
    dj_cache.put("aboveandbeyond", {
        "name": "Above & Beyond", "artwork_url": "",
        "aliases": [], "member_of": [],
        "members": [
            {"slug": "jonogrant", "name": "Jono Grant"},
            {"slug": "tonymcguinness", "name": "Tony McGuinness"},
        ],
    })
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Above & Beyond",
        artists=["Above & Beyond"],
        artist_slugs=["aboveandbeyond"],
        festival="Tomorrowland", year="2024",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config(), dj_cache=dj_cache))
    tags = [t.text for t in root.findall("tag")]
    assert "Above & Beyond" in tags
    assert "Jono Grant" in tags
    assert "Tony McGuinness" in tags


def test_nfo_group_members_graceful_without_slugs(tmp_path):
    """Older files with no album-artist slugs degrade gracefully.

    With ``artist_slugs=[]`` there is no slug to resolve, and the cache has
    no key matching the artist name, so no members are expanded. The artist's
    own name tag is still emitted and generation does not crash.
    """
    dj_cache = DjCache(tmp_path / "dj_cache.json")
    dj_cache.put("aboveandbeyond", {
        "name": "Above & Beyond", "artwork_url": "",
        "aliases": [], "member_of": [],
        "members": [
            {"slug": "jonogrant", "name": "Jono Grant"},
        ],
    })
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Above & Beyond",
        artists=["Above & Beyond"],
        artist_slugs=[],
        festival="Tomorrowland", year="2024",
        content_type="festival_set",
    )
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    root = _parse_nfo(generate_nfo(mf, video, load_config(), dj_cache=dj_cache))
    tags = [t.text for t in root.findall("tag")]
    assert "Above & Beyond" in tags
    assert "Jono Grant" not in tags
