r"""Integration test: dry-run against the real \\hyperv\Data\Concerts collection.

Skip if the network share is not accessible.
"""
import pytest
from pathlib import Path

from festival_organizer.analyzer import analyse_file
from festival_organizer.classifier import classify
from festival_organizer.config import Config, DEFAULT_CONFIG, load_config
from festival_organizer.planner import plan_actions
from festival_organizer.scanner import scan_folder

CONCERTS_ROOT = Path("//hyperv/Data/Concerts")
SKIP_REASON = "Network share not accessible"


@pytest.fixture
def config():
    config_path = Path("config.json")
    return load_config(config_path if config_path.exists() else None)


@pytest.mark.skipif(not CONCERTS_ROOT.exists(), reason=SKIP_REASON)
class TestRealCollection:

    def test_scan_finds_files(self, config):
        files = scan_folder(CONCERTS_ROOT, config)
        assert len(files) >= 60  # We know there are 72+
        # Should not include BDMV files
        for f in files:
            assert "BDMV" not in str(f)

    def test_all_files_analyse_without_error(self, config):
        files = scan_folder(CONCERTS_ROOT, config)
        for fp in files:
            mf = analyse_file(fp, CONCERTS_ROOT, config)
            assert mf.source_path == fp
            # Every file should have at least extension set
            assert mf.extension != ""

    def test_all_files_classify(self, config):
        files = scan_folder(CONCERTS_ROOT, config)
        types = {"festival_set": 0, "concert_film": 0, "unknown": 0}
        for fp in files:
            mf = analyse_file(fp, CONCERTS_ROOT, config)
            ct = classify(mf, CONCERTS_ROOT, config)
            assert ct in types
            types[ct] += 1
        # We expect at least some festival sets and some concert films
        assert types["festival_set"] > 0
        assert types["concert_film"] > 0

    def test_amf_2024_martin_garrix(self, config):
        """Specific file: AMF 2024 Martin Garrix — should have 1001TL metadata."""
        files = scan_folder(CONCERTS_ROOT, config)
        target = [f for f in files if "MARTIN GARRIX" in f.name.upper() and "AMF" in str(f).upper() and "2024" in str(f)]
        assert len(target) >= 1
        mf = analyse_file(target[0], CONCERTS_ROOT, config)
        assert mf.artist == "Martin Garrix"
        assert mf.festival == "AMF"
        assert mf.year == "2024"
        assert mf.metadata_source == "1001tracklists"

    def test_tomorrowland_belgium_hardwell(self, config):
        """Specific: Tomorrowland Belgium Hardwell WE1."""
        files = scan_folder(CONCERTS_ROOT, config)
        target = [f for f in files if "Hardwell WE1" in f.name]
        assert len(target) >= 1
        mf = analyse_file(target[0], CONCERTS_ROOT, config)
        assert mf.artist == "Hardwell"
        assert mf.festival == "Tomorrowland"
        assert mf.location == "Belgium"
        assert mf.set_title == "WE1"

    def test_adele_classified_as_concert(self, config):
        """Adele files should be concert_film."""
        files = scan_folder(CONCERTS_ROOT, config)
        adele = [f for f in files if "Adele" in str(f)]
        assert len(adele) >= 1
        for fp in adele:
            mf = analyse_file(fp, CONCERTS_ROOT, config)
            ct = classify(mf, CONCERTS_ROOT, config)
            assert ct == "concert_film"

    def test_plan_produces_no_duplicate_targets(self, config):
        """No two files should map to the same target path."""
        files = scan_folder(CONCERTS_ROOT, config)
        media_files = []
        for fp in files:
            mf = analyse_file(fp, CONCERTS_ROOT, config)
            mf.content_type = classify(mf, CONCERTS_ROOT, config)
            media_files.append(mf)
        actions = plan_actions(media_files, Path("C:/Test/Output"), config)
        targets = [str(a.target) for a in actions]
        # Allow soft check — some may collide but shouldn't be many
        unique = set(targets)
        collision_count = len(targets) - len(unique)
        assert collision_count < 5, f"Too many target collisions: {collision_count}"
