"""Tests for enrich contract progress helpers and class."""
import pytest
from festival_organizer.operations import OperationResult
from festival_organizer.progress import _enrich_detail, _enrich_badge


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
