"""Tests for tracklist search result scoring."""

from festival_organizer.tracklists.scoring import (
    AliasGroup,
    QueryParts,
    SearchResult,
    get_abbreviation,
    parse_query,
    remove_diacritics,
    score_results,
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
    # "DJ" (2 chars) → excluded; "at", "an" (≤2 chars) → excluded
    # "AMF" is not a known alias → keyword (3 chars passes filter)
    assert parts.keywords == ["amf"]


def test_parse_query_all_caps_produces_keywords():
    """ALL-CAPS queries: non-alias words become keywords; alias-value words become alias groups."""
    aliases = {"umf": "Ultra Music Festival"}
    parts = parse_query("AFROJACK LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026", aliases)
    assert parts.year == "2026"
    # Non-alias words should become keywords
    assert "afrojack" in parts.keywords
    assert "live" in parts.keywords
    assert "miami" in parts.keywords
    # Alias-value words should be in alias_groups, not keywords
    assert "ultra" not in parts.keywords
    assert "festival" not in parts.keywords
    assert len(parts.alias_groups) == 1
    assert parts.alias_groups[0].abbreviation == "umf"
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


def test_parse_query_mixed_case_unknown_caps_become_keywords():
    """Unknown all-caps words in mixed-case queries should be keywords, not abbreviations."""
    aliases = {"edc": "Electric Daisy Carnival"}
    parts = parse_query("MARTIN GARRIX Americas Tour 2026", aliases)
    assert "martin" in parts.keywords
    assert "garrix" in parts.keywords
    assert "americas" in parts.keywords
    assert "tour" in parts.keywords
    assert "MARTIN" not in parts.abbreviations
    assert "GARRIX" not in parts.abbreviations


def test_parse_query_post_expansion_caps_become_keywords():
    """After alias expansion, alias-value words become an alias group; remaining caps are keywords."""
    aliases = {"edc": "Electric Daisy Carnival"}
    parts = parse_query("FISHER Electric Daisy Carnival LAS VEGAS 2025", aliases)
    assert "fisher" in parts.keywords
    assert "las" in parts.keywords
    assert "vegas" in parts.keywords
    # Alias value words are now in alias_groups, not keywords
    assert "electric" not in parts.keywords
    assert "daisy" not in parts.keywords
    assert "carnival" not in parts.keywords
    assert len(parts.alias_groups) == 1
    assert parts.alias_groups[0].abbreviation == "edc"


def test_parse_query_mixed_case_known_alias_stays_abbreviation():
    """Known aliases in mixed-case queries remain abbreviations (not keywords)."""
    aliases = {"amf": "Amsterdam Music Festival"}
    parts = parse_query("Fisher AMF 2025", aliases)
    assert "AMF" in parts.abbreviations
    assert "amf" not in parts.keywords
    assert "fisher" in parts.keywords


# --- parse_query alias groups ---


def test_parse_query_detects_alias_group_from_expansion():
    """Expanded 'Electric Daisy Carnival' should become an alias group, not 3 keywords."""
    aliases = {"edc": "Electric Daisy Carnival"}
    parts = parse_query(
        "ZEDD @ Electric Daisy Carnival Las Vegas 2026 kineticFIELD 2K", aliases
    )
    assert parts.year == "2026"
    assert len(parts.alias_groups) == 1
    assert parts.alias_groups[0].abbreviation == "edc"
    assert parts.alias_groups[0].full_name == "Electric Daisy Carnival"
    assert parts.alias_groups[0].keywords == ["electric", "daisy", "carnival"]
    assert "electric" not in parts.keywords
    assert "daisy" not in parts.keywords
    assert "carnival" not in parts.keywords
    assert "zedd" in parts.keywords
    assert "las" in parts.keywords
    assert "vegas" in parts.keywords
    assert "kineticfield" in parts.keywords


def test_parse_query_detects_alias_group_all_caps():
    """Full alias name in ALL-CAPS query should be detected as alias group."""
    aliases = {"umf": "Ultra Music Festival"}
    parts = parse_query("AFROJACK LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026", aliases)
    assert len(parts.alias_groups) == 1
    assert parts.alias_groups[0].abbreviation == "umf"
    assert parts.alias_groups[0].keywords == ["ultra", "music", "festival"]
    assert "ultra" not in parts.keywords
    assert "music" not in parts.keywords
    assert "festival" not in parts.keywords
    assert "afrojack" in parts.keywords
    assert "miami" in parts.keywords


def test_parse_query_skips_single_word_alias_values():
    """Single-word alias values should NOT produce alias groups."""
    aliases = {"tml": "Tomorrowland"}
    parts = parse_query("Hardwell Tomorrowland 2025", aliases)
    assert len(parts.alias_groups) == 0
    assert "tomorrowland" in parts.keywords


def test_parse_query_no_alias_group_when_no_match():
    """Alias values not present in query should not produce alias groups."""
    aliases = {"edc": "Electric Daisy Carnival"}
    parts = parse_query("Hardwell Tomorrowland 2025", aliases)
    assert len(parts.alias_groups) == 0
    assert "hardwell" in parts.keywords
    assert "tomorrowland" in parts.keywords


def test_parse_query_alias_group_longest_match_first():
    """When two aliases overlap, the longest should be matched first."""
    aliases = {
        "umf": "Ultra Music Festival",
        "umfm": "Ultra Music Festival Miami",
    }
    parts = parse_query("Zedd Ultra Music Festival Miami 2026", aliases)
    assert len(parts.alias_groups) == 1
    assert parts.alias_groups[0].abbreviation == "umfm"
    assert parts.alias_groups[0].keywords == ["ultra", "music", "festival", "miami"]
    assert "miami" not in parts.keywords


# --- score_results ---


def test_score_keywords_proportional():
    results = [
        SearchResult(
            id="1", title="Sub Zero Project @ Amsterdam Music Festival 2025", url=""
        ),
        SearchResult(id="2", title="Random Artist @ Other Event", url=""),
    ]
    parts = parse_query("Sub Zero Project", {})
    scored = score_results(results, parts)
    # First result matches all 3 keywords, second matches none
    assert len(scored) == 1  # zero-keyword match filtered out
    assert scored[0].id == "1"
    assert scored[0].score > 0


def test_score_all_keywords_good_duration_reaches_plus():
    """All keywords matched + duration within 5m + year match should score 250+."""
    results = [
        SearchResult(
            id="1",
            title="Swedish House Mafia @ Creamfields 2025",
            url="",
            duration_mins=63,
            date="2025-07-25",
        ),
    ]
    parts = QueryParts(
        keywords=["swedish", "house", "mafia", "creamfields"], year="2025"
    )
    scored = score_results(results, parts, video_duration_minutes=60)
    assert scored[0].score >= 250, (
        f"Perfect match with good duration should reach '+' (got {scored[0].score:.0f})"
    )


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
    parts = QueryParts(
        keywords=["artist"], event_patterns=[{"type": "Weekend", "number": "1"}]
    )
    scored = score_results(results, parts)
    assert scored[0].score > 100  # Gets +40 pattern bonus


def test_score_event_pattern_wrong_weekend():
    wrong = [SearchResult(id="1", title="Artist @ Tomorrowland Weekend 2 2025", url="")]
    correct = [
        SearchResult(id="2", title="Artist @ Tomorrowland Weekend 1 2025", url="")
    ]
    parts = QueryParts(
        keywords=["artist", "tomorrowland"],
        event_patterns=[{"type": "Weekend", "number": "1"}],
    )
    wrong_scored = score_results(wrong, parts)
    correct_scored = score_results(correct, parts)
    assert wrong_scored[0].score < correct_scored[0].score


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
        SearchResult(
            id="1",
            title="AFROJACK @ Mainstage, Ultra Music Festival Miami, United States",
            url="",
            duration_mins=60,
            date="2026-03-29",
        ),
        SearchResult(
            id="2",
            title="ZHU @ Live Stage, Ultra Music Festival Miami, United States",
            url="",
            duration_mins=58,
            date="2026-03-29",
        ),
        SearchResult(
            id="3",
            title="Random DJ - Radio Show 123",
            url="",
            duration_mins=60,
            date="2026-01-01",
        ),
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
        SearchResult(
            id="1", title="Sub Zero Project @ Amsterdam Music Festival 2025", url=""
        ),
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


def test_duration_multiplier_never_penalizes():
    """Duration multiplier should never go below 1.0 (no penalty for mismatch)."""
    result = SearchResult(
        id="test", title="Test Set @ Festival", url="/test/", duration_mins=30
    )
    query_parts = QueryParts(keywords=["test", "festival"])

    # Score with large duration mismatch (video=120min, result=30min)
    score_results([result], query_parts, video_duration_minutes=120)
    score_with_mismatch = result.score

    # Score with no duration info
    result2 = SearchResult(
        id="test2", title="Test Set @ Festival", url="/test2/", duration_mins=None
    )
    score_results([result2], query_parts, video_duration_minutes=120)
    score_no_duration = result2.score

    # Mismatched duration should not score LOWER than no duration
    assert score_with_mismatch >= score_no_duration


def test_all_match_bonus_beats_partial_with_close_duration():
    """A result matching all keywords should outscore a partial match with closer duration."""
    # Simulates Eric Prydz (all 4 kw, 118min) vs Adriatique (2/4 kw, 91min) with 90min video
    full_match = SearchResult(
        id="full",
        title="Eric Prydz @ Resistance Megastructure, Ultra Music Festival",
        url="/f/",
        duration_mins=118,
    )
    partial_match = SearchResult(
        id="partial",
        title="Adriatique @ Resistance Megastructure, Ultra Music Festival",
        url="/p/",
        duration_mins=91,
    )

    query_parts = QueryParts(keywords=["eric", "prydz", "resistance", "megastructure"])
    results = score_results(
        [full_match, partial_match], query_parts, video_duration_minutes=90
    )

    assert results[0].id == "full", (
        "Full keyword match should rank higher despite worse duration"
    )


def test_multi_word_event_pattern():
    """'WEEKEND 2' (two words) should be detected as a Weekend event pattern."""
    aliases = {}
    qp = parse_query("HARDWELL TOMORROWLAND 2024 MAINSTAGE WEEKEND 2", aliases)
    assert any(p["type"] == "Weekend" and p["number"] == "2" for p in qp.event_patterns)


# --- alias group scoring ---


def test_score_alias_group_matches_abbreviation_in_title():
    """Alias group should match when title contains the abbreviation."""
    result = SearchResult(
        id="1",
        title="Zedd @ kineticFIELD, EDC Las Vegas",
        url="",
        duration_mins=68,
        date="2026-05-17",
    )
    parts = QueryParts(
        keywords=["zedd", "las", "vegas", "kineticfield"],
        alias_groups=[
            AliasGroup(
                "edc", "Electric Daisy Carnival", ["electric", "daisy", "carnival"]
            )
        ],
        year="2026",
    )
    scored = score_results([result], parts, video_duration_minutes=67)
    assert scored[0].has_event_match is True
    assert scored[0].matched_keyword_count == 7  # 4 regular + 3 alias


def test_score_alias_group_matches_full_name_in_title():
    """Alias group should match when title contains the full name."""
    result = SearchResult(
        id="1", title="Zedd @ kineticFIELD, Electric Daisy Carnival Las Vegas", url=""
    )
    parts = QueryParts(
        keywords=["zedd", "las", "vegas", "kineticfield"],
        alias_groups=[
            AliasGroup(
                "edc", "Electric Daisy Carnival", ["electric", "daisy", "carnival"]
            )
        ],
    )
    scored = score_results([result], parts)
    assert scored[0].has_event_match is True
    assert scored[0].matched_keyword_count == 7


def test_score_alias_group_no_match():
    """Alias group should not match when title has neither form."""
    result = SearchResult(id="1", title="Zedd @ Tomorrowland Mainstage", url="")
    parts = QueryParts(
        keywords=["zedd", "tomorrowland"],
        alias_groups=[
            AliasGroup(
                "edc", "Electric Daisy Carnival", ["electric", "daisy", "carnival"]
            )
        ],
    )
    scored = score_results([result], parts)
    assert scored[0].has_event_match is False
    assert (
        scored[0].matched_keyword_count == 2
    )  # "zedd" + "tomorrowland", no alias contribution


def test_score_alias_group_triggers_all_keywords_bonus():
    """When all regular keywords AND alias group match, the all-keywords bonus should trigger."""
    all_match = SearchResult(
        id="full",
        title="Zedd @ kineticFIELD, EDC Las Vegas, United States",
        url="",
        duration_mins=68,
    )
    partial_match = SearchResult(
        id="partial",
        title="Hardwell @ kineticFIELD, EDC Las Vegas, United States",
        url="",
        duration_mins=68,
    )

    parts = QueryParts(
        keywords=["zedd", "las", "vegas", "kineticfield"],
        alias_groups=[
            AliasGroup(
                "edc", "Electric Daisy Carnival", ["electric", "daisy", "carnival"]
            )
        ],
    )
    scored = score_results([all_match, partial_match], parts, video_duration_minutes=67)

    assert scored[0].id == "full"
    assert (
        scored[0].matched_keyword_count == 7
    )  # all keywords + alias = all-match bonus
    assert (
        scored[1].matched_keyword_count == 6
    )  # 3 regular + 3 alias = no all-match bonus
    assert scored[0].score > scored[1].score + 50  # decisive gap from +80 bonus


def test_zedd_outscores_hardwell_with_expanded_edc():
    """Regression: Zedd should rank above Hardwell when query expands EDC.

    The original bug: expand_aliases_in_query turns 'EDC' into 'Electric Daisy Carnival',
    creating 3 phantom keywords that never match 1001TL titles (which use 'EDC').
    This diluted keyword ratios and let scoring biases flip the correct ordering.
    """
    aliases = {"edc": "Electric Daisy Carnival"}
    query = "ZEDD @ Electric Daisy Carnival Las Vegas 2026 kineticFIELD 2K"
    parts = parse_query(query, aliases)

    results = [
        SearchResult(
            id="hardwell",
            title="Hardwell @ kineticFIELD, EDC Las Vegas, United States",
            url="",
            duration_mins=68,
            date="2026-05-16",
        ),
        SearchResult(
            id="zedd",
            title="Zedd @ kineticFIELD, EDC Las Vegas, United States",
            url="",
            duration_mins=68,
            date="2026-05-17",
        ),
    ]

    scored = score_results(results, parts, video_duration_minutes=67)
    assert scored[0].id == "zedd", (
        f"Zedd should rank #1 but got {scored[0].id} (scores: {scored[0].score:.0f} vs {scored[1].score:.0f})"
    )
    assert scored[0].score > scored[1].score + 20, "Zedd should have a decisive lead"


def test_filter_with_alias_group_event_context():
    """Alias groups should enable has_event_context, filtering low-relevance results."""
    results = [
        SearchResult(
            id="1", title="Zedd @ kineticFIELD, EDC Las Vegas, United States", url=""
        ),
        SearchResult(id="2", title="Random Vegas DJ Mix 2026", url=""),
    ]
    parts = QueryParts(
        keywords=["zedd", "las", "vegas", "kineticfield"],
        alias_groups=[
            AliasGroup(
                "edc", "Electric Daisy Carnival", ["electric", "daisy", "carnival"]
            )
        ],
    )
    scored = score_results(results, parts)
    result_ids = [r.id for r in scored]
    assert "1" in result_ids
    # Result 2 matches only "vegas" (1 keyword) with no event match
    # With has_event_context from alias_groups, it should be filtered
    assert "2" not in result_ids, (
        "Low-relevance result should be filtered with alias group event context"
    )


def test_auto_select_threshold_separates_good_from_bad():
    """Auto-select requires both minimum score AND minimum gap to #2."""
    from festival_organizer.tracklists.cli_handler import (
        AUTO_SELECT_MIN_GAP,
        AUTO_SELECT_MIN_SCORE,
    )

    strong = SearchResult(
        id="s",
        title="Hardwell @ Mainstage, Tomorrowland Weekend 2",
        url="/s/",
        duration_mins=90,
    )
    partial = SearchResult(
        id="p", title="Hardwell @ Some Other Festival", url="/p/", duration_mins=90
    )

    query_parts = QueryParts(keywords=["hardwell", "tomorrowland", "mainstage"])
    query_parts.event_patterns = [{"type": "Weekend", "number": "2"}]

    scored = score_results([strong, partial], query_parts, video_duration_minutes=90)

    assert scored[0].score >= AUTO_SELECT_MIN_SCORE, (
        f"Strong match ({scored[0].score:.0f}) should pass score threshold"
    )
    gap = scored[0].score - scored[1].score
    assert gap >= AUTO_SELECT_MIN_GAP, f"Gap ({gap:.0f}) should pass gap threshold"


def test_auto_select_rejects_narrow_gap():
    """Auto-select should skip when #1 and #2 are too close, even if score is high."""
    from festival_organizer.tracklists.cli_handler import AUTO_SELECT_MIN_GAP

    # Two results with near-identical scores (same keywords match both)
    r1 = SearchResult(
        id="r1",
        title="AFROJACK @ Mainstage, Ultra Music Festival Miami",
        url="/1/",
        duration_mins=60,
    )
    r2 = SearchResult(
        id="r2",
        title="Martin Garrix & Alesso @ Mainstage, Ultra Music Festival Miami",
        url="/2/",
        duration_mins=60,
    )

    query_parts = QueryParts(
        keywords=["ultra", "music", "festival", "miami", "mainstage"]
    )
    scored = score_results([r1, r2], query_parts, video_duration_minutes=60)

    gap = scored[0].score - scored[1].score
    assert gap < AUTO_SELECT_MIN_GAP, (
        f"Near-identical results should have gap ({gap:.0f}) below threshold"
    )


def test_dj_cache_does_not_distort_ranking():
    """A cached DJ name on a wrong result must not outrank the correct result.

    Regression: Cosmic Gate query ranked Peggy Gou first when 'peggy gou'
    was in the DJ cache but 'cosmic gate' was not, because the +25 cache
    bonus (amplified by the duration multiplier) closed the keyword gap.
    """
    parts = parse_query(
        "Cosmic Gate Live at Electric Daisy Carnival Las Vegas 2026",
        {"edc": "Electric Daisy Carnival"},
    )
    correct = SearchResult(
        id="cg",
        title="Cosmic Gate @ quantumVALLEY, EDC Las Vegas, United States",
        url="/t/",
        duration_mins=59,
        date="2026-05-15",
    )
    wrong = SearchResult(
        id="pg",
        title="Peggy Gou & KI/KI @ circuitGROUNDS, EDC Las Vegas, United States",
        url="/t/",
        duration_mins=60,
        date="2026-05-16",
    )
    scored = score_results([wrong, correct], parts, video_duration_minutes=59)
    assert scored[0].id == "cg"
