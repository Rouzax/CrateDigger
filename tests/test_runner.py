from io import StringIO
from pathlib import Path

from rich.console import Console

from festival_organizer.models import MediaFile
from festival_organizer.progress import ProgressPrinter
from festival_organizer.operations import Operation, OperationResult
from festival_organizer.runner import run_pipeline


def _make_console() -> tuple[Console, StringIO]:
    """Create a Console writing to a buffer for test assertions."""
    buf = StringIO()
    return Console(file=buf, no_color=True, force_terminal=True), buf


def test_progress_file_header():
    """Print file counter and name."""
    console, buf = _make_console()
    pp = ProgressPrinter(total=5, console=console)
    pp.file_start(Path("2024 - AMF - Martin Garrix.mkv"), "Martin Garrix/")
    output = buf.getvalue()
    assert "[1/5]" in output
    assert "2024 - AMF - Martin Garrix.mkv" in output
    assert "Martin Garrix/" in output


def test_progress_operation_results():
    """Print operation results inline."""
    console, buf = _make_console()
    pp = ProgressPrinter(total=3, console=console)
    pp.file_start(Path("test.mkv"), "Artist/")
    pp.file_done([
        OperationResult("nfo", "done"),
        OperationResult("art", "done"),
        OperationResult("poster", "skipped", "exists"),
    ])
    output = buf.getvalue()
    assert "nfo" in output
    assert "art" in output
    assert "poster" in output
    assert "exists" in output


def test_progress_summary():
    """Print aggregate summary."""
    console, buf = _make_console()
    pp = ProgressPrinter(total=3, console=console)
    pp.record_results([
        OperationResult("nfo", "done"),
        OperationResult("art", "done"),
    ])
    pp.record_results([
        OperationResult("nfo", "done"),
        OperationResult("art", "skipped", "exists"),
    ])
    pp.print_summary()
    output = buf.getvalue()
    assert "NFO" in output or "nfo" in output.lower()


def test_progress_quiet_mode():
    """Quiet mode suppresses per-file output but keeps summary."""
    console, buf = _make_console()
    pp = ProgressPrinter(total=1, console=console, quiet=True)
    pp.file_start(Path("test.mkv"), "Artist/")
    pp.file_done([OperationResult("nfo", "done")])
    # Per-file output suppressed
    assert "test.mkv" not in buf.getvalue()
    # Summary still works
    pp.record_results([OperationResult("nfo", "done")])
    pp.print_summary()
    output = buf.getvalue()
    assert "nfo" in output.lower() or "NFO" in output


def _make_mf(**kwargs):
    defaults = dict(source_path=Path("test.mkv"), artist="Test",
                    festival="TML", year="2024", content_type="festival_set")
    defaults.update(kwargs)
    return MediaFile(**defaults)


class BrokenIsNeededOp(Operation):
    name = "broken"

    def is_needed(self, file_path, media_file):
        raise OSError("broken symlink")

    def execute(self, file_path, media_file):
        return OperationResult(self.name, "done")


def test_pipeline_is_needed_failure_does_not_crash(tmp_path):
    """If is_needed() raises, the operation is marked as error, pipeline continues."""
    video = tmp_path / "test.mkv"
    video.write_bytes(b"")
    mf = _make_mf()
    ops = [BrokenIsNeededOp()]
    console, _ = _make_console()
    progress = ProgressPrinter(total=1, console=console)
    results = run_pipeline([(video, mf, ops)], progress)
    assert len(results) == 1
    assert results[0][0].status == "error"
    assert "broken symlink" in results[0][0].detail
