"""Logging: console output and CSV export."""
import csv
import io
import sys
from pathlib import Path

from festival_organizer.models import FileAction

# Force UTF-8 on Windows console (skip when running under pytest to
# avoid closing the capture file descriptors pytest relies on).
if sys.platform == "win32" and "pytest" not in sys.modules:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


CSV_FIELDS = [
    "status", "source", "target",
    "artist", "festival", "year", "date", "set_title",
    "stage", "location", "content_type", "file_type",
    "resolution", "duration", "video_format", "audio_format",
    "metadata_source", "tracklists_url", "error",
]


class ActionLogger:
    """Collects action results for display and CSV export."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.rows: list[dict] = []

    def log_action(self, action: FileAction) -> None:
        """Record and optionally print a file action."""
        mf = action.media_file
        row = {
            "status": action.status,
            "source": str(action.source),
            "target": str(action.target),
            "artist": mf.artist,
            "festival": mf.festival,
            "year": mf.year,
            "date": mf.date,
            "set_title": mf.set_title,
            "stage": mf.stage,
            "location": mf.location,
            "content_type": mf.content_type,
            "file_type": mf.file_type,
            "resolution": mf.resolution,
            "duration": mf.duration_formatted,
            "video_format": mf.video_format,
            "audio_format": mf.audio_format,
            "metadata_source": mf.metadata_source,
            "tracklists_url": mf.tracklists_url,
            "error": action.error,
        }
        self.rows.append(row)

        if self.verbose:
            self._print_action(action)

    def _print_action(self, action: FileAction) -> None:
        status_labels = {
            "pending": "DRY",
            "done": " OK",
            "skipped": "SKIP",
            "error": "ERR",
        }
        label = status_labels.get(action.status, action.status.upper())
        ct = action.media_file.content_type or "?"
        print(f"  [{label:>4}] [{ct:<12}] {action.source}")
        if action.status in ("pending", "done"):
            print(f"         --> {action.target}")
        if action.error:
            print(f"         !!! {action.error}")

    def save_csv(self, path: Path) -> None:
        """Write all recorded actions to a CSV file."""
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.rows)

    @property
    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.rows:
            s = row.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        return counts
