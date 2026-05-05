"""Tests for the context-aware organize detail string builder."""
from pathlib import Path
from unittest.mock import patch

from festival_organizer.progress import _organize_detail


def _win_normcase(s: str) -> str:
    return s.replace("/", "\\").lower()


class TestLiveRun:
    def test_rename_only_shows_new_filename(self):
        detail = _organize_detail(
            source=Path("/lib/old_name.mkv"),
            target=Path("/lib/new_name.mkv"),
            output_root=Path("/lib"),
            action="rename",
            dry_run=False,
        )
        assert detail == "new_name.mkv"

    def test_import_shows_full_relative_path(self):
        detail = _organize_detail(
            source=Path("/inbox/file.mkv"),
            target=Path("/lib/Festivals/Ultra Miami 2026/file.mkv"),
            output_root=Path("/lib"),
            action="copy",
            dry_run=False,
        )
        assert detail == "Festivals/Ultra Miami 2026/file.mkv"

    def test_both_changed_shows_full_relative(self):
        detail = _organize_detail(
            source=Path("/inbox/raw.mkv"),
            target=Path("/lib/Festivals/Ultra/clean.mkv"),
            output_root=Path("/lib"),
            action="copy",
            dry_run=False,
        )
        assert detail == "Festivals/Ultra/clean.mkv"

    def test_up_to_date(self):
        p = Path("/lib/file.mkv")
        detail = _organize_detail(
            source=p, target=p, output_root=Path("/lib"),
            action="rename", dry_run=False,
        )
        assert detail == "already at target"

    def test_prefix_case_difference_is_up_to_date(self):
        with patch("festival_organizer.paths.os.sep", "\\"), \
             patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase):
            detail = _organize_detail(
                source=Path("e:\\lib\\file.mkv"),
                target=Path("E:\\lib\\file.mkv"),
                output_root=Path("E:\\lib"),
                action="rename",
                dry_run=False,
            )
        assert detail == "already at target"


class TestDryRun:
    def test_rename_only_preview(self):
        detail = _organize_detail(
            source=Path("/lib/old.mkv"),
            target=Path("/lib/new.mkv"),
            output_root=Path("/lib"),
            action="rename",
            dry_run=True,
        )
        assert detail == "would rename to new.mkv"

    def test_copy_preview(self):
        detail = _organize_detail(
            source=Path("/inbox/f.mkv"),
            target=Path("/lib/Fests/f.mkv"),
            output_root=Path("/lib"),
            action="copy",
            dry_run=True,
        )
        assert detail == "would copy to Fests/f.mkv"

    def test_move_both_changed_preview(self):
        detail = _organize_detail(
            source=Path("/inbox/raw.mkv"),
            target=Path("/lib/Fests/Ultra/clean.mkv"),
            output_root=Path("/lib"),
            action="move",
            dry_run=True,
        )
        assert detail == "would move to Fests/Ultra/clean.mkv"

    def test_prefix_case_difference_is_up_to_date(self):
        """e:\\Data vs E:\\data prefix is the same library; file is at target."""
        with patch("festival_organizer.paths.os.sep", "\\"), \
             patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase):
            detail = _organize_detail(
                source=Path("e:\\Data\\AMF\\2024 - Marlon Hoffstadt - AMF.mkv"),
                target=Path("E:\\Data\\AMF\\2024 - Marlon Hoffstadt - AMF.mkv"),
                output_root=Path("E:\\Data"),
                action="rename",
                dry_run=True,
            )
        assert detail == "already at target"
