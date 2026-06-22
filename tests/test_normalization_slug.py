from festival_organizer.normalization import folder_slug, slugify


def test_slugify_matches_1001tl_style():
    assert slugify("Above & Beyond") == "aboveandbeyond"
    assert slugify("Tiësto") == "tiesto"
    assert slugify("Kölsch") == "kolsch"
    assert slugify("Cosmic Gate") == "cosmicgate"
    assert slugify("Fred again..") == "fredagain"
    assert slugify("Fred again") == "fredagain"


def test_slugify_empty_is_empty():
    assert slugify("") == ""
    assert slugify("   ") == ""


def test_folder_slug_strips_trailing_dots_and_spaces():
    # Windows cannot hold a dir named "fredagain.."
    assert folder_slug("fredagain..") == "fredagain"
    assert folder_slug("aboveandbeyond") == "aboveandbeyond"
    assert folder_slug("tiesto") == "tiesto"
