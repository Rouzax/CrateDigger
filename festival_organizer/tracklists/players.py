"""Per-source ("player") selection and line partitioning for multi-source
1001TL tracklists. Pure functions: no HTTP, no HTML parsing."""

from __future__ import annotations

import re

_PLAYER_MARKER = re.compile(r"^Player (\d+)$")


def partition_lines_by_player(lines: list[str]) -> dict[int, list[str]]:
    """Split export lines into per-player buckets keyed by ordinal.

    A bare ``Player N`` line switches the active ordinal. Lines before any
    marker fall under key 0. With no markers present, returns {0: lines}.
    """
    buckets: dict[int, list[str]] = {}
    current = 0
    saw_marker = False
    for line in lines:
        stripped = line.strip()
        m = _PLAYER_MARKER.match(stripped)
        if m:
            current = int(m.group(1))
            saw_marker = True
            buckets.setdefault(current, [])
            continue
        buckets.setdefault(current, []).append(line)
    if not saw_marker:
        return {0: lines}
    return buckets
