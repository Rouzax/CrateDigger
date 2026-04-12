"""Orchestration tests: embed_chapters builds per-chapter tag map and canonical names."""
from unittest.mock import patch, MagicMock
from festival_organizer.tracklists.chapters import (
    Chapter, _build_chapter_tags_map, embed_chapters,
)
from festival_organizer.tracklists.api import Track
from festival_organizer.tracklists.dj_cache import DjCache


def test_build_chapter_tags_map_matches_by_ms(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("afrojack", {"name": "Afrojack"})
    chapters = [
        Chapter(timestamp="00:00:00.000", title="Intro"),
        Chapter(timestamp="00:01:00.000", title="Second"),
    ]
    uids = [111, 222]
    tracks = [
        Track(start_ms=0, raw_text="AFROJACK - Take Over Control",
              artist_slugs=["afrojack"], genres=["House"]),
        Track(start_ms=60000, raw_text="Guest - Track",
              artist_slugs=["guest-artist"], genres=["Techno", "Tech House"]),
    ]
    result = _build_chapter_tags_map(chapters, uids, tracks, cache)
    assert result[111]["ARTIST"] == "Afrojack"
    assert result[111]["ARTIST_SLUGS"] == "afrojack"
    assert result[111]["GENRE"] == "House"
    assert result[222]["ARTIST"] == "guest-artist"  # fallback when not in cache
    assert result[222]["ARTIST_SLUGS"] == "guest-artist"
    assert result[222]["GENRE"] == "Techno|Tech House"


def test_build_chapter_tags_map_skips_unmatched(tmp_path):
    chapters = [Chapter(timestamp="00:01:00.000", title="Only one")]
    uids = [111]
    # Track has wrong timestamp
    tracks = [Track(start_ms=5000, raw_text="x", artist_slugs=["a"], genres=[])]
    result = _build_chapter_tags_map(chapters, uids, tracks, None)
    assert result == {}


def test_build_chapter_tags_map_no_dj_cache(tmp_path):
    chapters = [Chapter(timestamp="00:00:00.000", title="A")]
    uids = [111]
    tracks = [Track(start_ms=0, raw_text="x", artist_slugs=["foo"], genres=["House"])]
    result = _build_chapter_tags_map(chapters, uids, tracks, None)
    assert result[111]["ARTIST"] == "foo"  # no cache, fall back to slug
    assert result[111]["GENRE"] == "House"


def test_build_chapter_tags_map_empty_tracks_omits_uid(tmp_path):
    chapters = [Chapter(timestamp="00:00:00.000", title="A")]
    uids = [111]
    tracks = [Track(start_ms=0, raw_text="x", artist_slugs=[], genres=[])]
    result = _build_chapter_tags_map(chapters, uids, tracks, None)
    assert result == {}  # nothing useful to say


def test_build_chapter_tags_map_pairs_by_index(tmp_path):
    """chapters[i] must pair with uids[i]."""
    chapters = [
        Chapter(timestamp="00:00:00.000", title="A"),
        Chapter(timestamp="00:02:00.000", title="B"),
    ]
    uids = [111, 222]
    tracks = [
        Track(start_ms=0, raw_text="x", artist_slugs=["a"], genres=[]),
        Track(start_ms=120000, raw_text="y", artist_slugs=["b"], genres=[]),
    ]
    result = _build_chapter_tags_map(chapters, uids, tracks, None)
    assert result[111]["ARTIST"] == "a"
    assert result[222]["ARTIST"] == "b"


def test_embed_chapters_canonical_artists_tag(tmp_path):
    """CRATEDIGGER_1001TL_ARTISTS uses DjCache canonical names, not display_name."""
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("afrojack", {"name": "Afrojack"})  # canonical titlecase
    # dj_artists tuple: slug, raw 1001TL display text (upper case)
    dj_artists = [("afrojack", "AFROJACK")]

    # Build a fake MKV so embed_chapters doesn't bail on the extension check
    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")

    # mock mkvpropedit path so embed_chapters attempts the calls
    with patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"), \
         patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write, \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_write.return_value = True
        embed_chapters(
            fake_mkv,
            chapters=[],
            tracklist_url="https://x",
            dj_artists=dj_artists,
            dj_cache=cache,
        )
        # Verify the tags dict passed to write_merged_tags has canonical name
        call_args = mock_write.call_args
        tags_payload = call_args[0][1]  # second positional arg
        assert tags_payload[70]["CRATEDIGGER_1001TL_ARTISTS"] == "Afrojack"


def test_embed_chapters_without_dj_cache_uses_display_name(tmp_path):
    """Backwards compat: no dj_cache means no canonical rewrite."""
    dj_artists = [("afrojack", "AFROJACK")]
    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")
    with patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"), \
         patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write, \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_write.return_value = True
        embed_chapters(
            fake_mkv,
            chapters=[],
            tracklist_url="https://x",
            dj_artists=dj_artists,
            # no dj_cache
        )
        tags_payload = mock_write.call_args[0][1]
        assert tags_payload[70]["CRATEDIGGER_1001TL_ARTISTS"] == "AFROJACK"
