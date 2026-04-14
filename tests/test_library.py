import json
import logging
import os
from pathlib import Path
from festival_organizer.library import (
    find_library_root, init_library, cleanup_empty_dirs,
    migrate_folder_artefacts,
)


def test_find_library_root_at_path(tmp_path):
    """Find .cratedigger/ marker at the given path."""
    marker = tmp_path / ".cratedigger"
    marker.mkdir()
    assert find_library_root(tmp_path) == tmp_path


def test_find_library_root_walks_up(tmp_path):
    """Walk up from subfolder to find .cratedigger/ marker."""
    marker = tmp_path / ".cratedigger"
    marker.mkdir()
    sub = tmp_path / "Artist" / "Festival"
    sub.mkdir(parents=True)
    assert find_library_root(sub) == tmp_path


def test_find_library_root_returns_none(tmp_path):
    """Return None when no marker found."""
    sub = tmp_path / "some" / "deep" / "path"
    sub.mkdir(parents=True)
    assert find_library_root(sub) is None


def test_find_library_root_stops_at_filesystem_root(tmp_path):
    """Don't walk above filesystem boundaries."""
    result = find_library_root(tmp_path)
    assert result is None


def test_init_library_creates_marker(tmp_path):
    """init_library creates .cratedigger/ directory."""
    init_library(tmp_path)
    assert (tmp_path / ".cratedigger").is_dir()


def test_init_library_creates_config(tmp_path):
    """init_library creates config.json with layout."""
    init_library(tmp_path, layout="festival_flat")
    cfg = json.loads((tmp_path / ".cratedigger" / "config.json").read_text())
    assert cfg["default_layout"] == "festival_flat"


def test_init_library_idempotent(tmp_path):
    """Running init_library twice doesn't overwrite existing config."""
    init_library(tmp_path, layout="festival_flat")
    # Manually add a custom setting
    cfg_path = tmp_path / ".cratedigger" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["custom_key"] = "custom_value"
    cfg_path.write_text(json.dumps(cfg))
    # Re-init should not clobber
    init_library(tmp_path, layout="artist_flat")
    cfg = json.loads(cfg_path.read_text())
    assert cfg["custom_key"] == "custom_value"


def test_find_library_root_config_dir(tmp_path):
    """find_library_root returns path from real subfolder."""
    init_library(tmp_path, layout="artist_nested")
    # From a real subfolder:
    sub = tmp_path / "Artist"
    sub.mkdir()
    root = find_library_root(sub)
    assert root == tmp_path


# ── cleanup_empty_dirs tests ──────────────────────────────────────────


