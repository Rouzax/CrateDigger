from festival_organizer.tracklists.api import Track, top_genres_by_frequency


def _track(genres):
    return Track(start_ms=0, raw_text="x", artist_slugs=[], genres=genres)


def test_top_genres_counts_per_track_occurrences():
    tracks = [
        _track(["House"]),
        _track(["House", "Tech House"]),
        _track(["Techno"]),
        _track(["House"]),
    ]
    result = top_genres_by_frequency(tracks, n=5)
    assert result[0] == "House"
    assert set(result) == {"House", "Tech House", "Techno"}


def test_top_genres_respects_n():
    tracks = [_track([f"G{i}"]) for i in range(10)]
    result = top_genres_by_frequency(tracks, n=3)
    assert len(result) == 3


def test_top_genres_ties_broken_by_first_appearance():
    tracks = [_track(["B"]), _track(["A"]), _track(["B"]), _track(["A"])]
    result = top_genres_by_frequency(tracks, n=5)
    assert result == ["B", "A"]


def test_top_genres_empty():
    assert top_genres_by_frequency([], n=5) == []


def test_top_genres_skips_blank():
    tracks = [_track(["", "House", ""])]
    assert top_genres_by_frequency(tracks, n=5) == ["House"]
