"""Pure helpers for assembling overlay ("w/") chapters and mashup metadata.

These functions operate over parsed :class:`Track` rows and build the
``vs.``-style titles and merged tags for layered/folded chapters. No ``w/``
prefix is ever emitted: folds and clusters use ``vs.``.
"""

from __future__ import annotations

from .api import Track

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
