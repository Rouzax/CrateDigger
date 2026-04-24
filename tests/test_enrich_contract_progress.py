"""Tests for enrich contract progress helpers and class."""
import io
from pathlib import Path

from rich.console import Console

from festival_organizer.operations import OperationResult
from festival_organizer.progress import _enrich_detail, _enrich_badge


def _console():
    return Console(file=io.StringIO(), width=120, no_color=True)


def _capture(con) -> str:
    return con.file.getvalue()


class TestEnrichDetail:
    def test_all_done(self):
        results = [
            OperationResult("nfo", "done"),
            OperationResult("art", "done"),
            OperationResult("tags", "done"),
        ]
        assert _enrich_detail(results) == "nfo, art, tags"

    def test_all_skipped_trivial(self):
        """All skipped with trivial reasons -> 'all up to date'."""
        results = [
            OperationResult("nfo", "skipped", "exists"),
            OperationResult("art", "skipped", "exists"),
        ]
        assert _enrich_detail(results) == "all up to date"

    def test_mixed_done_and_trivial_skip(self):
        """Done ops listed, trivially-skipped ops omitted."""
        results = [
            OperationResult("nfo", "done"),
            OperationResult("art", "skipped", "exists"),
            OperationResult("tags", "done"),
        ]
        assert _enrich_detail(results) == "nfo, tags"

    def test_error_called_out(self):
        """Errors are called out after done ops."""
        results = [
            OperationResult("nfo", "done"),
            OperationResult("art", "done"),
            OperationResult("posters", "error", "no thumb"),
            OperationResult("tags", "done"),
        ]
        assert _enrich_detail(results) == "nfo, art, tags done; posters error: no thumb"

    def test_skip_with_actionable_reason(self):
        """Non-trivial skip reasons are shown."""
        results = [
            OperationResult("nfo", "done"),
            OperationResult("chapter_artist_mbids", "skipped", "run identify"),
        ]
        assert _enrich_detail(results) == "nfo; chapter_artist_mbids skipped: run identify"

    def test_all_error(self):
        results = [
            OperationResult("nfo", "error", "write failed"),
            OperationResult("art", "error", "no source"),
        ]
        assert _enrich_detail(results) == "nfo error: write failed; art error: no source"

    def test_all_skipped_with_actionable_reason(self):
        """All skipped but with non-trivial reasons."""
        results = [
            OperationResult("chapter_artist_mbids", "skipped", "run identify"),
            OperationResult("album_artist_mbids", "skipped", "MBIDs already current"),
        ]
        detail = _enrich_detail(results)
        assert "chapter_artist_mbids skipped: run identify" in detail


