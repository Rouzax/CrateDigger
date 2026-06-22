"""Tests for same_library_path drive-letter-aware comparison."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from festival_organizer.paths import same_library_path


def _win_normcase(s: str) -> str:
    """Simulate Windows os.path.normcase: lowercase and backslash-normalize."""
    return s.replace("/", "\\").lower()


@pytest.fixture()
def _win_paths():
    """Patch os.path.normcase and os.sep to simulate Windows semantics."""
    with (
        patch("festival_organizer.paths.os.path.normcase", side_effect=_win_normcase),
        patch("festival_organizer.paths.os.sep", "\\"),
    ):
        yield


class TestPosix:
    """Cases that run with native POSIX path semantics (no mocking)."""

    def test_identical_paths(self):
        a = Path("/data/lib/Fest/Alok/set.mkv")
        root = Path("/data/lib")
        assert same_library_path(a, a, root) is True

    def test_different_filenames(self):
        a = Path("/data/lib/Fest/Alok/set1.mkv")
        b = Path("/data/lib/Fest/Alok/set2.mkv")
        root = Path("/data/lib")
        assert same_library_path(a, b, root) is False

    def test_posix_case_sensitive(self):
        """On POSIX, normcase is a no-op; different case in prefix is different."""
        a = Path("/mnt/Media/lib/Fest/Alok/set.mkv")
        b = Path("/mnt/media/lib/Fest/Alok/set.mkv")
        root = Path("/mnt/media/lib")
        assert same_library_path(a, b, root) is False


@pytest.mark.usefixtures("_win_paths")
class TestWindows:
    """Cases that simulate Windows path semantics via mocked normcase/sep."""

    def test_directory_case_rename_detected(self):
        """Case rename inside library (Alok vs ALOK) must be detected."""
        root = Path("E:\\Data\\Lib")
        a = Path("E:\\Data\\Lib\\Fest\\Alok\\set.mkv")
        b = Path("E:\\Data\\Lib\\Fest\\ALOK\\set.mkv")
        assert same_library_path(a, b, root) is False

    def test_drive_letter_case(self):
        """e:\\ vs E:\\ is the same volume."""
        root = Path("E:\\Data\\Lib")
        a = Path("e:\\Data\\Lib\\Fest\\Alok\\set.mkv")
        b = Path("E:\\Data\\Lib\\Fest\\Alok\\set.mkv")
        assert same_library_path(a, b, root) is True

    def test_drive_letter_case_backslash(self):
        root = Path("E:\\Festivals\\Video")
        a = Path("e:\\Festivals\\Video\\Ultra\\DJ Snake\\set.mkv")
        b = Path("E:\\Festivals\\Video\\Ultra\\DJ Snake\\set.mkv")
        assert same_library_path(a, b, root) is True

    def test_same_drive_different_relative(self):
        root = Path("E:\\Data\\Lib")
        a = Path("E:\\Data\\Lib\\FestA\\Alok\\set.mkv")
        b = Path("E:\\Data\\Lib\\FestB\\Alok\\set.mkv")
        assert same_library_path(a, b, root) is False

    def test_unc_paths(self):
        root = Path("\\\\server\\share\\lib")
        a = Path("\\\\server\\share\\lib\\Fest\\Alok\\set.mkv")
        b = Path("\\\\server\\share\\lib\\Fest\\Alok\\set.mkv")
        assert same_library_path(a, b, root) is True

    def test_full_prefix_case_difference(self):
        """e:\\data\\lib vs E:\\Data\\Lib with identical relative path."""
        root = Path("E:\\Data\\Lib")
        a = Path("e:\\data\\lib\\Fest\\Alok\\set.mkv")
        b = Path("E:\\Data\\Lib\\Fest\\Alok\\set.mkv")
        assert same_library_path(a, b, root) is True

    def test_neither_under_root(self):
        """Fallback: full normcase comparison when neither path is under root."""
        root = Path("E:\\Data\\Lib")
        a = Path("D:\\Other\\file.mkv")
        b = Path("d:\\other\\file.mkv")
        assert same_library_path(a, b, root) is True

    def test_only_one_under_root(self):
        """Fallback: paths on different volumes are different."""
        root = Path("E:\\Data\\Lib")
        a = Path("E:\\Data\\Lib\\Fest\\set.mkv")
        b = Path("D:\\Other\\set.mkv")
        assert same_library_path(a, b, root) is False
