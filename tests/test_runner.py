from io import StringIO
from pathlib import Path
from festival_organizer.progress import ProgressPrinter
from festival_organizer.operations import OperationResult


def test_progress_file_header():
    """Print file counter and name."""
    out = StringIO()
    pp = ProgressPrinter(total=5, stream=out)
    pp.file_start(Path("2024 - AMF - Martin Garrix.mkv"), "Martin Garrix/")
    output = out.getvalue()
    assert "[1/5]" in output
    assert "2024 - AMF - Martin Garrix.mkv" in output
    assert "Martin Garrix/" in output


def test_progress_operation_results():
    """Print operation results inline."""
    out = StringIO()
    pp = ProgressPrinter(total=3, stream=out)
    pp.file_start(Path("test.mkv"), "Artist/")
    pp.file_done([
        OperationResult("nfo", "done"),
        OperationResult("art", "done"),
        OperationResult("poster", "skipped", "exists"),
    ])
    output = out.getvalue()
    assert "nfo" in output
    assert "art" in output
    assert "poster" in output
    assert "exists" in output


def test_progress_summary():
    """Print aggregate summary."""
    out = StringIO()
    pp = ProgressPrinter(total=3, stream=out)
    pp.record_results([
        OperationResult("nfo", "done"),
        OperationResult("art", "done"),
    ])
    pp.record_results([
        OperationResult("nfo", "done"),
        OperationResult("art", "skipped", "exists"),
    ])
    pp.print_summary()
    output = out.getvalue()
    assert "NFO: 2" in output or "nfo: 2" in output.lower()


def test_progress_quiet_mode():
    """Quiet mode suppresses per-file output but keeps summary."""
    out = StringIO()
    pp = ProgressPrinter(total=1, stream=out, quiet=True)
    pp.file_start(Path("test.mkv"), "Artist/")
    pp.file_done([OperationResult("nfo", "done")])
    # Per-file output suppressed
    assert "test.mkv" not in out.getvalue()
    # Summary still works
    pp.record_results([OperationResult("nfo", "done")])
    pp.print_summary()
    assert "nfo" in out.getvalue().lower() or "NFO" in out.getvalue()
