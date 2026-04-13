"""Tests for wiring ChapterMbidsOperation into the enrich CLI pipeline.

These tests verify observable behaviour (the ops list passed to
run_pipeline) rather than internal dispatch details.
"""
from unittest.mock import patch, MagicMock

from festival_organizer.cli import run
from festival_organizer.operations import (
    ChapterMbidsOperation,
    NfoOperation,
    TagsOperation,
)


def _run_enrich_and_capture_ops(tmp_path, extra_args=None):
    """Invoke `enrich` against a fake library and return the ops for file 0.

    Patches scanning / analysis / pipeline so the CLI builds the ops list
    but never actually executes operations.
    """
    lib = tmp_path / "concerts"
    (lib / ".cratedigger").mkdir(parents=True)
    fake_file = lib / "test.mkv"
    fake_file.touch()

    mock_mf = MagicMock()
    mock_mf.content_type = "festival_set"
    mock_mf.festival = "TestFest"
    mock_mf.artist = "TestArtist"
    mock_mf.source_path = fake_file

    captured = {}

    def fake_run_pipeline(pipeline_files, progress):
        captured["pipeline_files"] = pipeline_files
        return []

    args = ["enrich", str(lib)]
    if extra_args:
        args.extend(extra_args)

    with patch("festival_organizer.cli.resolve_library_root", return_value=lib):
        with patch("festival_organizer.cli.scan_folder", return_value=[fake_file]):
            with patch("festival_organizer.cli._analyse_parallel",
                       return_value=[(fake_file, mock_mf)]):
                with patch("festival_organizer.cli.run_pipeline",
                           side_effect=fake_run_pipeline):
                    run(args)

    pipeline_files = captured.get("pipeline_files", [])
    assert pipeline_files, "run_pipeline was not called with any files"
    # pipeline_files is a list of (fp, mf, ops)
    return pipeline_files[0][2]


def test_enrich_default_includes_chapter_mbids_op(tmp_path):
    """Default enrich (no --only) appends a ChapterMbidsOperation."""
    ops = _run_enrich_and_capture_ops(tmp_path)
    assert any(isinstance(op, ChapterMbidsOperation) for op in ops), \
        f"expected ChapterMbidsOperation in default enrich ops; got {[type(o).__name__ for o in ops]}"


def test_enrich_only_chapter_mbids_selects_only_that_op(tmp_path):
    """--only chapter_mbids includes the op and excludes others."""
    ops = _run_enrich_and_capture_ops(tmp_path, ["--only", "chapter_mbids"])
    types = [type(op) for op in ops]
    assert ChapterMbidsOperation in types
    assert NfoOperation not in types
    assert TagsOperation not in types


def test_enrich_only_tags_excludes_chapter_mbids(tmp_path):
    """--only tags must not include ChapterMbidsOperation."""
    ops = _run_enrich_and_capture_ops(tmp_path, ["--only", "tags"])
    types = [type(op) for op in ops]
    assert TagsOperation in types
    assert ChapterMbidsOperation not in types


def test_enrich_regenerate_propagates_force_to_chapter_mbids(tmp_path):
    """--regenerate sets force=True on the ChapterMbidsOperation instance."""
    ops = _run_enrich_and_capture_ops(tmp_path, ["--regenerate"])
    chapter_ops = [op for op in ops if isinstance(op, ChapterMbidsOperation)]
    assert chapter_ops, "ChapterMbidsOperation missing when --regenerate is set"
    assert chapter_ops[0].force is True
