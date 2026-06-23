from pathlib import Path

from festival_organizer.tracklists.api import PlayerInfo, _parse_players

FIX = Path(__file__).parent / "fixtures" / "multiplayer_tracklist.html"


def test_parse_players_orders_sources_with_ytid_and_duration():
    players = _parse_players(FIX.read_text())
    assert [(p.ordinal, p.youtube_id, p.duration_seconds) for p in players] == [
        (1, "p-nL0FjuCPs", 2277),
        (2, "v-e4wZutXY4", 8364),
    ]


def test_parse_players_single_source_returns_one():
    # A single-source page has one ytPlayer block and no media tabs.
    html = (
        "<script>jsbuffer.push(['ready', function() { ytPlayer = new Object(); "
        'ytPlayer.idPlayer = "ABCdefGHIjk"; ytPlayer.cue = "0"; '
        'ytPlayer.source = "UC"; ytPlayer.duration = "3600"; }]);</script>'
    )
    assert _parse_players(html) == [PlayerInfo(1, "ABCdefGHIjk", 3600)]


def test_parse_players_no_youtube_source_returns_empty():
    assert _parse_players("<div>no players</div>") == []