class TestCleanupEmptyDirs:
    """Tests for cleanup_empty_dirs()."""

    def test_removes_empty_leaf_dir(self, tmp_path):
        """An empty subdirectory is removed."""
        empty = tmp_path / "Artist" / "Festival"
        empty.mkdir(parents=True)
        cleanup_empty_dirs(tmp_path)
        assert not empty.exists()
        assert not (tmp_path / "Artist").exists()

    def test_preserves_root(self, tmp_path):
        """The root directory itself is never removed, even when empty."""
        cleanup_empty_dirs(tmp_path)
        assert tmp_path.exists()

    def test_preserves_non_empty_dir(self, tmp_path):
        """Directories containing real files are kept."""
        d = tmp_path / "Artist"
        d.mkdir()
        (d / "set.mkv").write_text("video")
        cleanup_empty_dirs(tmp_path)
        assert d.exists()
        assert (d / "set.mkv").exists()

    def test_removes_junk_files_then_empty_dir(self, tmp_path):
        """Dirs containing only junk files (.DS_Store, Thumbs.db) are treated as empty."""
        d = tmp_path / "Artist"
        d.mkdir()
        (d / ".DS_Store").write_text("junk")
        (d / "Thumbs.db").write_text("junk")
        cleanup_empty_dirs(tmp_path)
        assert not d.exists()

    def test_removes_desktop_ini(self, tmp_path):
        """desktop.ini is also treated as junk."""
        d = tmp_path / "Folder"
        d.mkdir()
        (d / "desktop.ini").write_text("junk")
        cleanup_empty_dirs(tmp_path)
        assert not d.exists()

    def test_preserves_dir_with_unknown_hidden_file(self, tmp_path, caplog):
        """Unknown hidden files prevent cleanup; a WARNING is logged."""
        d = tmp_path / "Artist"
        d.mkdir()
        (d / ".custom_hidden").write_text("keep me")
        with caplog.at_level(logging.WARNING):
            cleanup_empty_dirs(tmp_path)
        assert d.exists()
        assert ".custom_hidden" in caplog.text

    def test_removes_orphaned_folder_sidecars(self, tmp_path):
        """folder.jpg without media files is removed."""
        d = tmp_path / "Artist" / "Festival"
        d.mkdir(parents=True)
        (d / "folder.jpg").write_bytes(b"\xff\xd8")
        cleanup_empty_dirs(tmp_path)
        assert not d.exists()
        assert not (tmp_path / "Artist").exists()

    def test_preserves_folder_sidecars_when_media_exists(self, tmp_path):
        """folder.jpg is kept when there are media files in the dir."""
        d = tmp_path / "Artist"
        d.mkdir()
        (d / "folder.jpg").write_bytes(b"\xff\xd8")
        (d / "set.mkv").write_text("video")
        cleanup_empty_dirs(tmp_path)
        assert d.exists()
        assert (d / "folder.jpg").exists()

    def test_never_removes_cratedigger_dir(self, tmp_path):
        """.cratedigger directory is always preserved."""
        marker = tmp_path / ".cratedigger"
        marker.mkdir()
        (marker / "config.json").write_text("{}")
        cleanup_empty_dirs(tmp_path)
        assert marker.exists()

    def test_never_removes_empty_cratedigger_dir(self, tmp_path):
        """.cratedigger is preserved even when empty."""
        marker = tmp_path / ".cratedigger"
        marker.mkdir()
        cleanup_empty_dirs(tmp_path)
        assert marker.exists()

    def test_preserves_ancestor_of_cratedigger(self, tmp_path):
        """Dirs that are ancestors of .cratedigger are never removed."""
        # root/.cratedigger exists, root is the ancestor — already covered by root preservation
        # But also check a nested .cratedigger scenario
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / ".cratedigger").mkdir()
        cleanup_empty_dirs(tmp_path)
        assert sub.exists()

    def test_permission_error_logged_and_continues(self, tmp_path, caplog):
        """Permission errors on a directory log WARNING and don't abort."""
        d1 = tmp_path / "dir1"
        d2 = tmp_path / "dir2"
        d1.mkdir()
        d2.mkdir()
        # Make dir1 non-removable by removing write permission on parent
        # We'll use a nested structure to trigger the error
        nested = d1 / "locked"
        nested.mkdir()
        os.chmod(str(d1), 0o555)
        try:
            with caplog.at_level(logging.WARNING):
                cleanup_empty_dirs(tmp_path)
            # dir2 should still be cleaned up despite dir1 error
            assert not d2.exists()
            assert "WARNING" in caplog.text or "Permission" in caplog.text or "locked" in caplog.text
        finally:
            os.chmod(str(d1), 0o755)

    def test_logs_what_prevented_cleanup(self, tmp_path, caplog):
        """When a dir is not empty due to user files, log what prevented cleanup."""
        d = tmp_path / "Artist"
        d.mkdir()
        (d / "notes.txt").write_text("keep me")
        with caplog.at_level(logging.DEBUG, logger="festival_organizer.library"):
            cleanup_empty_dirs(tmp_path)
        assert d.exists()
        assert "notes.txt" in caplog.text

    def test_nested_empty_dirs_removed_bottom_up(self, tmp_path):
        """Deeply nested empty dirs are all removed."""
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        cleanup_empty_dirs(tmp_path)
        assert not (tmp_path / "a").exists()

    def test_mixed_tree(self, tmp_path):
        """In a tree with both empty and non-empty branches, only empty ones are removed."""
        # Empty branch
        (tmp_path / "empty" / "sub").mkdir(parents=True)
        # Non-empty branch
        keep = tmp_path / "keep" / "sub"
        keep.mkdir(parents=True)
        (keep / "file.mkv").write_text("video")
        cleanup_empty_dirs(tmp_path)
        assert not (tmp_path / "empty").exists()
        assert keep.exists()
        assert (keep / "file.mkv").exists()

    def test_junk_plus_sidecar_no_media(self, tmp_path):
        """Dir with only junk + orphaned sidecars and no media is removed."""
        d = tmp_path / "Festival"
        d.mkdir()
        (d / ".DS_Store").write_text("junk")
        (d / "folder.jpg").write_bytes(b"\xff\xd8")
        cleanup_empty_dirs(tmp_path)
        assert not d.exists()


# ── find_library_root with non-existent paths ───────────────────────────


def test_find_library_root_nonexistent_start_walks_up(tmp_path):
    """When start_path doesn't exist, walk up from nearest existing ancestor."""
    marker = tmp_path / ".cratedigger"
    marker.mkdir()
    # The start path doesn't exist yet (e.g. output dir to be created)
    nonexistent = tmp_path / "future" / "output"
    assert not nonexistent.exists()
    assert find_library_root(nonexistent) == tmp_path


def test_find_library_root_nonexistent_no_marker(tmp_path):
    """Non-existent start path with no marker anywhere returns None."""
    nonexistent = tmp_path / "no" / "marker" / "here"
    assert find_library_root(nonexistent) is None


# ── resolve_library_root tests ──────────────────────────────────────────


from festival_organizer.library import resolve_library_root


def test_resolve_library_root_output_wins_over_source(tmp_path):
    """When both source and output have .cratedigger, output wins."""
    source = tmp_path / "source"
    source.mkdir()
    (source / ".cratedigger").mkdir()

    output = tmp_path / "output"
    output.mkdir()
    (output / ".cratedigger").mkdir()

    result = resolve_library_root(source=source, output=output)
    assert result == output


