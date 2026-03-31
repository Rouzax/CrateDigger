"""Tests for tracklist search result scoring."""
from festival_organizer.tracklists.scoring import (
    parse_query,
    score_results,
    remove_diacritics,
    get_abbreviation,
    SearchResult,
    QueryParts,
)


# --- remove_diacritics ---

def test_remove_diacritics_basic():
    assert remove_diacritics("Tiësto") == "Tiesto"
    assert remove_diacritics("Château") == "Chateau"
    assert remove_diacritics("Ibañez") == "Ibanez"


def test_remove_diacritics_no_change():
    assert remove_diacritics("Martin Garrix") == "Martin Garrix"


# --- get_abbreviation ---

def test_get_abbreviation_basic():
    assert get_abbreviation("Amsterdam Music Festival") == "AMF"
    assert get_abbreviation("Electric Daisy Carnival") == "EDC"


def test_get_abbreviation_single_word():
    assert get_abbreviation("Tomorrowland") is None


def test_get_abbreviation_lowercase():
    assert get_abbreviation("the small thing") is None


# --- parse_query ---

def test_parse_query_basic():
    aliases = {"amf": "Amsterdam Music Festival"}
    parts = parse_query("2025 AMF Sub Zero Project", aliases)
    assert parts.year == "2025"
    assert "AMF" in parts.abbreviations
    assert len(parts.resolved_aliases) == 1
    assert parts.resolved_aliases[0]["target"] == "Amsterdam Music Festival"
    assert "sub" in parts.keywords
    assert "zero" in parts.keywords
    assert "project" in parts.keywords


def test_parse_query_event_patterns():
    parts = parse_query("Hardwell WE1 Tomorrowland 2025", {})
    assert len(parts.event_patterns) == 1
    assert parts.event_patterns[0]["type"] == "Weekend"
    assert parts.event_patterns[0]["number"] == "1"
    assert parts.year == "2025"


def test_parse_query_day_pattern():
    parts = parse_query("Defqon D2 2025", {})
    assert len(parts.event_patterns) == 1
    assert parts.event_patterns[0]["type"] == "Day"
    assert parts.event_patterns[0]["number"] == "2"


def test_parse_query_strips_youtube_id():
    parts = parse_query("Artist Name [dQw4w9WgXcQ]", {})
    assert "dqw4w9wgxcq" not in " ".join(parts.keywords)
    assert "artist" in parts.keywords
    assert "name" in parts.keywords


def test_parse_query_no_short_words():
    parts = parse_query("DJ at an AMF", {})
    # "DJ" and "AMF" → abbreviations; "at", "an" are ≤2 chars → excluded
    assert len(parts.keywords) == 0


def test_parse_query_all_caps_produces_keywords():
    """ALL-CAPS queries (YouTube titles) should produce keywords, not just abbreviations."""
    aliases = {"umf": "Ultra Music Festival"}
    parts = parse_query("AFROJACK LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026", aliases)
    assert parts.year == "2026"
    # All-caps words should become keywords, not abbreviations
    assert "afrojack" in parts.keywords
    assert "live" in parts.keywords
    assert "ultra" in parts.keywords
    assert "festival" in parts.keywords
    assert "miami" in parts.keywords
    # Should NOT have spurious abbreviations from regular words
    assert "AFROJACK" not in parts.abbreviations
    assert "FESTIVAL" not in parts.abbreviations


def test_parse_query_all_caps_preserves_known_alias():
    """ALL-CAPS queries should still detect known alias abbreviations."""
    aliases = {"amf": "Amsterdam Music Festival"}
    parts = parse_query("AMF AFROJACK 2025", aliases)
    assert parts.year == "2025"
    # AMF is a known alias — should be abbreviation AND keyword
    assert "AMF" in parts.abbreviations
    assert len(parts.resolved_aliases) == 1
    assert parts.resolved_aliases[0]["target"] == "Amsterdam Music Festival"
    # AFROJACK is not a known alias — should be keyword only
    assert "afrojack" in parts.keywords
    assert "AFROJACK" not in parts.abbreviations


def test_parse_query_mixed_case_unchanged():
    """Mixed-case queries preserve existing abbreviation behavior."""
    aliases = {"amf": "Amsterdam Music Festival"}
    parts = parse_query("2025 AMF Sub Zero Project", aliases)
    # AMF → abbreviation (existing behavior)
    assert "AMF" in parts.abbreviations
    # Sub, Zero, Project → keywords (existing behavior)
    assert "sub" in parts.keywords
    assert "zero" in parts.keywords
    assert "project" in parts.keywords
    # Keywords should NOT include "amf" (mixed-case: abbreviations stay separate)
    assert "amf" not in parts.keywords


# --- score_results ---

def test_score_keywords_proportional():
    results = [
        SearchResult(id="1", title="Sub Zero Project @ Amsterdam Music Festival 2025", url=""),
        SearchResult(id="2", title="Random Artist @ Other Event", url=""),
    ]
    parts = parse_query("Sub Zero Project", {})
    scored = score_results(results, parts)
    # First result matches all 3 keywords, second matches none
    assert len(scored) == 1  # zero-keyword match filtered out
    assert scored[0].id == "1"
    assert scored[0].score > 0


def test_score_abbreviation_direct():
    results = [
        SearchResult(id="1", title="Artist @ AMF 2025", url=""),
    ]
    parts = QueryParts(abbreviations=["AMF"], keywords=["artist"])
    scored = score_results(results, parts)
    assert len(scored) == 1
    assert scored[0].has_event_match is True
    assert scored[0].score > 100  # keyword(100) + abbreviation(35) = 135 minimum


