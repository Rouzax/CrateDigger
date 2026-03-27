import tempfile
from pathlib import Path
from festival_organizer.scanner import scan_folder
from festival_organizer.config import Config, DEFAULT_CONFIG

CFG = Config(DEFAULT_CONFIG)


def test_scan_finds_media_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "video.mkv").touch()
        (root / "audio.mp3").touch()
        (root / "readme.txt").touch()
        (root / "image.jpg").touch()
        files = scan_folder(root, CFG)
        names = {f.name for f in files}
        assert "video.mkv" in names
        assert "audio.mp3" in names
        assert "readme.txt" not in names
        assert "image.jpg" not in names


def test_scan_recursive():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sub = root / "sub" / "deep"
        sub.mkdir(parents=True)
        (sub / "nested.mkv").touch()
        files = scan_folder(root, CFG)
        assert len(files) == 1
        assert files[0].name == "nested.mkv"


def test_scan_skips_bdmv():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bdmv = root / "Dolby" / "BDMV" / "STREAM"
        bdmv.mkdir(parents=True)
        (bdmv / "00001.m2ts").touch()
        (root / "good.mkv").touch()
        files = scan_folder(root, CFG)
        names = {f.name for f in files}
        assert "good.mkv" in names
        assert "00001.m2ts" not in names


def test_scan_skips_dolby_pattern():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dolby = root / "Dolby.UHD.Demo"
        dolby.mkdir()
        (dolby / "demo.mkv").touch()
        (root / "good.mkv").touch()
        files = scan_folder(root, CFG)
        names = {f.name for f in files}
        assert "good.mkv" in names
        assert "demo.mkv" not in names


def test_scan_empty_folder():
    with tempfile.TemporaryDirectory() as tmp:
        assert scan_folder(Path(tmp), CFG) == []


def test_scan_folder_permission_denied(tmp_path):
    """Scanner skips unreadable directories instead of crashing."""
    import os

    from festival_organizer.config import load_config

    config = load_config()

    # Create a readable file and an unreadable subdirectory
    (tmp_path / "good.mkv").write_bytes(b"")
    bad_dir = tmp_path / "noaccess"
    bad_dir.mkdir()
    (bad_dir / "hidden.mkv").write_bytes(b"")
    os.chmod(bad_dir, 0o000)

    try:
        files = scan_folder(tmp_path, config)
        # Should find the good file without crashing
        assert any("good.mkv" in str(f) for f in files)
    finally:
        os.chmod(bad_dir, 0o755)
