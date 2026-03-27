from io import StringIO
from pathlib import Path
from festival_organizer.models import MediaFile
from festival_organizer.progress import ProgressPrinter
from festival_organizer.operations import Operation, OperationResult
from festival_organizer.runner import run_pipeline


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
    progress = ProgressPrinter(total=1, stream=StringIO())
    results = run_pipeline([(video, mf, ops)], progress)
    assert len(results) == 1
    assert results[0][0].status == "error"
    assert "broken symlink" in results[0][0].detail