def test_score_abbreviation_derived():
    results = [
        SearchResult(id="1", title="Artist @ Amsterdam Music Festival 2025", url=""),
    ]
    parts = QueryParts(abbreviations=["AMF"], keywords=["artist"])
    scored = score_results(results, parts)
    assert scored[0].has_event_match is True


def test_score_alias_match():
    results = [
        SearchResult(id="1", title="Artist @ Tomorrowland Weekend 1 2025", url=""),
    ]
    parts = QueryParts(
        keywords=["artist"],
        resolved_aliases=[{"alias": "TML", "target": "Tomorrowland"}],
    )
    scored = score_results(results, parts)
    assert scored[0].has_event_match is True


def test_score_duration_multiplier_exact():
    results = [
        SearchResult(id="1", title="Artist @ Festival 2025", url="", duration_mins=62),
    ]
    parts = QueryParts(keywords=["artist"])
    scored = score_results(results, parts, video_duration_minutes=62)
    score_exact = scored[0].score

    results2 = [
        SearchResult(id="1", title="Artist @ Festival 2025", url="", duration_mins=120),
    ]
    scored2 = score_results(results2, parts, video_duration_minutes=62)
    score_far = scored2[0].score

    assert score_exact > score_far  # Exact match should score higher


def test_score_year_bonus():
    results = [
        SearchResult(id="1", title="Artist @ Festival", url="", date="2025-10-19"),
    ]
    parts = QueryParts(keywords=["artist"], year="2025")
    scored = score_results(results, parts)

    results2 = [
        SearchResult(id="1", title="Artist @ Festival", url="", date="2024-10-19"),
    ]
    parts2 = QueryParts(keywords=["artist"], year="2025")
    scored2 = score_results(results2, parts2)

    assert scored[0].score > scored2[0].score  # Year match gets +25 bonus


def test_score_event_pattern_correct_weekend():
    results = [
        SearchResult(id="1", title="Artist @ Tomorrowland Weekend 1 2025", url=""),
    ]
    parts = QueryParts(keywords=["artist"], event_patterns=[{"type": "Weekend", "number": "1"}])
    scored = score_results(results, parts)
    assert scored[0].score > 100  # Gets +40 pattern bonus


def test_score_event_pattern_wrong_weekend():
    results = [
        SearchResult(id="1", title="Artist @ Tomorrowland Weekend 2 2025", url=""),
    ]
    parts = QueryParts(keywords=["artist"], event_patterns=[{"type": "Weekend", "number": "1"}])
    scored = score_results(results, parts)
    # Gets -30 for wrong weekend, so lower than without pattern
    assert scored[0].score < 100


def test_filter_zero_keyword_matches():
    results = [
        SearchResult(id="1", title="Completely Different Title", url=""),
        SearchResult(id="2", title="Sub Zero Project @ AMF", url=""),
    ]
    parts = parse_query("Sub Zero Project", {})
    scored = score_results(results, parts)
    assert len(scored) == 1
    assert scored[0].id == "2"


def test_filter_low_relevance_with_event():
    results = [
        SearchResult(id="1", title="Sub Zero Project @ AMF 2025", url=""),
        SearchResult(id="2", title="Sub Random Other Track 2025", url=""),
    ]
    aliases = {"amf": "Amsterdam Music Festival"}
    parts = parse_query("2025 AMF Sub Zero Project", aliases)
    scored = score_results(results, parts)
    # Result 2 has only 1 keyword match ("sub") and no event match → filtered
    assert all(r.id != "2" for r in scored) or scored[-1].score < scored[0].score


def test_all_caps_query_scores_matching_results():
    """ALL-CAPS query should score and return matching results, not filter all out."""
    results = [
        SearchResult(id="1", title="AFROJACK @ Mainstage, Ultra Music Festival Miami, United States", url="", duration_mins=60, date="2026-03-29"),
        SearchResult(id="2", title="ZHU @ Live Stage, Ultra Music Festival Miami, United States", url="", duration_mins=58, date="2026-03-29"),
        SearchResult(id="3", title="Random DJ - Radio Show 123", url="", duration_mins=60, date="2026-01-01"),
    ]
    aliases = {"umf": "Ultra Music Festival"}
    parts = parse_query("AFROJACK LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026", aliases)
    scored = score_results(results, parts, video_duration_minutes=60)
    # Should NOT filter everything out
    assert len(scored) >= 2
    # AFROJACK result should score highest (matches artist + festival keywords)
    assert scored[0].id == "1"


def test_mixed_case_with_alias_still_filters_correctly():
    """Regression: mixed-case queries with aliases should keep strict filtering."""
    results = [
        SearchResult(id="1", title="Sub Zero Project @ Amsterdam Music Festival 2025", url=""),
        SearchResult(id="2", title="Sub Random Other Track 2025", url=""),
    ]
    aliases = {"amf": "Amsterdam Music Festival"}
    parts = parse_query("2025 AMF Sub Zero Project", aliases)
    scored = score_results(results, parts)
    # Result 1 should be present and highly scored
    assert any(r.id == "1" for r in scored)
    # Result 2 should be filtered or score much lower (only 1 keyword match "sub", no event)
    if any(r.id == "2" for r in scored):
        r1_score = next(r.score for r in scored if r.id == "1")
        r2_score = next(r.score for r in scored if r.id == "2")
        assert r1_score > r2_score
