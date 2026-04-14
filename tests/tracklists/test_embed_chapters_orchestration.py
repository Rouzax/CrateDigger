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
        Track(start_ms=0, raw_text="AFROJACK ft. Eva Simons - Take Over Control",
              artist_slugs=["afrojack"], genres=["House"]),
        Track(start_ms=60000, raw_text="Guest & Someone - Track",
              artist_slugs=["guest-artist", "someone"], genres=["Techno", "Tech House"]),
    ]
    result = _build_chapter_tags_map(chapters, uids, tracks, cache)
    assert result[111]["CRATEDIGGER_TRACK_PERFORMER"] == "AFROJACK ft. Eva Simons"
    assert result[111]["CRATEDIGGER_TRACK_PERFORMER_SLUGS"] == "afrojack"
    assert result[111]["CRATEDIGGER_TRACK_GENRE"] == "House"
    assert result[222]["CRATEDIGGER_TRACK_PERFORMER"] == "Guest & Someone"
    assert result[222]["CRATEDIGGER_TRACK_PERFORMER_SLUGS"] == "guest-artist|someone"
    assert result[222]["CRATEDIGGER_TRACK_GENRE"] == "Techno|Tech House"


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
    tracks = [Track(start_ms=0, raw_text="Artist Name - Some Title",
                    artist_slugs=["artist-slug"], genres=["House"])]
    result = _build_chapter_tags_map(chapters, uids, tracks, None)
    # PERFORMER comes from raw_text prefix; DjCache is not consulted for it.
    assert result[111]["CRATEDIGGER_TRACK_PERFORMER"] == "Artist Name"
    assert result[111]["CRATEDIGGER_TRACK_GENRE"] == "House"


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
        Track(start_ms=0, raw_text="Artist A - Song A", artist_slugs=["a"], genres=[]),
        Track(start_ms=120000, raw_text="Artist B - Song B", artist_slugs=["b"], genres=[]),
    ]
    result = _build_chapter_tags_map(chapters, uids, tracks, None)
    assert result[111]["CRATEDIGGER_TRACK_PERFORMER"] == "Artist A"
    assert result[222]["CRATEDIGGER_TRACK_PERFORMER"] == "Artist B"


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


def test_embed_chapters_writes_albumartist_display_and_slugs(tmp_path):
    """ALBUMARTIST_DISPLAY and ALBUMARTIST_SLUGS are written alongside 1001TL_ARTISTS
    and stay positionally aligned (canonical names joined with ' & ', slugs with '|')."""
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("arminvanbuuren", {"name": "Armin van Buuren"})
    cache.put("kislashki", {"name": "KI/KI"})
    dj_artists = [("arminvanbuuren", "ARMIN VAN BUUREN"), ("kislashki", "KI/KI")]

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
        tags = mock_write.call_args[0][1][70]
        assert tags["CRATEDIGGER_1001TL_ARTISTS"] == "Afrojack"
        assert tags["CRATEDIGGER_ALBUMARTIST_SLUGS"] == "afrojack"
        assert tags["CRATEDIGGER_ALBUMARTIST_DISPLAY"] == "Afrojack"


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


def test_performer_preserves_full_display_line_from_raw_text(tmp_path):
    """PERFORMER is the raw_text prefix (everything before the final ' - ')."""
    chapters = [Chapter(timestamp="00:00:00.000", title="Intro")]
    uids = [111]
    tracks = [Track(
        start_ms=0,
        raw_text="Fred again.. & Jamie T - Lights Burn Dimmer (Tiësto Remix)",
        artist_slugs=["fred-again..", "jamie-t", "tiesto"],
        genres=[],
    )]
    result = _build_chapter_tags_map(chapters, uids, tracks, None, None)
    # Full display artist line, multi-artist preserved, no drop.
    assert result[111]["CRATEDIGGER_TRACK_PERFORMER"] == "Fred again.. & Jamie T"
    assert result[111]["CRATEDIGGER_TRACK_PERFORMER_SLUGS"] == "fred-again..|jamie-t|tiesto"


def test_performer_handles_mashup_composite_display():
    """Mashup rows put the full composite artist string before the ' - '."""
    chapters = [Chapter(timestamp="00:00:00.000", title="x")]
    uids = [111]
    tracks = [Track(
        start_ms=0,
        raw_text=("NLW & MureKian vs. Ivan Gough & Feenixpawl & Georgi Kay vs. "
                  "RÜFÜS DU SOL - Loco vs. In My Mind vs. Innerbloom (AFROJACK Mashup)"),
        artist_slugs=["nlw-murekian-vs-ivan-gough-feenixpawl-georgi-kay-vs-rufus-du-sol", "afrojack"],
        genres=[],
    )]
    result = _build_chapter_tags_map(chapters, uids, tracks, None, None)
    assert result[111]["CRATEDIGGER_TRACK_PERFORMER"] == (
        "NLW & MureKian vs. Ivan Gough & Feenixpawl & Georgi Kay vs. RÜFÜS DU SOL"
    )


def test_performer_preserves_1001tl_display_form_not_alias():
    """Per-chapter PERFORMER keeps the 1001TL display form; alias resolution
    (e.g. SOMETHING ELSE -> ALOK) is only applied to the top-level ARTIST
    tag for filesystem routing, NOT to per-chapter tags which document what
    the DJ / crowd knows the track as."""
    aliases = {"SOMETHING ELSE": "ALOK"}
    def resolver(name: str) -> str:
        return aliases.get(name, name)
    chapters = [Chapter(timestamp="00:00:00.000", title="x")]
    uids = [111]
    tracks = [Track(
        start_ms=0,
        raw_text="SOMETHING ELSE - Ignite",
        artist_slugs=["somethingelse-br"],
        genres=[],
    )]
    result = _build_chapter_tags_map(chapters, uids, tracks, None, resolver)
    # Display form preserved. ALOK would only be correct for filesystem
    # routing (top-level ARTIST tag handled elsewhere).
    assert result[111]["CRATEDIGGER_TRACK_PERFORMER"] == "SOMETHING ELSE"


def test_chapter_tags_include_title_and_label():
    """TITLE and LABEL are emitted when the track carries them."""
    chapters = [Chapter(timestamp="00:00:00.000", title="x")]
    uids = [111]
    tracks = [Track(
        start_ms=0,
        raw_text="AFROJACK ft. Eva Simons - Take Over Control",
        artist_slugs=["afrojack"],
        genres=[],
        title="Take Over Control",
        label="WALL",
    )]
    result = _build_chapter_tags_map(chapters, uids, tracks, None, None)
    assert result[111]["TITLE"] == "Take Over Control"
    assert result[111]["CRATEDIGGER_TRACK_LABEL"] == "WALL"


def test_chapter_tags_omit_title_and_label_when_empty():
    """TITLE and LABEL omitted when track fields are empty strings."""
    chapters = [Chapter(timestamp="00:00:00.000", title="x")]
    uids = [111]
    tracks = [Track(
        start_ms=0,
        raw_text="Artist - Song",
        artist_slugs=["slug"],
        genres=[],
        title="",
        label="",
    )]
    result = _build_chapter_tags_map(chapters, uids, tracks, None, None)
    assert "TITLE" not in result[111]
    assert "CRATEDIGGER_TRACK_LABEL" not in result[111]
