import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from festival_organizer.executor import execute_actions, resolve_collision
from festival_organizer.models import FileAction, MediaFile


def _make_action(source: Path, target: Path, action: str = "move") -> FileAction:
    mf = MediaFile(source_path=source)
    return FileAction(source=source, target=target, media_file=mf, action=action)


def test_execute_move():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "source.mkv"
        src.write_text("video data")
        target = root / "dest" / "output.mkv"

        action = _make_action(src, target, "move")
        results = execute_actions([action])

        assert results[0].status == "done"
        assert target.exists()
        assert not src.exists()


def test_execute_copy():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "source.mkv"
        src.write_text("video data")
        target = root / "dest" / "output.mkv"

        action = _make_action(src, target, "copy")
        results = execute_actions([action])

        assert results[0].status == "done"
        assert target.exists()
        assert src.exists()  # Original still present


def test_execute_rename():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "old_name.mkv"
        src.write_text("video data")
        target = root / "new_name.mkv"

        action = _make_action(src, target, "rename")
        results = execute_actions([action])

        assert results[0].status == "done"
        assert target.exists()
        assert not src.exists()


def test_execute_skip_same_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "same.mkv"
        src.write_text("data")

        action = _make_action(src, src)
        results = execute_actions([action])

        assert results[0].status == "skipped"
        assert src.exists()


def test_resolve_collision():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        existing = root / "file.mkv"
        existing.write_text("existing")

        resolved = resolve_collision(existing)
        assert resolved == root / "file (1).mkv"

        # Create the (1) too
        resolved.write_text("collision 1")
        resolved2 = resolve_collision(existing)
        assert resolved2 == root / "file (2).mkv"


def test_resolve_collision_no_conflict():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "new.mkv"
        assert resolve_collision(target) == target


def test_execute_handles_collision():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "source.mkv"
        src.write_text("new data")
        target = root / "dest" / "output.mkv"
        target.parent.mkdir()
        target.write_text("existing data")

        action = _make_action(src, target, "move")
        results = execute_actions([action])

        assert results[0].status == "done"
        # Should have been moved to output (1).mkv
        assert "output (1).mkv" in results[0].target.name


def test_execute_error_handling():
    """Non-existent source should produce error status."""
    action = _make_action(Path("C:/nonexistent.mkv"), Path("C:/out.mkv"))
    results = execute_actions([action])
    assert results[0].status == "error"
    assert results[0].error != ""


def test_keyboard_interrupt_propagates(tmp_path):
    """KeyboardInterrupt during file move propagates, not swallowed."""
    source = tmp_path / "test.mkv"
    source.write_bytes(b"data")
    target = tmp_path / "dest" / "test.mkv"

    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   festival="TML", year="2024", content_type="festival_set")
    action = FileAction(source=source, target=target, action="move", media_file=mf)

    with patch("festival_organizer.executor.shutil.move", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            execute_actions([action])
