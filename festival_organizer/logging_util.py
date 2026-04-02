"""Logging: console output and CSV export."""
import csv
from pathlib import Path

from rich.console import Console
from rich.text import Text

from festival_organizer.console import escape, make_console
from festival_organizer.models import FileAction


CSV_FIELDS = [
    "status", "source", "target",
    "artist", "display_artist", "festival", "year", "date", "set_title",
    "stage", "edition", "content_type", "file_type",
    "resolution", "duration", "video_format", "audio_format",
    "metadata_source", "tracklists_url", "error",
]


class ActionLogger:
    """Collects action results for display and CSV export."""

    def __init__(self, verbose: bool = True, console: Console | None = None):
        self.verbose = verbose
        self.console = console or make_console()
        self.rows: list[dict] = []

    def log_action(self, action: FileAction) -> None:
        """Record and optionally print a file action."""
        mf = action.media_file
        row = {
            "status": action.status,
            "source": str(action.source),
            "target": str(action.target),
            "artist": mf.artist,
            "display_artist": mf.display_artist,
            "festival": mf.festival,
            "year": mf.year,
            "date": mf.date,
            "set_title": mf.set_title,
            "stage": mf.stage,
            "edition": mf.edition,
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
        status_styles = {
            "pending": ("DRY", "dim"),
            "done": (" OK", "green"),
            "skipped": ("SKIP", "yellow"),
            "error": ("ERR", "red"),
        }
        label, style = status_styles.get(action.status, (action.status.upper(), ""))
        ct = action.media_file.content_type or "?"
        line = Text("  [")
        line.append(f"{label:>4}", style=style)
        line.append(f"] [{ct:<12}] ")
        line.append(str(action.source))
        self.console.print(line)
        if action.status in ("pending", "done"):
            self.console.print(f"         --> {escape(str(action.target))}")
        if action.error:
            err_line = Text("         !!! ")
            err_line.append(str(action.error), style="red")
            self.console.print(err_line)

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