class TestEnrichContractFileDone:
    def test_emits_two_line_verdict(self):
        from festival_organizer.progress import EnrichContractProgress
        con = _console()
        p = EnrichContractProgress(total=1, console=con, quiet=False, verbose=False)
        results = [
            OperationResult("nfo", "done"),
            OperationResult("art", "done"),
            OperationResult("tags", "skipped", "exists"),
        ]
        p.file_done(source=Path("/lib/my_set.mkv"), results=results, elapsed_s=2.5)
        out = _capture(con)
        lines = [entry for entry in out.strip().split("\n") if entry.strip()]
        assert len(lines) == 2
        assert "done" in lines[0]
        assert "my_set.mkv" in lines[0]
        assert "2.5s" in lines[0]
        assert "nfo, art" in lines[1]
        assert "->" not in lines[0]

    def test_all_skipped_shows_up_to_date(self):
        from festival_organizer.progress import EnrichContractProgress
        con = _console()
        p = EnrichContractProgress(total=1, console=con, quiet=False, verbose=False)
        results = [
            OperationResult("nfo", "skipped", "exists"),
            OperationResult("art", "skipped", "exists"),
        ]
        p.file_done(source=Path("/lib/my_set.mkv"), results=results, elapsed_s=0.1)
        out = _capture(con)
        assert "up-to-date" in out
        assert "all up to date" in out

    def test_error_badge_with_mixed(self):
        from festival_organizer.progress import EnrichContractProgress
        con = _console()
        p = EnrichContractProgress(total=1, console=con, quiet=False, verbose=False)
        results = [
            OperationResult("nfo", "done"),
            OperationResult("posters", "error", "no thumb"),
        ]
        p.file_done(source=Path("/lib/my_set.mkv"), results=results, elapsed_s=1.0)
        out = _capture(con)
        first_line = out.strip().split("\n")[0]
        assert "error" in first_line
        assert "posters error" in out

    def test_quiet_suppresses(self):
        from festival_organizer.progress import EnrichContractProgress
        con = _console()
        p = EnrichContractProgress(total=1, console=con, quiet=True, verbose=False)
        results = [OperationResult("nfo", "done")]
        p.file_done(source=Path("/lib/f.mkv"), results=results, elapsed_s=0.1)
        assert _capture(con).strip() == ""

    def test_verbose_shows_per_op_breakdown(self):
        from festival_organizer.progress import EnrichContractProgress
        con = _console()
        p = EnrichContractProgress(total=1, console=con, quiet=False, verbose=True)
        results = [
            OperationResult("nfo", "done", "generated"),
            OperationResult("art", "skipped", "exists"),
            OperationResult("tags", "error", "mkvpropedit failed"),
        ]
        p.file_done(source=Path("/lib/f.mkv"), results=results, elapsed_s=1.0)
        out = _capture(con)
        lines = [entry for entry in out.strip().split("\n") if entry.strip()]
        # Verdict block (2 lines) + verbose breakdown lines
        assert len(lines) >= 3

    def test_stats_tracking(self):
        from festival_organizer.progress import EnrichContractProgress
        con = _console()
        p = EnrichContractProgress(total=3, console=con, quiet=True, verbose=False)
        p.file_done(source=Path("/lib/a.mkv"),
                     results=[OperationResult("nfo", "done")], elapsed_s=0.1)
        p.file_done(source=Path("/lib/b.mkv"),
                     results=[OperationResult("nfo", "done")], elapsed_s=0.1)
        p.file_done(source=Path("/lib/c.mkv"),
                     results=[OperationResult("nfo", "skipped", "exists")], elapsed_s=0.1)
        assert p._file_stats["done"] == 2
        assert p._file_stats["up_to_date"] == 1

    def test_error_tracking(self):
        from festival_organizer.progress import EnrichContractProgress
        con = _console()
        p = EnrichContractProgress(total=1, console=con, quiet=True, verbose=False)
        p.file_done(source=Path("/lib/a.mkv"),
                     results=[OperationResult("posters", "error", "no thumb")], elapsed_s=0.1)
        assert p._file_stats["error"] == 1
        assert len(p._errors) == 1
        assert p._errors[0] == ("a.mkv", "posters", "no thumb")

    def test_op_counts_tracking(self):
        from festival_organizer.progress import EnrichContractProgress
        con = _console()
        p = EnrichContractProgress(total=2, console=con, quiet=True, verbose=False)
        p.file_done(source=Path("/lib/a.mkv"),
                     results=[OperationResult("nfo", "done"), OperationResult("art", "done")],
                     elapsed_s=0.1)
        p.file_done(source=Path("/lib/b.mkv"),
                     results=[OperationResult("nfo", "skipped", "exists"), OperationResult("art", "done")],
                     elapsed_s=0.1)
        assert p._op_counts["nfo"]["done"] == 1
        assert p._op_counts["nfo"]["skipped"] == 1
        assert p._op_counts["art"]["done"] == 2


class TestEnrichBadge:
    def test_all_done(self):
        results = [
            OperationResult("nfo", "done"),
            OperationResult("art", "done"),
        ]
        assert _enrich_badge(results) == "done"

    def test_all_skipped(self):
        results = [
            OperationResult("nfo", "skipped"),
            OperationResult("art", "skipped"),
        ]
        assert _enrich_badge(results) == "up-to-date"

    def test_error_wins(self):
        results = [
            OperationResult("nfo", "done"),
            OperationResult("art", "error", "fail"),
            OperationResult("tags", "done"),
        ]
        assert _enrich_badge(results) == "error"

    def test_done_beats_skipped(self):
        results = [
            OperationResult("nfo", "done"),
            OperationResult("art", "skipped"),
        ]
        assert _enrich_badge(results) == "done"
