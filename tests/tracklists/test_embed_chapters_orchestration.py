"""Orchestration tests: the album-level tags embed_chapters writes (artists, album artist, location)."""

from unittest.mock import MagicMock, patch

from festival_organizer.mkv_tags import CLEAR_TAG
from festival_organizer.tracklists.chapters import embed_chapters
from festival_organizer.tracklists.dj_cache import DjCache


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
    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"),
        patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write,
        patch("subprocess.run") as mock_run,
    ):
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


def test_embed_chapters_writes_albumartist_display_and_slugs(tmp_path):
    """ALBUMARTIST_DISPLAY and ALBUMARTIST_SLUGS are written alongside 1001TL_ARTISTS
    and stay positionally aligned (canonical names joined with ' & ', slugs with '|')."""
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("arminvanbuuren", {"name": "Armin van Buuren"})
    cache.put("kislashki", {"name": "KI/KI"})
    dj_artists = [("arminvanbuuren", "ARMIN VAN BUUREN"), ("kislashki", "KI/KI")]

    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")

    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"),
        patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write,
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_write.return_value = True
        embed_chapters(
            fake_mkv,
            chapters=[],
            tracklist_url="https://x",
            dj_artists=dj_artists,
            dj_cache=cache,
        )
        tags = mock_write.call_args[0][1][70]
        assert tags["CRATEDIGGER_1001TL_ARTISTS"] == "Armin van Buuren|KI/KI"
        assert tags["CRATEDIGGER_ALBUMARTIST_SLUGS"] == "arminvanbuuren|kislashki"
        assert tags["CRATEDIGGER_ALBUMARTIST_DISPLAY"] == "Armin van Buuren & KI/KI"


def test_embed_chapters_single_artist_writes_length_1_albumartist_tags(tmp_path):
    """Single-artist sets still emit all three tags with one slot each."""
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("afrojack", {"name": "Afrojack"})
    dj_artists = [("afrojack", "AFROJACK")]

    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")

    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"),
        patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write,
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_write.return_value = True
        embed_chapters(
            fake_mkv,
            chapters=[],
            tracklist_url="https://x",
            dj_artists=dj_artists,
            dj_cache=cache,
        )
        tags = mock_write.call_args[0][1][70]
        assert tags["CRATEDIGGER_1001TL_ARTISTS"] == "Afrojack"
        assert tags["CRATEDIGGER_ALBUMARTIST_SLUGS"] == "afrojack"
        assert tags["CRATEDIGGER_ALBUMARTIST_DISPLAY"] == "Afrojack"


def test_embed_chapters_without_dj_cache_uses_display_name(tmp_path):
    """Backwards compat: no dj_cache means no canonical rewrite."""
    dj_artists = [("afrojack", "AFROJACK")]
    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")
    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"),
        patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write,
        patch("subprocess.run") as mock_run,
    ):
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


def test_embed_chapters_writes_location_when_no_linked_source(tmp_path):
    """CRATEDIGGER_1001TL_LOCATION is written when there's no linked
    location-bearing source (Festival / Venue / Conference / Radio).
    This is the lowest-tier fallback derived from the 1001TL h1 tail.
    """
    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")

    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"),
        patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write,
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_write.return_value = True
        embed_chapters(
            fake_mkv,
            chapters=[],
            tracklist_url="https://x",
            location="Alexandra Palace London",
            sources_by_type={},
        )
        tags = mock_write.call_args[0][1][70]
        assert tags["CRATEDIGGER_1001TL_LOCATION"] == "Alexandra Palace London"


def test_embed_chapters_clears_location_when_linked_venue_present(tmp_path):
    """When a linked location-bearing source (e.g. Event Location -> VENUE)
    is present, any stale CRATEDIGGER_1001TL_LOCATION must be cleared.

    This is the cleanup path: a file previously enriched with LOCATION is
    now being re-identified against a tracklist that carries a linked venue,
    so LOCATION should no longer apply. The clear must trigger even when
    the passed-in location is the empty string (the prior-work suppression
    rule in export_tracklist already blanks it, but the file may still have
    a stale value on disk).
    """
    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")

    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"),
        patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write,
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_write.return_value = True
        embed_chapters(
            fake_mkv,
            chapters=[],
            tracklist_url="https://x",
            location="",
            sources_by_type={"Event Location": ["Alexandra Palace"]},
        )
        tags = mock_write.call_args[0][1][70]
        assert tags["CRATEDIGGER_1001TL_LOCATION"] is CLEAR_TAG
        # The linked venue is still written normally
        assert tags["CRATEDIGGER_1001TL_VENUE"] == "Alexandra Palace"


def test_embed_chapters_clears_location_when_festival_present(tmp_path):
    """When location is empty and a festival source is present, LOCATION
    is cleared by the blanket managed-tag sweep while FESTIVAL is set."""
    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")

    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"),
        patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write,
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_write.return_value = True
        embed_chapters(
            fake_mkv,
            chapters=[],
            tracklist_url="https://x",
            location="",
            sources_by_type={"Open Air / Festival": ["Tomorrowland"]},
        )
        tags = mock_write.call_args[0][1][70]
        assert tags["CRATEDIGGER_1001TL_LOCATION"] is CLEAR_TAG
        assert tags["CRATEDIGGER_1001TL_FESTIVAL"] == "Tomorrowland"


def test_embed_chapters_clears_location_when_empty_and_no_linked_source(tmp_path):
    """When location is empty AND no linked source is present, the blanket
    managed-tag sweep sets LOCATION to CLEAR_TAG so any stale value from a
    prior identification is removed.
    """
    fake_mkv = tmp_path / "x.mkv"
    fake_mkv.write_bytes(b"")

    with (
        patch("festival_organizer.metadata.MKVPROPEDIT_PATH", "/bin/true"),
        patch("festival_organizer.tracklists.chapters.write_merged_tags") as mock_write,
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_write.return_value = True
        embed_chapters(
            fake_mkv,
            chapters=[],
            tracklist_url="https://x",
            location="",
            sources_by_type={},
        )
        tags = mock_write.call_args[0][1][70]
        assert tags["CRATEDIGGER_1001TL_LOCATION"] is CLEAR_TAG
