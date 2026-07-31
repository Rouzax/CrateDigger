"""Byte-parity net: synthesized lines vs real export_data.php output.

Each fixture pair holds a tracklist page and the real export API response
captured at the same moment (2026-07-31, before the API was retired from
the pipeline). Synthesis must reproduce the export's timed rows exactly:
same player buckets, same second, same visible text including qualifiers
and the joined [Label] suffix.

Timestamps compare at second granularity because the export renders
minute-precision-friendly forms ("[02:25]", "[2:14:27]") while synthesis
emits HH:MM:SS.mmm; both parse to the same seconds value.
"""

import re
from pathlib import Path

import pytest

from festival_organizer.tracklists.api import _parse_tracks, _synthesize_export_lines
from festival_organizer.tracklists.players import partition_lines_by_player

FIXTURES = Path(__file__).parent / "fixtures" / "paired"
PAIR_IDS = ["1pn8l919", "2wrmg6f1", "2wtsw119"]

_TS_RE = re.compile(r"^\s*\[([0-9:.]+)\]\s*(.+?)\s*$")


def _ts_seconds(ts: str) -> int:
    total = 0
    for part in ts.split(":"):
        total = total * 60 + int(float(part))
    return total


def _timed_rows(lines: list[str]) -> list[tuple[int, int, str]]:
    """(player, seconds, text) for every timed line, via the real partitioner."""
    rows = []
    for player, bucket in sorted(partition_lines_by_player(lines).items()):
        for line in bucket:
            m = _TS_RE.match(line)
            if m:
                rows.append((player, _ts_seconds(m.group(1)), m.group(2)))
    return rows


@pytest.mark.parametrize("pair_id", PAIR_IDS)
def test_synthesized_lines_match_real_export(pair_id):
    html = (FIXTURES / f"{pair_id}.html").read_text(encoding="utf-8")
    export_raw = (FIXTURES / f"{pair_id}.export.txt").read_text(encoding="utf-8")

    export_lines = [ln for ln in export_raw.split("\n") if ln.strip()]
    synthesized = _synthesize_export_lines(_parse_tracks(html))

    assert _timed_rows(synthesized) == _timed_rows(export_lines)


@pytest.mark.parametrize("pair_id", PAIR_IDS)
def test_synthesized_player_buckets_match_export(pair_id):
    html = (FIXTURES / f"{pair_id}.html").read_text(encoding="utf-8")
    export_raw = (FIXTURES / f"{pair_id}.export.txt").read_text(encoding="utf-8")

    export_lines = [ln for ln in export_raw.split("\n") if ln.strip()]
    synthesized = _synthesize_export_lines(_parse_tracks(html))

    exp_buckets = {
        p: len([ln for ln in b if _TS_RE.match(ln)])
        for p, b in partition_lines_by_player(export_lines).items()
        if any(_TS_RE.match(ln) for ln in b)
    }
    syn_buckets = {
        p: len([ln for ln in b if _TS_RE.match(ln)])
        for p, b in partition_lines_by_player(synthesized).items()
        if any(_TS_RE.match(ln) for ln in b)
    }
    assert syn_buckets == exp_buckets
