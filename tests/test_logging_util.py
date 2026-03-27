import csv
import io
import tempfile
from pathlib import Path
from festival_organizer.logging_util import ActionLogger
from festival_organizer.models import FileAction, MediaFile


def test_logger_records_actions():
    logger = ActionLogger(verbose=False)
    mf = MediaFile(source_path=Path("src.mkv"), artist="Test", festival="AMF", year="2024")
    fa = FileAction(source=Path("src.mkv"), target=Path("dst.mkv"), media_file=mf, status="done")
    logger.log_action(fa)
    assert len(logger.rows) == 1
    assert logger.rows[0]["status"] == "done"


def test_logger_stats():
    logger = ActionLogger(verbose=False)
    mf = MediaFile(source_path=Path("a.mkv"))
    logger.log_action(FileAction(source=Path("a"), target=Path("b"), media_file=mf, status="done"))
    logger.log_action(FileAction(source=Path("c"), target=Path("d"), media_file=mf, status="error", error="oops"))
    logger.log_action(FileAction(source=Path("e"), target=Path("f"), media_file=mf, status="done"))
    stats = logger.stats
    assert stats["done"] == 2
    assert stats["error"] == 1


def test_logger_save_csv():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "test.csv"
        logger = ActionLogger(verbose=False)
        mf = MediaFile(source_path=Path("src.mkv"), artist="Martin Garrix", festival="AMF", year="2024")
        fa = FileAction(source=Path("src.mkv"), target=Path("dst.mkv"), media_file=mf, status="done")
        logger.log_action(fa)
        logger.save_csv(log_path)

        assert log_path.exists()
        with open(log_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["artist"] == "Martin Garrix"
        assert rows[0]["status"] == "done"
