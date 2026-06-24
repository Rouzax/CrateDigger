from pathlib import Path

from festival_organizer.tracklists.api import PlayerInfo
from festival_organizer.tracklists.chapters import parse_tracklist_lines
from festival_organizer.tracklists.players import (
    partition_lines_by_player,
    select_player,
)

EXPORT = (Path(__file__).parent / "fixtures" / "multiplayer_export.txt").read_text()
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
