"""Tests for legacy-path warning on CLI startup."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from festival_organizer import paths


class TestLegacyWarning:
    def test_warn_if_legacy_paths_exist_emits_one_warning(self, tmp_path: Path, caplog):
        legacy = tmp_path / ".cratedigger"
        legacy.mkdir()
        (legacy / "config.json").write_text("{}")
        state = tmp_path / "state"
        with patch("festival_organizer.paths.state_dir", return_value=state), \
             caplog.at_level("WARNING", logger="festival_organizer.paths"):
            paths.warn_if_legacy_paths_exist(home=tmp_path)
        ours = [r for r in caplog.records if r.name == "festival_organizer.paths"]
        assert len(ours) == 1
        assert "legacy" in ours[0].getMessage().lower()
