"""Tests for the last-chapter overrun check in identify."""

from festival_organizer.tracklists.api import Track
from festival_organizer.tracklists.cli_handler import _tail_overrun
from festival_organizer.tracklists.overlays import AssembledChapter


def _chapter(
    start_ms: int, duration_ms: int, *, as_primary: bool = True
) -> AssembledChapter:
    track = Track(
        start_ms=start_ms,
        raw_text="Artist - Title",
        artist_slugs=[],
        genres=[],
        duration_ms=duration_ms,
    )
    if as_primary:
        return AssembledChapter(start_ms=start_ms, title="", primary=track)
    return AssembledChapter(
        start_ms=start_ms, title="", primary=None, contributors=[track]
    )


def test_last_chapter_far_longer_than_its_track_is_reported():
    # Guetta AMF 2026 before trimming: "Without You" (5:08) cued at 87:20 in a
    # 103:20 video, because the video carried a 12-minute intro.
    chapters = [_chapter(0, 0), _chapter(5_240_000, 308_000)]
    assert _tail_overrun(chapters, 6199.8) == (959, 308)


def test_last_chapter_with_ordinary_outro_is_not_reported():
    chapters = [_chapter(5_240_000, 308_000)]
    assert _tail_overrun(chapters, 5_240 + 308 + 120) is None


def test_unknown_release_length_is_not_reported():
    chapters = [_chapter(5_240_000, 0)]
    assert _tail_overrun(chapters, 6199.8) is None


def test_breakout_last_chapter_uses_its_lead_track():
    chapters = [_chapter(5_240_000, 308_000, as_primary=False)]
    assert _tail_overrun(chapters, 6199.8) == (959, 308)


def test_no_chapters_or_unknown_media_length_is_not_reported():
    assert _tail_overrun([], 6199.8) is None
    assert _tail_overrun([_chapter(5_240_000, 308_000)], None) is None
