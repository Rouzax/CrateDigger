"""Build RunReport models from run results (pure, dependency-injected I/O)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from festival_organizer.notify.models import EmailSet, RunReport, UpdateInfo


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


def _email_set(mf, final_path: Path, *, metric: str) -> EmailSet:
    return EmailSet(
        artist=mf.display_artist or mf.artist,
        event=mf.place or mf.festival or "",
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
    host: str,
    timestamp: str,
    count_chapters: Callable[[Path], int | None],
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
        sets.append(_email_set(mf, final_path, metric=_new_metric(mf, chapters)))
    return RunReport(channel="new_sets", sets=sets, update=update,
                     stats=stats, host=host, timestamp=timestamp)
