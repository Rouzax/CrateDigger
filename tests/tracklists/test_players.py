from pathlib import Path

from festival_organizer.tracklists.api import PlayerInfo
from festival_organizer.tracklists.players import (
    partition_lines_by_player,
    select_player,
)

EXPORT = (Path(__file__).parent / "fixtures" / "multiplayer_export.txt").read_text()


def test_partition_splits_by_player_marker():
    lines = [line for line in EXPORT.split("\n") if line.strip()]
    parts = partition_lines_by_player(lines)
    # Player 1 block has exactly the three Repeat-It/Shape-Of-You lines
    p1 = parts[1]
    assert any("[00:01]" in line and "Repeat It" in line for line in p1)
    assert any("[03:17]" in line for line in p1)
    assert any("[33:40]" in line for line in p1)
    assert all("Catharina" not in line for line in p1)
    # Player 2 block has the opener and the closer, not the B2B tracks
    p2 = parts[2]
    assert any("Catharina" in line for line in p2)
    assert any("[2:14:27]" in line for line in p2)
    assert all("Shape Of You" not in line for line in p2)


def test_partition_no_markers_returns_single_bucket():
    lines = ["[00:00] A - B", "[01:00] C - D"]
    assert partition_lines_by_player(lines) == {0: lines}


PLAYERS = [
    PlayerInfo(1, "p-nL0FjuCPs", 2277),
    PlayerInfo(2, "v-e4wZutXY4", 8364),
]


def test_select_empty_players_returns_zero():
    assert select_player([], "anything", 1234.0) == 0


def test_select_by_youtube_id_exact():
    assert select_player(PLAYERS, "p-nL0FjuCPs", 9999.0) == 1
    assert select_player(PLAYERS, "v-e4wZutXY4", None) == 2


def test_select_by_duration_when_no_id():
    # 2276s file matches player 1 (2277s) within tolerance
    assert select_player(PLAYERS, None, 2276.0) == 1
    assert select_player(PLAYERS, "", 8300.0) == 2


def test_select_no_match_returns_none():
    # unknown id and a duration far from both sources
    assert select_player(PLAYERS, "zzzzzzzzzzz", 600.0) is None


def test_select_ambiguous_duration_returns_none():
    # two sources both within tolerance of the file duration -> refuse to guess
    near = [PlayerInfo(1, "aaaaaaaaaaa", 3600), PlayerInfo(2, "bbbbbbbbbbb", 3650)]
    assert select_player(near, None, 3620.0) is None
    # but an exact id match still wins even when durations are ambiguous
    assert select_player(near, "bbbbbbbbbbb", 3620.0) == 2
