"""Tests for the organize_verdict function."""
from pathlib import Path

from festival_organizer.console import organize_verdict


class TestPreview:
    def test_from_to_layout(self):
        text = organize_verdict(
            status="preview",
            index=1,
            total=86,
            source=Path("/inbox/old.mkv"),
            target=Path("/lib/Fests/new.mkv"),
            output_root=Path("/lib"),
            elapsed_s=0.0,
        )
        plain = text.plain
        assert "preview" in plain
        assert "from:" in plain
        assert "to:" in plain
        assert "old.mkv" in plain
        assert "Fests/new.mkv" in plain

    def test_source_at_root_shows_dot_slash(self):
        text = organize_verdict(
            status="preview",
            index=1,
            total=5,
            source=Path("/lib/old.mkv"),
            target=Path("/lib/Fests/new.mkv"),
            output_root=Path("/lib"),
            elapsed_s=0.0,
        )
        plain = text.plain
        assert "from:" in plain
        from_line = plain.split("\n")[0]
        assert "./" in from_line

    def test_source_outside_library_bare_filename(self):
        text = organize_verdict(
            status="preview",
            index=1,
            total=5,
            source=Path("/inbox/raw.mkv"),
            target=Path("/lib/Fests/clean.mkv"),
            output_root=Path("/lib"),
            elapsed_s=0.0,
        )
        from_line = text.plain.split("\n")[0]
        assert "raw.mkv" in from_line

    def test_counter_right_aligned(self):
        text = organize_verdict(
            status="preview",
            index=1,
            total=86,
            source=Path("/inbox/f.mkv"),
            target=Path("/lib/Fests/f.mkv"),
            output_root=Path("/lib"),
            elapsed_s=0.0,
        )
        assert "[ 1/86]" in text.plain


class TestDone:
    def test_from_to_with_elapsed(self):
        text = organize_verdict(
            status="done",
            index=5,
            total=10,
            source=Path("/inbox/f.mkv"),
            target=Path("/lib/Fests/f.mkv"),
            output_root=Path("/lib"),
            elapsed_s=2.5,
        )
        plain = text.plain
        assert "done" in plain
        assert "from:" in plain
        assert "to:" in plain
        assert "2.5s" in plain

    def test_elapsed_on_to_line(self):
        text = organize_verdict(
            status="done",
            index=1,
            total=5,
            source=Path("/inbox/f.mkv"),
            target=Path("/lib/Fests/f.mkv"),
            output_root=Path("/lib"),
            elapsed_s=1.5,
        )
        lines = text.plain.split("\n")
        assert len(lines) == 2
        assert "1.5s" in lines[1]
        assert "1.5s" not in lines[0]


class TestUpToDate:
    def test_single_line_no_from_to(self):
        p = Path("/lib/same.mkv")
        text = organize_verdict(
            status="up-to-date",
            index=3,
            total=10,
            source=p,
            target=p,
            output_root=Path("/lib"),
            elapsed_s=0.0,
        )
        plain = text.plain
        assert "up-to-date" in plain
        assert "\n" not in plain
        assert "from:" not in plain
        assert "to:" not in plain


class TestSkippedAndError:
    def test_skipped_delegates_to_verdict(self):
        text = organize_verdict(
            status="skipped",
            index=1,
            total=5,
            source=Path("/inbox/f.mkv"),
            target=Path("/lib/Fests/f.mkv"),
            output_root=Path("/lib"),
            elapsed_s=0.0,
            detail="file too large",
        )
        plain = text.plain
        assert "skipped" in plain
        assert "file too large" in plain

    def test_error_delegates_to_verdict(self):
        text = organize_verdict(
            status="error",
            index=1,
            total=5,
            source=Path("/inbox/f.mkv"),
            target=Path("/lib/f.mkv"),
            output_root=Path("/lib"),
            elapsed_s=0.1,
            detail="Permission denied",
        )
        plain = text.plain
        assert "error" in plain
        assert "Permission denied" in plain


class TestFromToAlignment:
    def test_to_path_aligns_with_from_path(self):
        text = organize_verdict(
            status="preview",
            index=1,
            total=5,
            source=Path("/lib/old.mkv"),
            target=Path("/lib/Fests/new.mkv"),
            output_root=Path("/lib"),
            elapsed_s=0.0,
        )
        lines = text.plain.split("\n")
        assert len(lines) == 2
        from_path_col = lines[0].index("./")
        to_path_col = lines[1].index("Fests/")
        assert from_path_col == to_path_col