def test_resolve_library_root_falls_back_to_source(tmp_path):
    """When only source has .cratedigger, use that."""
    source = tmp_path / "source"
    source.mkdir()
    (source / ".cratedigger").mkdir()

    output = tmp_path / "output"
    output.mkdir()

    result = resolve_library_root(source=source, output=output)
    assert result == source


def test_resolve_library_root_output_only(tmp_path):
    """When only output has .cratedigger, use that."""
    source = tmp_path / "source"
    source.mkdir()

    output = tmp_path / "output"
    output.mkdir()
    (output / ".cratedigger").mkdir()

    result = resolve_library_root(source=source, output=output)
    assert result == output


def test_resolve_library_root_no_output(tmp_path):
    """When no output is given, search source only (existing behavior)."""
    source = tmp_path / "source"
    source.mkdir()
    (source / ".cratedigger").mkdir()

    result = resolve_library_root(source=source, output=None)
    assert result == source


def test_resolve_library_root_neither(tmp_path):
    """When neither has .cratedigger, return None."""
    source = tmp_path / "source"
    source.mkdir()

    result = resolve_library_root(source=source, output=None)
    assert result is None


def test_resolve_library_root_output_nonexistent(tmp_path):
    """When output doesn't exist yet, walk up from its parent."""
    library = tmp_path / "library"
    library.mkdir()
    (library / ".cratedigger").mkdir()

    source = tmp_path / "source"
    source.mkdir()

    # Output is a subdir that doesn't exist yet
    output = library / "new_subdir"
    assert not output.exists()

    result = resolve_library_root(source=source, output=output)
    assert result == library


# ── migrate_folder_artefacts tests ────────────────────────────────────


def test_migrate_folder_artefacts_moves_files_to_target(tmp_path):
    """When a video has been moved to a new folder and the source folder no
    longer contains any videos, folder.jpg / fanart.jpg follow to the target
    folder. This is the festival_flat alias-change scenario."""
    old_dir = tmp_path / "UMF Miami"
    new_dir = tmp_path / "Ultra Music Festival Miami"
    old_dir.mkdir()
    new_dir.mkdir()
    # Video + per-file sidecars already moved by OrganizeOperation._move_sidecars
    (new_dir / "2026 - Eric Prydz.mkv").write_bytes(b"video")
    (new_dir / "2026 - Eric Prydz.nfo").write_text("<nfo/>")
    # Folder-level artefacts left behind in old_dir
    (old_dir / "folder.jpg").write_bytes(b"\xff\xd8folder")
    (old_dir / "fanart.jpg").write_bytes(b"\xff\xd8fanart")

    migrate_folder_artefacts([(old_dir, new_dir)], video_exts={".mkv", ".mp4"})

    assert (new_dir / "folder.jpg").read_bytes() == b"\xff\xd8folder"
    assert (new_dir / "fanart.jpg").read_bytes() == b"\xff\xd8fanart"
    assert not (old_dir / "folder.jpg").exists()
    assert not (old_dir / "fanart.jpg").exists()


def test_migrate_folder_artefacts_noop_when_source_still_has_videos(tmp_path):
    """If the source folder still contains other videos, don't steal its
    folder-level artefacts — they still belong to that folder."""
    old_dir = tmp_path / "Shared"
    new_dir = tmp_path / "Moved"
    old_dir.mkdir()
    new_dir.mkdir()
    (new_dir / "moved.mkv").write_bytes(b"video")
    # Another video stayed in old_dir
    (old_dir / "stayed.mkv").write_bytes(b"video")
    (old_dir / "folder.jpg").write_bytes(b"\xff\xd8")

    migrate_folder_artefacts([(old_dir, new_dir)], video_exts={".mkv"})

    assert (old_dir / "folder.jpg").exists()
    assert not (new_dir / "folder.jpg").exists()


def test_migrate_folder_artefacts_noop_when_same_dir(tmp_path):
    """Rename that stays inside the same folder (artist_flat, artist unchanged)
    must not touch folder-level artefacts."""
    same_dir = tmp_path / "Eric Prydz"
    same_dir.mkdir()
    (same_dir / "2026.mkv").write_bytes(b"video")
    (same_dir / "folder.jpg").write_bytes(b"\xff\xd8")

    migrate_folder_artefacts([(same_dir, same_dir)], video_exts={".mkv"})

    assert (same_dir / "folder.jpg").exists()


def test_migrate_folder_artefacts_target_overwrite_preserves_target(tmp_path):
    """If the target folder already has a folder.jpg (e.g. prior enrich run),
    don't overwrite it. The new folder's existing artefact is authoritative."""
    old_dir = tmp_path / "Old"
    new_dir = tmp_path / "New"
    old_dir.mkdir()
    new_dir.mkdir()
    (new_dir / "moved.mkv").write_bytes(b"video")
    (old_dir / "folder.jpg").write_bytes(b"old")
    (new_dir / "folder.jpg").write_bytes(b"new")

    migrate_folder_artefacts([(old_dir, new_dir)], video_exts={".mkv"})

    assert (new_dir / "folder.jpg").read_bytes() == b"new"
    assert not (old_dir / "folder.jpg").exists()  # source still got cleaned
