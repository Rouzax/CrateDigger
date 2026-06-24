from pathlib import Path
from unittest.mock import MagicMock, patch

from festival_organizer.tracklists.api import (
    PlayerInfo,
    TracklistExport,
    _parse_tracks,
)
from festival_organizer.tracklists.chapters import parse_tracklist_lines
from festival_organizer.tracklists.cli_handler import _fetch_and_embed
from festival_organizer.tracklists.players import (
    partition_lines_by_player,
    select_player,
)

EXPORT = (Path(__file__).parent / "fixtures" / "multiplayer_export.txt").read_text(
    encoding="utf-8"
)
MULTIPLAYER_HTML = (
    Path(__file__).parent / "fixtures" / "multiplayer_tracklist.html"
).read_text(encoding="utf-8")
PLAYERS = [PlayerInfo(1, "p-nL0FjuCPs", 2277), PlayerInfo(2, "v-e4wZutXY4", 8364)]


def test_player1_file_gets_only_b2b_chapters():
    lines = [line for line in EXPORT.split("\n") if line.strip()]
    ordinal = select_player(PLAYERS, "p-nL0FjuCPs", 2276.0)
    assert ordinal == 1
    selected = partition_lines_by_player(lines)[ordinal]
    chapters = parse_tracklist_lines(selected)
    titles = [c.title for c in chapters]
    secs = [c.timestamp for c in chapters]
    assert all("Catharina" not in t for t in titles)
    assert any("Repeat It" in t for t in titles)
    # monotonic, within the 37:56 file
    assert secs == sorted(secs)
    assert secs[0].startswith("00:00:01")


# --- Direct integration coverage for _fetch_and_embed multi-source glue ---
#
# The tests above exercise the selection helpers in isolation. The two below
# drive the real glue in cli_handler._fetch_and_embed end to end with a stubbed
# session and a mocked embed_chapters, so the wiring (select_player ->
# partition_lines_by_player -> parse_tracklist_lines -> embed_chapters) is
# covered, not just its parts.


def _make_multiplayer_export() -> TracklistExport:
    """Build a two-source export from the shared multiplayer fixtures.

    Lines come from multiplayer_export.txt (the "Player N" headers drive
    partitioning); tracks are parsed from multiplayer_tracklist.html so each
    Track carries its real .player ordinal and start_ms.
    """
    lines = [line for line in EXPORT.split("\n") if line.strip()]
    tracks = _parse_tracks(MULTIPLAYER_HTML)
    return TracklistExport(
        lines=lines,
        url="https://www.1001tracklists.com/tracklist/abc/martin-garrix.html",
        title="Martin Garrix @ Americas Tour",
        genres=["Big Room"],
        dj_artists=[("martin-garrix", "Martin Garrix")],
        tracks=tracks,
        players=PLAYERS,
    )


def _make_session(export: TracklistExport) -> MagicMock:
    sess = MagicMock()
    sess.export_tracklist.return_value = export
    sess._dj_cache = None  # _fetch_and_embed only forwards this to embed_chapters
    return sess


def _make_config() -> MagicMock:
    cfg = MagicMock()
    cfg.tracklists_settings = {"genre_top_n": 5}
    cfg.resolve_artist = lambda name: name
    return cfg


def test_fetch_and_embed_matched_multisource_embeds_player1_block(tmp_path):
    """(a) MATCHED multi-source: a file whose id/duration matches Player 1 must
    chapter ONLY the Player-1 B2B block (Repeat It...), never the Player-2
    Catharina opener, and persist Player 1's youtube_id."""
    export = _make_multiplayer_export()
    session = _make_session(export)
    config = _make_config()

    captured: dict = {}

    def fake_embed(filepath, chapters, **kwargs):
        captured["chapters"] = chapters
        captured["youtube_id"] = kwargs.get("youtube_id")
        captured["tracks"] = kwargs.get("tracks")
        return True

    # A real on-disk file: extract_existing_chapters reads it, but we patch
    # that and embed_chapters so no mkvpropedit / real I/O runs.
    fake_mkv = tmp_path / "martin-garrix.mkv"
    fake_mkv.write_bytes(b"")

    with (
        patch(
            "festival_organizer.tracklists.cli_handler.embed_chapters",
            side_effect=fake_embed,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.extract_existing_chapters",
            return_value=None,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.chapters_are_identical",
            return_value=False,
        ),
    ):
        status, vstatus, _ = _fetch_and_embed(
            session,
            export.url,
            fake_mkv,
            config,
            preview=False,
            quiet=True,
            language="eng",
            duration_seconds=2276,  # within tolerance of Player 1 (2277s)
            youtube_id="p-nL0FjuCPs",
        )

    assert status == "updated"
    assert vstatus == "updated"
    # embed_chapters got the Player-1 block only.
    titles = [c.title for c in captured["chapters"]]
    timestamps = [c.timestamp for c in captured["chapters"]]
    assert captured["chapters"], "expected a non-empty chapter list"
    assert timestamps[0].startswith("00:00:01")
    assert any("Repeat It" in t for t in titles)
    assert all("Catharina" not in t for t in titles)
    # Source id persisted is Player 1's.
    assert captured["youtube_id"] == "p-nL0FjuCPs"
    # Tracks were scoped to Player 1 as well.
    assert captured["tracks"]
    assert all(t.player == 1 for t in captured["tracks"])


def test_fetch_and_embed_no_match_multisource_skips_without_erasing(tmp_path):
    """(b) NO-MATCH multi-source: an unknown id and a duration matching neither
    source must warn-and-skip, returning ('skipped', 'skipped', 'no matching
    player'). embed_chapters, if called, gets an EMPTY chapter list so existing
    chapters are preserved (no erase)."""
    export = _make_multiplayer_export()
    session = _make_session(export)
    config = _make_config()

    captured: dict = {}

    def fake_embed(filepath, chapters, **kwargs):
        captured["chapters"] = chapters
        return True

    fake_mkv = tmp_path / "unknown.mkv"
    fake_mkv.write_bytes(b"")

    with (
        patch(
            "festival_organizer.tracklists.cli_handler.embed_chapters",
            side_effect=fake_embed,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.extract_existing_chapters",
            return_value=None,
        ),
        patch(
            "festival_organizer.tracklists.cli_handler.chapters_are_identical",
            return_value=False,
        ),
    ):
        result = _fetch_and_embed(
            session,
            export.url,
            fake_mkv,
            config,
            preview=False,
            quiet=True,
            language="eng",
            duration_seconds=600,  # matches neither 2277s nor 8364s
            youtube_id="",
        )

    assert result == ("skipped", "skipped", "no matching player")
    # The no-match branch metadata-tags the file but passes [] so chapters are
    # left intact (warn-and-skip, not erase).
    assert "chapters" in captured, "embed_chapters should still write metadata"
    assert captured["chapters"] == []
