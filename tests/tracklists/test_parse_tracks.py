from pathlib import Path
from festival_organizer.tracklists.api import _parse_tracks

FIXTURE = Path(__file__).parent / "fixtures" / "afrojack_edc_2025.html"


def test_parse_tracks_returns_chapter_aligned_rows_only():
    """HTML has 77 tlpItem rows but only ~27-30 are chapter-aligned."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    assert 24 <= len(tracks) <= 35


def test_parse_tracks_extracts_slugs():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    # First track is AFROJACK - Take Over Control; its slug is 'afrojack'.
    assert tracks[0].artist_slugs
    assert tracks[0].artist_slugs[0] == "afrojack"
    # At least 80% of chapter-aligned rows have at least one slug
    with_slugs = [t for t in tracks if t.artist_slugs]
    assert len(with_slugs) >= int(len(tracks) * 0.8)


def test_parse_tracks_extracts_genres_from_chapter_rows():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    all_genres = [g for t in tracks for g in t.genres]
    assert len(all_genres) >= 5


def test_parse_tracks_start_ms_monotonic():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    starts = [t.start_ms for t in tracks]
    assert starts == sorted(starts)


def test_parse_tracks_first_chapter_at_zero():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    assert tracks[0].start_ms == 0


def test_parse_tracks_raw_text_preserved():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    assert "Take Over Control" in tracks[0].raw_text


def test_parse_tracks_no_mojibake():
    """After the 1e45b59 fix, no parsed text should contain mojibake bytes."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    for t in tracks:
        assert "\u251c" not in t.raw_text, f"mojibake in {t.raw_text!r}"
        for g in t.genres:
            assert "\u251c" not in g
