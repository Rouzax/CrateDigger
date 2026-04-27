"""Tests for OrganizeContractProgress."""
import io
from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

from festival_organizer.operations import OrganizeOperation, OperationResult
from festival_organizer.progress import OrganizeContractProgress


def _console():
    return Console(file=io.StringIO(), width=120, no_color=True)


def _mf(content_type="festival_set"):
    m = MagicMock()
    m.content_type = content_type
    return m


def _capture(con) -> str:
    return con.file.getvalue()


class TestFileDone:
    def test_emits_done_verdict_for_rename(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="place_nested",
        )
        op = OrganizeOperation(target=Path("/lib/new.mkv"), action="rename")
        op.sidecars_moved = 0
        result = OperationResult("organize", "done")
        p.file_done(
            source=Path("/lib/old.mkv"), media_file=_mf(),
            op=op, result=result, elapsed_s=0.1,
        )
        out = _capture(con)
        assert "done" in out
        assert "new.mkv" in out

    def test_emits_up_to_date_when_same_path(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="place_nested",
        )
        target = Path("/lib/same.mkv")
        op = OrganizeOperation(target=target, action="rename")
        op.sidecars_moved = 0
        result = OperationResult("organize", "skipped", "exists")
        p.file_done(
            source=target, media_file=_mf(),
            op=op, result=result, elapsed_s=0.0,
        )
        out = _capture(con)
        assert "up-to-date" in out
        assert "already at target" in out

    def test_emits_error_verdict(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="copy", layout="place_flat",
        )
        op = OrganizeOperation(target=Path("/lib/out/f.mkv"), action="copy")
        op.sidecars_moved = 0
        result = OperationResult("organize", "error", "Permission denied")
        p.file_done(
            source=Path("/in/f.mkv"), media_file=_mf(),
            op=op, result=result, elapsed_s=0.3,
        )
        out = _capture(con)
        assert "error" in out
        assert "Permission denied" in out

    def test_verdict_is_two_lines(self):
        """file_done emits a two-line verdict block."""
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="place_nested",
        )
        op = OrganizeOperation(target=Path("/lib/new.mkv"), action="rename")
        op.sidecars_moved = 0
        result = OperationResult("organize", "done")
        p.file_done(
            source=Path("/lib/old.mkv"), media_file=_mf(),
            op=op, result=result, elapsed_s=0.1,
        )
        out = _capture(con)
        lines = [entry for entry in out.strip().split("\n") if entry.strip()]
        assert len(lines) == 2
        assert "->" not in lines[0]
        assert "new.mkv" in lines[1]

    def test_quiet_suppresses_output(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=True, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="place_nested",
        )
        op = OrganizeOperation(target=Path("/lib/new.mkv"), action="rename")
        op.sidecars_moved = 0
        result = OperationResult("organize", "done")
        p.file_done(
            source=Path("/lib/old.mkv"), media_file=_mf(),
            op=op, result=result, elapsed_s=0.1,
        )
        assert _capture(con).strip() == ""


class TestFilePreview:
    def test_emits_preview_verdict(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=True,
            action="copy", layout="place_flat",
        )
        p.file_preview(
            source=Path("/in/f.mkv"), media_file=_mf(),
            target=Path("/lib/Fests/Ultra/f.mkv"),
        )
        out = _capture(con)
        assert "preview" in out
        assert "would copy to" in out


class TestVerboseMetadata:
    def test_metadata_line_emitted(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=True,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="place_nested",
        )
        op = OrganizeOperation(target=Path("/lib/new.mkv"), action="rename")
        op.sidecars_moved = 2
        result = OperationResult("organize", "done")
        p.file_done(
            source=Path("/lib/old.mkv"), media_file=_mf("festival_set"),
            op=op, result=result, elapsed_s=0.1,
        )
        out = _capture(con)
        assert "festival_set" in out
        assert "place_nested" in out
        assert "2 sidecars" in out

    def test_metadata_line_absent_when_not_verbose(self):
        con = _console()
        p = OrganizeContractProgress(
            total=1, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="rename", layout="place_nested",
        )
        op = OrganizeOperation(target=Path("/lib/new.mkv"), action="rename")
        op.sidecars_moved = 2
        result = OperationResult("organize", "done")
        p.file_done(
            source=Path("/lib/old.mkv"), media_file=_mf("festival_set"),
            op=op, result=result, elapsed_s=0.1,
        )
        out = _capture(con)
        assert "festival_set" not in out


class TestSummary:
    def test_prints_summary_panel(self):
        con = _console()
        p = OrganizeContractProgress(
            total=2, console=con, quiet=False, verbose=False,
            output_root=Path("/lib"), dry_run=False,
            action="copy", layout="place_flat",
        )
        op1 = OrganizeOperation(target=Path("/lib/Fests/Ultra/a.mkv"), action="copy")
        op1.sidecars_moved = 0
        p.file_done(
            source=Path("/in/a.mkv"), media_file=_mf(),
            op=op1, result=OperationResult("organize", "done"),
            elapsed_s=1.0,
        )
        op2 = OrganizeOperation(target=Path("/lib/Fests/Ultra/b.mkv"), action="copy")
        op2.sidecars_moved = 0
        p.file_done(
            source=Path("/in/b.mkv"), media_file=_mf(),
            op=op2, result=OperationResult("organize", "done"),
            elapsed_s=0.5,
        )
        p.print_summary(elapsed_s=1.5)
        out = _capture(con)
        assert "Summary" in out
        assert "done" in out
        assert "Fests/Ultra" in out
