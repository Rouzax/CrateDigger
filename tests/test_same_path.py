"""Tests for same_library_path drive-letter-aware comparison."""
from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest.mock import patch

import pytest

from festival_organizer.paths import same_library_path


def _win_normcase(s: str) -> str:
    """Simulate Windows os.path.normcase: lowercase and backslash-normalize."""
    return s.replace("/", "\\").lower()


class TestSameLibraryPath:
    """Cases that exercise both the library-root split and the fallback."""

    def test_identical_paths(self):
        """Identical paths are always the same."""
        a = Path("/data/lib/Fest/Alok/set.mkv")
        b = Path("/data/lib/Fest/Alok/set.mkv")
        root = Path("/data/lib")
        assert same_library_path(a, b, root) is True

    def test_different_filenames(self):
        """Different filenames are never the same."""
        a = Path("/data/lib/Fest/Alok/set1.mkv")
        b = Path("/data/lib/Fest/Alok/set2.mkv")
        root = Path("/data/lib")
        assert same_library_path(a, b, root) is False

    @patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase)
    @patch("festival_organizer.paths.os.sep", "\\")
    def test_directory_case_rename_detected(self, _mock_nc):
        """A case rename inside the library (Alok vs ALOK) must be detected."""
        root = Path("E:\\Data\\Lib")
        a = Path("E:\\Data\\Lib\\Fest\\Alok\\set.mkv")
        b = Path("E:\\Data\\Lib\\Fest\\ALOK\\set.mkv")
        assert same_library_path(a, b, root) is False

    @patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase)
    @patch("festival_organizer.paths.os.sep", "\\")
    def test_drive_letter_case_difference(self, _mock_nc):
        """Drive letter case difference only (e:\\ vs E:\\) should match."""
        root = Path("E:\\Data\\Lib")
        a = Path("e:\\Data\\Lib\\Fest\\Alok\\set.mkv")
        b = Path("E:\\Data\\Lib\\Fest\\Alok\\set.mkv")
        assert same_library_path(a, b, root) is True

    @patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase)
    @patch("festival_organizer.paths.os.sep", "\\")
    def test_drive_letter_case_backslash_style(self, _mock_nc):
        """Drive letter case difference with backslash style paths."""
        root = Path("E:\\Festivals\\Video")
        a = Path("e:\\Festivals\\Video\\Ultra\\DJ Snake\\set.mkv")
        b = Path("E:\\Festivals\\Video\\Ultra\\DJ Snake\\set.mkv")
        assert same_library_path(a, b, root) is True

    @patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase)
    @patch("festival_organizer.paths.os.sep", "\\")
    def test_same_drive_different_path_after_root(self, _mock_nc):
        """Same drive but different relative path after root."""
        root = Path("E:\\Data\\Lib")
        a = Path("E:\\Data\\Lib\\FestA\\Alok\\set.mkv")
        b = Path("E:\\Data\\Lib\\FestB\\Alok\\set.mkv")
        assert same_library_path(a, b, root) is False

    @patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase)
    @patch("festival_organizer.paths.os.sep", "\\")
    def test_unc_paths_same(self, _mock_nc):
        """UNC paths that are identical should match."""
        root = Path("\\\\server\\share\\lib")
        a = Path("\\\\server\\share\\lib\\Fest\\Alok\\set.mkv")
        b = Path("\\\\server\\share\\lib\\Fest\\Alok\\set.mkv")
        assert same_library_path(a, b, root) is True

    def test_posix_paths_no_drive(self):
        """POSIX paths with no drive letter, identical, should match."""
        a = Path("/mnt/media/lib/Fest/Alok/set.mkv")
        b = Path("/mnt/media/lib/Fest/Alok/set.mkv")
        root = Path("/mnt/media/lib")
        assert same_library_path(a, b, root) is True

    def test_posix_case_sensitive(self):
        """On POSIX, normcase is a no-op; different case in prefix is different."""
        a = Path("/mnt/Media/lib/Fest/Alok/set.mkv")
        b = Path("/mnt/media/lib/Fest/Alok/set.mkv")
        root = Path("/mnt/media/lib")
        # 'a' is not under root (case mismatch), so fallback fires.
        # normcase is identity on POSIX, so the two full paths differ.
        assert same_library_path(a, b, root) is False

    @patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase)
    @patch("festival_organizer.paths.os.sep", "\\")
    def test_full_prefix_case_difference_same_relative(self, _mock_nc):
        """Prefix differs in case (e:\\data\\lib vs E:\\Data\\Lib) but relative
        path is identical, so they are the same file."""
        root = Path("E:\\Data\\Lib")
        a = Path("e:\\data\\lib\\Fest\\Alok\\set.mkv")
        b = Path("E:\\Data\\Lib\\Fest\\Alok\\set.mkv")
        assert same_library_path(a, b, root) is True

    @patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase)
    @patch("festival_organizer.paths.os.sep", "\\")
    def test_neither_path_under_root(self, _mock_nc):
        """When neither path is under root, fallback to full normcase comparison."""
        root = Path("E:\\Data\\Lib")
        a = Path("D:\\Other\\file.mkv")
        b = Path("d:\\other\\file.mkv")
        # normcase makes both lowercase, so they match.
        assert same_library_path(a, b, root) is True

    @patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase)
    @patch("festival_organizer.paths.os.sep", "\\")
    def test_only_one_path_under_root(self, _mock_nc):
        """When only one path is under root, fallback to full normcase."""
        root = Path("E:\\Data\\Lib")
        a = Path("E:\\Data\\Lib\\Fest\\set.mkv")
        b = Path("D:\\Other\\set.mkv")
        # Full normcase comparison: these are clearly different.
        assert same_library_path(a, b, root) is False
