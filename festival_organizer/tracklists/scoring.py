"""Search result scoring for 1001Tracklists — multiplicative model.

Scores search results by combining content relevance with duration matching.
Ported from Add-TracklistChapters PowerShell Get-RelevanceScore.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class QueryParts:
    """Parsed components of a search query."""
    year: str | None = None
    keywords: list[str] = field(default_factory=list)        # lowercase, len > 2
    abbreviations: list[str] = field(default_factory=list)    # uppercase 2+ chars
    event_patterns: list[dict] = field(default_factory=list)  # [{"type": "Weekend"|"Day", "number": str}]
    resolved_aliases: list[dict] = field(default_factory=list) # [{"alias": str, "target": str}]


@dataclass
class SearchResult:
    """A single search result from 1001Tracklists."""
    id: str
    title: str
    url: str
    duration_mins: int | None = None
    date: str | None = None
    score: float = 0.0
    matched_keyword_count: int = 0
    has_event_match: bool = False


def remove_diacritics(text: str) -> str:
    """Remove diacritics/accents for robust matching. Tiësto → Tiesto, Château → Chateau."""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def get_abbreviation(text: str) -> str | None:
    """Extract abbreviation from multi-word text (first letter of each capitalized word).

    "Amsterdam Music Festival" → "AMF"
    Requires ≥2 words starting with uppercase.
    """
    words = text.split()
    caps = [w[0] for w in words if w and w[0].isupper()]
    if len(caps) >= 2:
        return "".join(caps)
    return None


def parse_query(query: str, aliases: dict[str, str]) -> QueryParts:
    """Parse a search query into components for scoring.

    Args:
        query: search string (e.g. "2025 AMF Sub Zero Project")
        aliases: lowercase-keyed alias map (e.g. {"amf": "Amsterdam Music Festival"})

    Returns:
        QueryParts with extracted year, keywords, abbreviations, event patterns, resolved aliases
    """
    parts = QueryParts()

    # Strip YouTube ID from end
    query = re.sub(r"\s*\[[A-Za-z0-9_-]{11}\]\s*$", "", query)

    words = query.split()
    remaining = []

    # Detect all-caps query (YouTube title convention)
    alpha_words = [w for w in words if re.match(r"^[A-Za-z]{2,}$", w)]
    all_caps_query = len(alpha_words) > 1 and all(w.isupper() for w in alpha_words)

    for word in words:
        # Year detection
        if re.match(r"^(19|20)\d{2}$", word):
            parts.year = word
            continue

        # Event patterns: WE1, W2, Weekend1, D1, Day2
        we_match = re.match(r"(?i)^(?:WE|W|Weekend)(\d+)$", word)
        if we_match:
            parts.event_patterns.append({"type": "Weekend", "number": we_match.group(1)})
            continue

        day_match = re.match(r"(?i)^(?:D|Day)(\d+)$", word)
        if day_match:
            parts.event_patterns.append({"type": "Day", "number": day_match.group(1)})
            continue

        # Abbreviation detection: exactly 2+ uppercase letters, no lowercase
        if re.match(r"^[A-Z]{2,}$", word):
            lower = word.lower()
            is_known_alias = lower in aliases

            if all_caps_query:
                # All-caps query: only known aliases are treated as abbreviations
                if is_known_alias:
                    parts.abbreviations.append(word)
                    parts.resolved_aliases.append({"alias": word, "target": aliases[lower]})
                # Always also a keyword candidate in all-caps mode
                remaining.append(word)
                continue
            else:
                # Mixed-case query: existing behavior — all uppercase words are abbreviations
                parts.abbreviations.append(word)
                if is_known_alias:
                    parts.resolved_aliases.append({"alias": word, "target": aliases[lower]})
                continue

        # Alias check (case-insensitive)
        lower = word.lower()
        if lower in aliases:
            parts.resolved_aliases.append({"alias": word, "target": aliases[lower]})

        remaining.append(word)

    # Keywords: words > 2 chars, lowercased, with diacritics removed
    for word in remaining:
        cleaned = remove_diacritics(word).lower()
        if len(cleaned) > 2:
            parts.keywords.append(cleaned)

    return parts


def score_results(
    results: list[SearchResult],
    query_parts: QueryParts,
    video_duration_minutes: int = 0,
) -> list[SearchResult]:
    """Score, filter, and sort search results.

    Scoring model:
      final = (content_score × duration_multiplier) + year_bonus + recency_bonus

    Filtering:
      1. Remove zero-keyword matches
      2. If query has aliases/abbreviations, remove results with ≤1 keyword and no event match

    Returns filtered list sorted by score descending.
    """
    if not results:
        return []

    # Compute date range for recency scoring
    dates = []
    for r in results:
        if r.date:
            try:
                dates.append(datetime.strptime(r.date, "%Y-%m-%d"))
            except ValueError:
                pass

    min_date = min(dates) if dates else None
    date_range_days = (max(dates) - min(dates)).days if len(dates) >= 2 else 0.0

    # Score each result
    for r in results:
        _compute_score(r, query_parts, video_duration_minutes, min_date, date_range_days)

    # Filter
    has_event_context = bool(query_parts.abbreviations or query_parts.resolved_aliases)

    filtered = []
    for r in results:
        # Always remove zero-keyword matches
        if r.matched_keyword_count == 0:
            continue
        # If query has event context, remove low-relevance results
        if has_event_context and r.matched_keyword_count <= 1 and not r.has_event_match:
            continue
        filtered.append(r)

    # Sort by score descending
    filtered.sort(key=lambda r: r.score, reverse=True)
    return filtered


def _compute_score(
    result: SearchResult,
    query_parts: QueryParts,
    video_duration_minutes: int,
    min_date: datetime | None,
    date_range_days: float,
) -> None:
    """Compute and set score fields on a single SearchResult."""
    title_normalized = remove_diacritics(result.title).lower()

    # --- Content score ---
    content_score = 0.0

    # 1. Keywords (0-120)
    total_keywords = len(query_parts.keywords)
    if total_keywords > 0:
        matched = sum(1 for kw in query_parts.keywords if kw in title_normalized)
        result.matched_keyword_count = matched
        keyword_score = (matched / total_keywords) * 100
        if matched == total_keywords:
            keyword_score += 20  # All-match bonus
        content_score += min(keyword_score, 120)

    # 2. Abbreviations (+35 each)
    for abbrev in query_parts.abbreviations:
        abbrev_upper = abbrev.upper()
        # Direct match in title
        if re.search(r"\b" + re.escape(abbrev_upper) + r"\b", result.title, re.IGNORECASE):
            content_score += 35
            result.has_event_match = True
            continue
        # Derived abbreviation from title segments
        for segment in re.split(r"[@,]", result.title):
            derived = get_abbreviation(segment.strip())
            if derived and derived.upper() == abbrev_upper:
                content_score += 35
                result.has_event_match = True
                break

    # 3. Aliases (+35 each)
    for alias_info in query_parts.resolved_aliases:
        target_normalized = remove_diacritics(alias_info["target"]).lower()
        if target_normalized in title_normalized:
            content_score += 35
            result.has_event_match = True

    # 4. Event patterns (±40)
    for pattern in query_parts.event_patterns:
        ptype = pattern["type"]
        pnum = pattern["number"]

        if ptype == "Weekend":
            correct_re = rf"(?i)(?:weekend\s*{pnum}|w{pnum}|we{pnum})"
            wrong_re = rf"(?i)(?:weekend\s*\d|w\d|we\d)"
            if re.search(correct_re, result.title):
                content_score += 40
                result.has_event_match = True
            elif re.search(wrong_re, result.title):
                content_score -= 30
        elif ptype == "Day":
            correct_re = rf"(?i)(?:day\s*{pnum}|d{pnum})"
            wrong_re = rf"(?i)(?:day\s*\d|d\d)"
            if re.search(correct_re, result.title):
                content_score += 40
                result.has_event_match = True
            elif re.search(wrong_re, result.title):
                content_score -= 30

    # --- Duration multiplier ---
    duration_mult = 1.0
    if video_duration_minutes > 0 and result.duration_mins is not None and result.duration_mins > 0:
        diff = abs(video_duration_minutes - result.duration_mins)
        if diff <= 1:
            duration_mult = 2.0
        elif diff <= 5:
            duration_mult = 1.8
        elif diff <= 15:
            duration_mult = 1.4
        elif diff <= 30:
            duration_mult = 1.1
        else:
            duration_mult = 0.8

    # --- Additive bonuses ---
    year_bonus = 0.0
    if query_parts.year and result.date and query_parts.year in result.date:
        year_bonus = 25.0

    recency_bonus = 0.0
    if min_date and date_range_days > 0 and result.date:
        try:
            result_date = datetime.strptime(result.date, "%Y-%m-%d")
            recency_bonus = ((result_date - min_date).days / date_range_days) * 10
        except ValueError:
            pass

    # --- Final score ---
    result.score = (content_score * duration_mult) + year_bonus + recency_bonus
