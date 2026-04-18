"""Tests for enrich_summary_panel."""
from festival_organizer.console import enrich_summary_panel


class TestEnrichSummaryPanel:
    def test_file_stats_row(self):
        panel = enrich_summary_panel(
            file_stats={"done": 5, "up_to_date": 3, "error": 1},
            op_counts={},
            errors=[],
            elapsed_s=12.5,
        )
        text = panel.renderable.plain
        assert "done: 5" in text
        assert "up_to_date: 3" in text
        assert "error: 1" in text
        assert "12.5s" in text

    def test_op_breakdown(self):
        panel = enrich_summary_panel(
            file_stats={"done": 2, "up_to_date": 0, "error": 0},
            op_counts={
                "nfo": {"done": 2},
                "art": {"done": 1, "skipped": 1},
                "tags": {"done": 2},
            },
            errors=[],
        )
        text = panel.renderable.plain
        assert "NFO" in text
        assert "ART" in text
        assert "TAGS" in text
        # Check art has both done and skipped counts
        assert "1" in text  # done count for art

    def test_errors_section(self):
        panel = enrich_summary_panel(
            file_stats={"done": 0, "up_to_date": 0, "error": 2},
            op_counts={},
            errors=[
                ("file1.mkv", "posters", "no thumb"),
                ("file2.mkv", "tags", "mkvpropedit failed"),
            ],
        )
        text = panel.renderable.plain
        assert "file1.mkv" in text
        assert "no thumb" in text
        assert "file2.mkv" in text

    def test_errors_capped_at_10(self):
        errors = [(f"file{i}.mkv", "op", f"err{i}") for i in range(15)]
        panel = enrich_summary_panel(
            file_stats={"done": 0, "up_to_date": 0, "error": 15},
            op_counts={},
            errors=errors,
        )
        text = panel.renderable.plain
        assert "+5 more" in text

    def test_unresolved_artists_count(self):
        panel = enrich_summary_panel(
            file_stats={"done": 5, "up_to_date": 0, "error": 0},
            op_counts={},
            errors=[],
            unresolved_count=14,
        )
        text = panel.renderable.plain
        assert "14" in text
        assert "nresolved" in text.lower() or "Unresolved" in text

    def test_title_is_summary(self):
        panel = enrich_summary_panel(
            file_stats={"done": 1, "up_to_date": 0, "error": 0},
            op_counts={},
            errors=[],
        )
        assert "Summary" in str(panel.title)

    def test_op_order(self):
        """Operations should appear in workflow order, not alphabetical."""
        panel = enrich_summary_panel(
            file_stats={"done": 1, "up_to_date": 0, "error": 0},
            op_counts={
                "tags": {"done": 1},
                "nfo": {"done": 1},
                "art": {"done": 1},
            },
            errors=[],
        )
        text = panel.renderable.plain
        nfo_pos = text.index("NFO")
        art_pos = text.index("ART")
        tags_pos = text.index("TAGS")
        assert nfo_pos < art_pos < tags_pos
