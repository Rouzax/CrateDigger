from festival_organizer.normalization import (
    safe_filename,
    normalise_name,
    strip_scene_tags,
    strip_noise_words,
    extract_youtube_id,
    scene_dots_to_spaces,
    fix_mojibake,
)


# --- fix_mojibake ---

def test_fix_mojibake_empty():
    assert fix_mojibake("") == ""


def test_fix_mojibake_idempotent_on_clean_text():
    assert fix_mojibake("Kölsch") == "Kölsch"


def test_fix_mojibake_latin1_double_encoded():
    assert fix_mojibake("KÃ¶lsch") == "Kölsch"


def test_fix_mojibake_preserves_diacritics():
    # Tiësto should survive unchanged
    assert fix_mojibake("Tiësto") == "Tiësto"


def test_fix_mojibake_french_accent():
    assert fix_mojibake("Ã©dition") == "édition"


def test_fix_mojibake_plain_ascii():
    assert fix_mojibake("plain ascii") == "plain ascii"


def test_safe_filename_removes_illegal_chars():
    assert safe_filename('Artist: The "Best" <Live>') == "Artist The Best Live"
    assert safe_filename("KI\u2044KI") == "KIKI"  # fraction slash U+2044


def test_safe_filename_collapses_whitespace():
    assert safe_filename("Artist   Name") == "Artist Name"


def test_safe_filename_strips_trailing_dots():
    assert safe_filename("Name...") == "Name"


def test_safe_filename_truncates_long_names():
    long_name = "A" * 250
    assert len(safe_filename(long_name)) <= 200


def test_normalise_name_trims_separators():
    assert normalise_name("  - Artist Name - ") == "Artist Name"
    assert normalise_name("") == ""


def test_strip_scene_tags():
    assert strip_scene_tags("Coldplay A Head Full of Dreams 2018 1080p AMZN WEB-DL DDP5 1 H 264-NTG") == "Coldplay A Head Full of Dreams 2018"
    assert strip_scene_tags("glastonbury 2016 coldplay 720p hdtv x264-verum") == "glastonbury 2016 coldplay"


def test_strip_scene_tags_preserves_content():
    assert strip_scene_tags("Martin Garrix LIVE @ AMF 2024") == "Martin Garrix LIVE @ AMF 2024"


def test_strip_noise_words():
    assert "Full Set" not in strip_noise_words("Martin Garrix Full Set")
    assert "Live Set" not in strip_noise_words("Tiësto Live Set")
    assert "DJ Set" not in strip_noise_words("Artist Full DJ Set")
    assert "Official" not in strip_noise_words("Official Stream")


def test_strip_noise_words_preserves_live_at():
    """'LIVE' before 'at' should NOT be stripped (it's a valid naming pattern)."""
    result = strip_noise_words("Dimitri Vegas Live At Tomorrowland 2024")
    assert "Live" in result
    assert "Tomorrowland" in result


def test_strip_noise_words_strips_live_before_at_sign():
    """'LIVE' before '@' should still be stripped (noise in LIVE @ format)."""
    result = strip_noise_words("Martin Garrix LIVE @ AMF 2024")
    assert "LIVE" not in result


def test_extract_youtube_id():
    stem, yt_id = extract_youtube_id("Armin van Buuren live at EDC Las Vegas 2025 [Dp7AwrAKckQ]")
    assert yt_id == "Dp7AwrAKckQ"
    assert "[Dp7AwrAKckQ]" not in stem
    assert stem.strip() == "Armin van Buuren live at EDC Las Vegas 2025"

    stem2, yt_id2 = extract_youtube_id("No ID here")
    assert yt_id2 == ""
    assert stem2 == "No ID here"


def test_scene_dots_to_spaces():
    assert scene_dots_to_spaces("glastonbury.2016.coldplay.1080p.hdtv.x264-verum") == "glastonbury 2016 coldplay 1080p hdtv x264-verum"
    # Should NOT convert when there are few dots (not scene-style)
    assert scene_dots_to_spaces("Defqon.1") == "Defqon.1"
    # Should NOT convert when there are already spaces
    assert scene_dots_to_spaces("Artist Name - Festival 2024") == "Artist Name - Festival 2024"
