from pathlib import Path

from festival_organizer.tracklists.players import partition_lines_by_player

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
