"""Per-source ("player") selection and line partitioning for multi-source
1001TL tracklists. Pure functions: no HTTP, no HTML parsing."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from festival_organizer.tracklists.api import PlayerInfo

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


def select_player(
    players: list[PlayerInfo],
    youtube_id: str | None,
    duration_s: float | None,
    duration_tolerance: float = 0.03,
) -> int | None:
    """Match a downloaded file to its source ordinal.

    Priority: exact YouTube-id match, then a *unique* video-duration match
    within ``duration_tolerance`` (fraction of the source duration).
    Returns 0 only when ``players`` is empty (no YouTube source); otherwise
    the matched ordinal, or None when sources exist but none matches OR the
    duration match is ambiguous (2+ sources within tolerance). We refuse to
    guess: an ambiguous duration is treated as no match.

    This is pure matching, used for two things: (1) selecting which source's
    timeline to chapter, which the caller applies ONLY when the tracklist is
    multi-source (``len(players) >= 2``); (2) deciding which source id to
    persist, applied for any ``len(players) >= 1`` when a match is found.
    """
    if not players:
        return 0
    if youtube_id:
        for p in players:
            if p.youtube_id and p.youtube_id == youtube_id:
                return p.ordinal
    if duration_s is not None:
        within = [
            (abs(p.duration_seconds - duration_s), p.ordinal)
            for p in players
            if p.duration_seconds > 0
            and abs(p.duration_seconds - duration_s)
            <= p.duration_seconds * duration_tolerance
        ]
        if len(within) == 1:
            return within[0][1]
        # 0 within tolerance -> no match; 2+ -> ambiguous, refuse to guess
    return None
