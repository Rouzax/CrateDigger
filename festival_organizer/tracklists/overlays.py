"""Pure helpers for assembling overlay ("w/") chapters and mashup metadata.

These functions operate over parsed :class:`Track` rows and build the
``vs.``-style titles and merged tags for layered/folded chapters. No ``w/``
prefix is ever emitted: folds and clusters use ``vs.``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .api import Track
from .chapters import Chapter, _timestamp_to_seconds

_SEPARATOR = " - "
_VS = " vs. "


def _split_artist_title(raw_text: str) -> tuple[str, str]:
    """Split a track label into (artist, title) on the LAST ``" - "``.

    With no ``" - "`` the artist is empty and the whole text is the title
    segment (e.g. ``"ID"`` or a label-less acapella).
    """
    artist, sep, title = raw_text.rpartition(_SEPARATOR)
    if not sep:
        return "", raw_text
    return artist, title


# The per-chapter tags that identify owns and merge_chapter_tags can emit.
# MUSICBRAINZ_ARTISTIDS is deliberately excluded: it is written per-chapter by
# the enrich pipeline, not here, so any drift check over identify-managed tags
# must ignore it (otherwise every enriched file looks perpetually stale).
CHAPTER_TAG_KEYS: frozenset[str] = frozenset(
    {
        "CRATEDIGGER_TRACK_PERFORMER",
        "CRATEDIGGER_TRACK_TITLE",
        "CRATEDIGGER_TRACK_PERFORMER_SLUGS",
        "CRATEDIGGER_TRACK_PERFORMER_NAMES",
        "CRATEDIGGER_TRACK_LABEL",
        "CRATEDIGGER_TRACK_GENRE",
    }
)


def _title_segments(members: list[Track]) -> tuple[str, str, list[str]]:
    """Split chapter members into ``(artist_segment, title_segment, labels)``.

    ``members`` are the tracks that make up the chapter, in order (anchor first,
    then folded contributors). Artists are joined with ``vs.``, deduplicated and
    order-preserving (so a repeated artist such as ``Marshmello`` collapses to
    one). Titles are joined with ``vs.`` in member order and are never
    deduplicated. ``labels`` are the distinct member labels in order.

    Members with empty ``raw_text`` are skipped: a contentless row carries no
    artist or title to join, so including it would emit a dangling ``vs.``. This
    is a data-void guard, not ``ID``-placeholder handling; an un-ID'd row parses
    to a real ``"ID - ID"`` and joins faithfully.

    Shared by :func:`combined_title` (the display string) and
    :func:`merge_chapter_tags` (the single-value performer/title tags) so the
    two can never disagree about how a chapter's mashup is rendered.
    """
    artists: list[str] = []
    seen_artists: set[str] = set()
    titles: list[str] = []
    labels: list[str] = []
    seen_labels: set[str] = set()

    for member in members:
        if not member.raw_text.strip():
            continue
        artist, title = _split_artist_title(member.raw_text)
        if artist and artist not in seen_artists:
            seen_artists.add(artist)
            artists.append(artist)
        titles.append(title)
        label = member.label
        if label and label not in seen_labels:
            seen_labels.add(label)
            labels.append(label)

    return _VS.join(artists), _VS.join(titles), labels


def combined_title(members: list[Track]) -> str:
    """Build ``A vs. B - TitleA vs. TitleB [LabelA/LabelB]`` for a chapter.

    ``members`` are the tracks that make up the chapter, in order (anchor first,
    then folded contributors). Artists, titles, and labels come from
    :func:`_title_segments`. The distinct labels are slash-joined inside
    ``[...]``; the bracket is omitted entirely when no member has a label. No
    ``w/`` prefix is emitted.
    """
    artist_segment, title_segment, labels = _title_segments(members)

    if artist_segment:
        result = f"{artist_segment}{_SEPARATOR}{title_segment}"
    else:
        result = title_segment

    if labels:
        result = f"{result} [{'/'.join(labels)}]"

    return result


def merge_chapter_tags(
    primary: Track | None,
    contributors: list[Track],
    *,
    mashup_metadata: bool,
) -> dict[str, str]:
    """Build the TTV=30 per-chapter tag block for one chapter.

    Unions the ``(slug, name)`` artist pairs and genres across the chapter's
    source tracks, deduplicating by slug (first occurrence wins) while keeping
    the parallel name list index-aligned with the slug list.

    For a mashup main WITH ``tlpSubTog`` sub-components and
    ``mashup_metadata=True`` the artist/genre source is the contributors (the
    real per-component rows), dropping the mashup primary whose only slug is a
    junk concatenated mega-slug and whose genres are empty. Otherwise the source
    is ``[primary] + contributors``. Labels are always the distinct labels
    across ``[primary] + contributors`` (including a mashup primary's real
    label), order-preserving.

    The single-value display tags (``CRATEDIGGER_TRACK_PERFORMER`` and
    ``CRATEDIGGER_TRACK_TITLE``) mirror the display title: they are the artist
    and title segments of :func:`_title_segments` over the same members the
    title pass uses (``primary`` plus the non-subcomponent contributors). So a
    folded ``w/`` overlay appears in these tags exactly as it does in the
    chapter title, never just in the flat ``_NAMES``/``_SLUGS`` lists. Keys are
    emitted only when their value is non-empty. ``MUSICBRAINZ_ARTISTIDS`` and
    the legacy unprefixed PERFORMER/LABEL/GENRE tags are intentionally never
    written here. Returns ``{}`` when there is no primary and no contributor.
    """
    if primary is None and not contributors:
        return {}

    # The members the title pass renders (see assemble step 4): primary plus the
    # non-subcomponent contributors. The single-value tags derive from these so
    # they always match combined_title.
    title_members = ([primary] if primary is not None else []) + [
        c for c in contributors if not c.is_subcomponent
    ]
    artist_segment, title_segment, _ = _title_segments(title_members)
    # lead is only a fallback for the performer tag when no member has an artist.
    lead: Track | None = primary
    if lead is None:
        lead = next((c for c in contributors if not c.is_subcomponent), None)

    use_children = (
        primary is not None
        and primary.is_mashup
        and mashup_metadata
        and any(c.is_subcomponent for c in contributors)
    )
    if use_children:
        artist_genre_source = contributors
    else:
        artist_genre_source = ([primary] if primary is not None else []) + contributors

    slugs: list[str] = []
    names: list[str] = []
    seen_slugs: set[str] = set()
    for track in artist_genre_source:
        for slug, name in zip(track.artist_slugs, track.artist_names, strict=True):
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            slugs.append(slug)
            names.append(name)

    genres: list[str] = []
    seen_genres: set[str] = set()
    for track in artist_genre_source:
        for genre in track.genres:
            if genre in seen_genres:
                continue
            seen_genres.add(genre)
            genres.append(genre)

    # Labels always come from primary + contributors (even a mashup primary's).
    label_source = ([primary] if primary is not None else []) + contributors
    labels: list[str] = []
    seen_labels: set[str] = set()
    for track in label_source:
        label = track.label
        if label and label not in seen_labels:
            seen_labels.add(label)
            labels.append(label)

    entry: dict[str, str] = {}
    if slugs:
        entry["CRATEDIGGER_TRACK_PERFORMER_SLUGS"] = "|".join(slugs)
        # names is built in lockstep with slugs, so lengths always match.
        entry["CRATEDIGGER_TRACK_PERFORMER_NAMES"] = "|".join(names)
        if artist_segment:
            display = artist_segment
        elif lead is not None:
            display = lead.raw_text.strip() or slugs[0]
        else:
            display = slugs[0]
        entry["CRATEDIGGER_TRACK_PERFORMER"] = display
    if title_segment:
        entry["CRATEDIGGER_TRACK_TITLE"] = title_segment
    if labels:
        entry["CRATEDIGGER_TRACK_LABEL"] = "|".join(labels)
    if genres:
        entry["CRATEDIGGER_TRACK_GENRE"] = "|".join(genres)
    return entry


def build_chapter_tags_from_assembled(
    assembled: list[AssembledChapter],
    chapter_uids: list[int],
    *,
    mashup_metadata: bool,
) -> dict[int, dict[str, str]]:
    """Build the per-chapter TTV=30 tag map keyed by ChapterUID.

    ``assembled`` must align 1:1 with ``chapter_uids`` (same order and count);
    the caller guarantees this. For each pair, :func:`merge_chapter_tags` builds
    the chapter's tag block from its ``primary`` and ``contributors``. A chapter
    is included only when its merged tag block is non-empty.
    """
    result: dict[int, dict[str, str]] = {}
    for ac, uid in zip(assembled, chapter_uids, strict=True):
        tags = merge_chapter_tags(
            ac.primary, ac.contributors, mashup_metadata=mashup_metadata
        )
        if tags:
            result[uid] = tags
    return result


@dataclass
class AssembledChapter:
    """A chapter after overlay coalescing.

    ``primary`` is the anchor :class:`Track` (a plain main or a mashup main);
    it is ``None`` for a pure breakout cluster that has no anchor. ``contributors``
    are the folded overlays plus any ``tlpSubTog`` sub-components attached to a
    mashup main; sub-components are metadata-only and never appear in ``title``.
    """

    start_ms: int
    title: str
    primary: Track | None
    contributors: list[Track] = field(default_factory=list)
    language: str = "eng"


def assemble(
    anchors: list[Chapter],
    anchor_tracks: dict[int, Track],
    tracks: list[Track],
    *,
    fold_seconds: int | None,
) -> list[AssembledChapter]:
    """Coalesce overlay rows onto anchor chapters by distance to host.

    ``anchors`` are the existing main / mashup-main chapters (already in time
    order). ``anchor_tracks`` maps an anchor's ``start_ms`` to its :class:`Track`
    (mains / mashup-mains only). ``tracks`` is the full parsed Track list.

    Each timed overlay folds into the most recent anchor when it sits within
    ``fold_seconds`` of it (or on its exact second); otherwise it breaks out as
    its own chapter, joining an immediately preceding breakout when within
    ``fold_seconds`` of it. Positionless overlays fold into the current anchor.
    ``tlpSubTog`` sub-components attach to the anchor whose mashup-main shares
    their ``group_id``. Returns chapters in ascending ``start_ms`` order.

    When ``fold_seconds is None`` (overlays-disabled mode) both the timed and
    positionless overlay passes are skipped entirely: no overlay is folded into
    a title and no breakout chapter is created. Sub-component (``tlpSubTog``)
    attachment and the title pass still run, so the result is exactly one
    :class:`AssembledChapter` per anchor, a mashup anchor still carries its
    sub-components as ``contributors``, and every title equals its anchor's own
    title. This lets the pipeline harvest mashup metadata even with overlay
    chapters turned off.
    """
    # 1. One AssembledChapter per anchor, in anchor order.
    anchor_chapters: list[AssembledChapter] = []
    for anchor in anchors:
        start_ms = round(_timestamp_to_seconds(anchor.timestamp) * 1000)
        anchor_chapters.append(
            AssembledChapter(
                start_ms=start_ms,
                title=anchor.title,
                primary=anchor_tracks.get(start_ms),
                contributors=[],
                language=anchor.language,
            )
        )

    breakouts: list[AssembledChapter] = []
    anchor_by_ms = {ac.start_ms: ac for ac in anchor_chapters}

    # In overlays-disabled mode (fold_seconds is None) we skip both the
    # positionless-overlay fold pass and the timed-overlay fold/breakout pass.
    if fold_seconds is not None:
        # Positionless overlays (cue 0) carry no time, so they cannot be placed
        # by a time-ordered pass. They belong to the anchor they sit under in
        # the parsed row order, so resolve each to the most recent anchor
        # preceding it in the original ``tracks`` list and fold it there.
        last_anchor_in_order: AssembledChapter | None = None
        for t in tracks:
            if t.is_subcomponent:
                continue
            if not t.is_overlay:
                # Anchor candidate: only count it when it maps to an anchor.
                ac = anchor_by_ms.get(t.start_ms)
                if ac is not None:
                    last_anchor_in_order = ac
                continue
            if t.start_ms == 0 and last_anchor_in_order is not None:
                last_anchor_in_order.contributors.append(t)

        # 2. Walk anchors + timed overlays in time order. On a tie the anchor
        # sorts before the overlay so an overlay on a main's exact second folds
        # INTO that main rather than starting a breakout.
        overlays = sorted(
            (
                t
                for t in tracks
                if t.is_overlay and not t.is_subcomponent and t.start_ms != 0
            ),
            key=lambda t: t.start_ms,
        )

        # event: (start_ms, kind_rank, payload); kind_rank 0 = anchor, 1 = overlay.
        events: list[tuple[int, int, object]] = []
        for ac in anchor_chapters:
            events.append((ac.start_ms, 0, ac))
        for ov in overlays:
            events.append((ov.start_ms, 1, ov))
        events.sort(key=lambda e: (e[0], e[1]))

        cur_anchor: AssembledChapter | None = None
        cur_breakout: AssembledChapter | None = None

        for _start_ms, kind, payload in events:
            if kind == 0:
                cur_anchor = payload  # type: ignore[assignment]
                cur_breakout = None
                continue

            overlay = payload  # type: ignore[assignment]
            assert isinstance(overlay, Track)

            host = cur_anchor
            if host is not None and (
                overlay.start_ms == host.start_ms
                or (overlay.start_ms - host.start_ms) / 1000 < fold_seconds
            ):
                host.contributors.append(overlay)
            elif (
                cur_breakout is not None
                and (overlay.start_ms - cur_breakout.start_ms) / 1000 < fold_seconds
            ):
                cur_breakout.contributors.append(overlay)
            else:
                cur_breakout = AssembledChapter(
                    start_ms=overlay.start_ms,
                    title="",
                    primary=None,
                    contributors=[overlay],
                )
                breakouts.append(cur_breakout)

    # 3. Sub-components attach to the anchor whose mashup-main shares group_id.
    for t in tracks:
        if not t.is_subcomponent:
            continue
        for ac in anchor_chapters:
            if (
                ac.primary is not None
                and ac.primary.group_id == t.group_id
                and t.group_id != -1
            ):
                ac.contributors.append(t)
                break

    # 4. Titles. Sub-components are excluded from title members.
    for ac in anchor_chapters + breakouts:
        title_members = ([ac.primary] if ac.primary is not None else []) + [
            c for c in ac.contributors if not c.is_subcomponent
        ]
        ac.title = combined_title(title_members)

    # 5. Time order: anchors interleaved with breakouts by start_ms.
    return sorted(anchor_chapters + breakouts, key=lambda ac: ac.start_ms)
