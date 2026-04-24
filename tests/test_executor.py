import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from festival_organizer.executor import (
    execute_actions, paths_are_same_file, resolve_collision,
)
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


def test_resolve_collision_ignores_self_on_case_insensitive_fs():
    """Case-only rename: the 'colliding' target IS the source file.

    Simulated by patching Path.samefile so the test also passes on
    case-sensitive filesystems. On Windows/macOS the real samefile
    already reports True for Alok.mkv vs ALOK.mkv.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "alok.mkv"
        source.write_text("x")
        target = root / "ALOK.mkv"
        target.write_text("x")  # stand-in for "target exists because it IS source"

        real_samefile = Path.samefile

        def fake_samefile(self, other):
            if str(self).lower() == str(other).lower():
                return True
            return real_samefile(self, other)

        with patch.object(Path, "samefile", fake_samefile):
            resolved = resolve_collision(target, source=source)

        assert resolved == target
        assert not (root / "ALOK (1).mkv").exists()


def test_resolve_collision_without_source_still_collides():
    """Back-compat: existing callers that don't pass source are unaffected."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        existing = root / "file.mkv"
        existing.write_text("x")
        assert resolve_collision(existing) == root / "file (1).mkv"


def test_paths_are_same_file_identifies_same_inode():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = root / "x.mkv"
        a.write_text("x")
        assert paths_are_same_file(a, a) is True


def test_paths_are_same_file_distinguishes_different_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = root / "x.mkv"
        b = root / "y.mkv"
        a.write_text("x")
        b.write_text("y")
        assert paths_are_same_file(a, b) is False


def test_paths_are_same_file_false_when_target_missing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = root / "x.mkv"
        a.write_text("x")
        assert paths_are_same_file(a, root / "missing.mkv") is False


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
    action = _make_action(Path("/tmp/test/nonexistent.mkv"), Path("/tmp/test/out.mkv"))
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


def test_execute_actions_logs_warning_on_oserror(tmp_path, caplog):
    """File action OSError is logged WARNING with src, target, and exception."""
    import logging
    source = tmp_path / "test.mkv"
    source.write_bytes(b"data")
    target = tmp_path / "dest" / "test.mkv"

    mf = MediaFile(source_path=Path("test.mkv"), artist="Test",
                   festival="TML", year="2024", content_type="festival_set")
    action = FileAction(source=source, target=target, action="move", media_file=mf)

    with patch("festival_organizer.executor.shutil.move",
               side_effect=OSError("permission denied")):
        with caplog.at_level(logging.WARNING, logger="festival_organizer.executor"):
            result = execute_actions([action])

    assert result[0].status == "error"
    assert "permission denied" in result[0].error
    joined = "\n".join(r.message for r in caplog.records)
    assert "File action failed" in joined
    assert "permission denied" in joined
    assert "test.mkv" in joined
