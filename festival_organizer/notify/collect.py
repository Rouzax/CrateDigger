"""Build RunReport models from run results (pure, dependency-injected I/O)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from festival_organizer.notify.models import EmailSet, RunReport, UpdateInfo

_log = logging.getLogger("festival_organizer.notify")


def format_duration(seconds: float | None) -> str:
    """Render a duration as 'Xh Ym' or 'Ym'. Empty string when unknown."""
    if not seconds or seconds <= 0:
        return ""
    total_min = int(seconds // 60)
    h, m = divmod(total_min, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _poster_for(video_path: Path) -> Path | None:
    candidate = video_path.with_name(f"{video_path.stem}-poster.jpg")
    if candidate.exists():
        return candidate
    folder = video_path.parent / "folder.jpg"
    return folder if folder.exists() else None


def _new_metric(mf, chapters: int | None) -> str:
    dur = format_duration(getattr(mf, "duration_seconds", None))
    parts = []
    if chapters:
        parts.append(f"{chapters} tracks")
    if dur:
        parts.append(dur)
    return " · ".join(parts)


PlaceDisplay = Callable[[str, str], str]


def _event_for(mf, place_display: PlaceDisplay | None) -> str:
    """Canonical event name for the email, mirroring ``build_display_title``.

    For festival/venue/location places we render through ``place_display``
    (typically ``Config.get_place_display``), which folds in the edition
    (e.g. ``Dreamstate`` + ``SoCal`` -> ``Dreamstate SoCal``). The
    artist-kind fallback and the no-callable path keep the raw place, so the
    email never shows ``Artist`` twice and tests stay config-free.
    """
    if (
        place_display is not None
        and mf.place_kind in ("festival", "venue", "location")
        and mf.place
    ):
        return place_display(mf.place, mf.edition)
    return mf.place or mf.festival or ""


def _email_set(
    mf, final_path: Path, *, metric: str, place_display: PlaceDisplay | None = None
) -> EmailSet:
    return EmailSet(
        artist=mf.display_artist or mf.artist,
        event=_event_for(mf, place_display),
        year=mf.year,
        note=mf.stage or mf.set_title or "",
        genres=list(mf.genres),
        metric=metric,
        poster_path=_poster_for(final_path),
        kind=mf.content_type or "unknown",
    )


def collect_new_sets(
    pipeline_files,
    all_results,
    *,
    update: UpdateInfo | None,
    stats: dict,
    timestamp: str,
    count_chapters: Callable[[Path], int | None],
    place_display: PlaceDisplay | None = None,
) -> RunReport:
    """Collect sets newly organized into the library (organize op status 'done')."""
    sets: list[EmailSet] = []
    for (_src, mf, ops), results in zip(pipeline_files, all_results):
        final_path = None
        for op, result in zip(ops, results):
            if op.name == "organize" and result.status == "done":
                final_path = op.target
        if final_path is None:
            continue
        chapters = count_chapters(final_path)
        sets.append(
            _email_set(
                mf,
                final_path,
                metric=_new_metric(mf, chapters),
                place_display=place_display,
            )
        )
    return RunReport(
        channel="new_sets", sets=sets, update=update, stats=stats, timestamp=timestamp
    )


def collect_updated_sets(
    updated_paths,
    *,
    analyse: Callable[[Path], object],
    count_chapters: Callable[[Path], int | None],
    update: UpdateInfo | None,
    timestamp: str,
    stats: dict | None = None,
    on_item: Callable[[int, int, str], None] | None = None,
    place_display: PlaceDisplay | None = None,
) -> RunReport:
    """Collect sets whose chapters changed this identify run.

    `on_item(i, total, name)` is called once per path (1-based index) before
    the per-file re-analysis, so callers can drive a progress spinner. The
    re-analysis is the slow part of building the updated-sets email.
    """
    sets: list[EmailSet] = []
    total = len(updated_paths)
    for i, path in enumerate(updated_paths, start=1):
        if on_item is not None:
            on_item(i, total, path.name)
        try:
            mf = analyse(path)
        except Exception as e:  # best-effort: never break the run for one file
            _log.warning('notify.analyse_failed: file=%s error="%s"', path, e)
            continue
        chapters = count_chapters(path)
        parts = []
        if chapters:
            parts.append(f"{chapters} chapters")
        dur = format_duration(getattr(mf, "duration_seconds", None))
        if dur:
            parts.append(dur)
        metric = " · ".join(parts)
        sets.append(_email_set(mf, path, metric=metric, place_display=place_display))
    return RunReport(
        channel="updated_sets",
        sets=sets,
        update=update,
        stats=stats or {},
        timestamp=timestamp,
    )
