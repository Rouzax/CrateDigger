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


def combined_title(primary: Track | None, members: list[Track]) -> str:
    """Build ``A vs. B - TitleA vs. TitleB [LabelA/LabelB]`` for a chapter.

    ``members`` are the tracks that make up the chapter, in order (anchor
    first, then folded contributors). ``primary`` is the anchor (informational
    only here; ``members`` already carries the ordered rows and may begin with
    the lead when ``primary`` is ``None``).

    Artists are joined with ``vs.``, deduplicated and order-preserving (so a
    repeated artist such as ``Marshmello`` collapses to one). Titles are joined
    with ``vs.`` in member order and are never deduplicated. The distinct
    labels across members are slash-joined inside ``[...]``; the bracket is
    omitted entirely when no member has a label. No ``w/`` prefix is emitted.
    """
    artists: list[str] = []
    seen_artists: set[str] = set()
    titles: list[str] = []
    labels: list[str] = []
    seen_labels: set[str] = set()

    for member in members:
        artist, title = _split_artist_title(member.raw_text)
        if artist and artist not in seen_artists:
            seen_artists.add(artist)
            artists.append(artist)
        titles.append(title)
        label = member.label
        if label and label not in seen_labels:
            seen_labels.add(label)
            labels.append(label)

    artist_segment = _VS.join(artists)
    title_segment = _VS.join(titles)

    if artist_segment:
        result = f"{artist_segment}{_SEPARATOR}{title_segment}"
    else:
        result = title_segment

    if labels:
        result = f"{result} [{'/'.join(labels)}]"

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
    fold_seconds: int,
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

    # Positionless overlays (cue 0) carry no time, so they cannot be placed by a
    # time-ordered pass. They belong to the anchor they sit under in the parsed
    # row order, so resolve each to the most recent anchor preceding it in the
    # original ``tracks`` list and fold it there.
    last_anchor_in_order: AssembledChapter | None = None
    for t in tracks:
        if t.is_subcomponent:
            continue
        if not t.is_overlay:
            # Anchor candidate: only count it when it maps to an anchor chapter.
            ac = anchor_by_ms.get(t.start_ms)
            if ac is not None:
                last_anchor_in_order = ac
            continue
        if t.start_ms == 0 and last_anchor_in_order is not None:
            last_anchor_in_order.contributors.append(t)

    # 2. Walk anchors + timed overlays in time order. On a tie the anchor sorts
    # before the overlay so an overlay on a main's exact second folds INTO that
    # main rather than starting a breakout.
    overlays = sorted(
        (
            t
            for t in tracks
            if t.is_overlay and not t.is_subcomponent and t.start_ms != 0
        ),
        key=lambda t: t.start_ms,
    )

    # event: (start_ms, kind_rank, payload) where kind_rank 0 = anchor, 1 = overlay.
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
        ac.title = combined_title(ac.primary, title_members)

    # 5. Time order: anchors interleaved with breakouts by start_ms.
    return sorted(anchor_chapters + breakouts, key=lambda ac: ac.start_ms)
