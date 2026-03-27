import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from festival_organizer.artwork import extract_cover
from festival_organizer.metadata import _find_mkvtoolnix_tool


def test_find_mkvextract():
    with patch("os.path.isfile", side_effect=lambda p: "MKVToolNix" in p):
        result = _find_mkvtoolnix_tool("mkvextract")
        assert result is not None
        assert "mkvextract" in result.lower()


def test_find_mkvextract_not_installed():
    with patch("shutil.which", return_value=None):
        with patch("os.path.isfile", return_value=False):
            assert _find_mkvtoolnix_tool("mkvextract") is None


def test_extract_cover_no_tool(tmp_path):
    """Should return None if mkvextract is not available."""
    with patch("festival_organizer.metadata.MKVEXTRACT_PATH", None):
        result = extract_cover(Path("test.mkv"), tmp_path)
        assert result is None


def test_extract_cover_success(tmp_path):
    """Should call mkvextract and return poster path on success."""
    source = tmp_path / "source.mkv"
    source.touch()
    target_dir = tmp_path / "output"
    target_dir.mkdir()

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("festival_organizer.metadata.MKVEXTRACT_PATH", "mkvextract"):
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            # Simulate that the file was created by mkvextract
            poster = target_dir / "poster.png"
            poster.touch()

            result = extract_cover(source, target_dir)
            assert result == poster
            mock_run.assert_called_once()


def test_extract_cover_no_attachment(tmp_path):
    """Should return None if mkvextract produces no file."""
    source = tmp_path / "source.mkv"
    source.touch()
    target_dir = tmp_path / "output"
    target_dir.mkdir()

    mock_result = MagicMock()
    mock_result.returncode = 1

    with patch("festival_organizer.metadata.MKVEXTRACT_PATH", "mkvextract"):
        with patch("subprocess.run", return_value=mock_result):
            result = extract_cover(source, target_dir)
            assert result is None
