"""Tests for Kodi JSON-RPC client and library sync."""
from unittest.mock import MagicMock, patch

import pytest

from festival_organizer.kodi import (
    KodiClient, KodiError, sync_library,
    _infer_path_mapping, _translate_path,
)


class TestKodiClient:

    def test_call_sends_jsonrpc_payload(self):
        client = KodiClient("localhost", 8080, "kodi", "pass")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "OK"}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            result = client._call("VideoLibrary.Scan", {"directory": ""})

        assert result == "OK"
        call_args = mock_post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "VideoLibrary.Scan"
        assert payload["params"] == {"directory": ""}
        assert "id" in payload

    def test_call_raises_on_connection_error(self):
        import requests
        client = KodiClient("localhost", 8080, "kodi", "pass")

        with patch.object(client._session, "post",
                          side_effect=requests.ConnectionError("refused")):
            with pytest.raises(KodiError, match="Cannot connect"):
                client._call("VideoLibrary.Scan")

    def test_call_raises_on_rpc_error(self):
        client = KodiClient("localhost", 8080, "kodi", "pass")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp):
            with pytest.raises(KodiError, match="RPC error"):
                client._call("Bogus.Method")

    def test_get_music_videos_stores_paths_as_is(self):
        """Kodi paths (including SMB URLs) are stored verbatim."""
        client = KodiClient("localhost", 8080, "kodi", "pass")
        rpc_result = {
            "musicvideos": [
                {"musicvideoid": 10,
                 "file": "smb://HYPERV/Data/Concerts/Artist/video1.mkv",
                 "label": "v1"},
                {"musicvideoid": 20,
                 "file": "smb://HYPERV/Data/Concerts/Artist/video2.mkv",
                 "label": "v2"},
            ],
        }

        with patch.object(client, "_call", return_value=rpc_result):
            mapping = client.get_music_videos()

        assert len(mapping) == 2
        assert mapping["smb://HYPERV/Data/Concerts/Artist/video1.mkv"] == 10
        assert mapping["smb://HYPERV/Data/Concerts/Artist/video2.mkv"] == 20

    def test_get_music_videos_empty_library(self):
        client = KodiClient("localhost", 8080, "kodi", "pass")

        with patch.object(client, "_call", return_value={}):
            mapping = client.get_music_videos()

        assert mapping == {}

    def test_refresh_music_video_calls_rpc(self):
        client = KodiClient("localhost", 8080, "kodi", "pass")

        with patch.object(client, "_call", return_value="OK") as mock_call:
            client.refresh_music_video(42)

        mock_call.assert_called_once_with("VideoLibrary.RefreshMusicVideo", {
            "musicvideoid": 42,
            "ignorenfo": False,
        })

    def test_clean_calls_rpc(self):
        client = KodiClient("localhost", 8080, "kodi", "pass")

        with patch.object(client, "_call", return_value="OK") as mock_call:
            client.clean()

        mock_call.assert_called_once_with("VideoLibrary.Clean", {
            "content": "musicvideos",
            "showdialogs": False,
        })


class TestInferPathMapping:

    def test_infers_mapping_from_matching_filename(self, tmp_path):
        """Auto-detects prefix pair from a file that exists in both local and Kodi."""
        video = tmp_path / "Concerts" / "ALOK" / "2025 - TML - ALOK.mkv"
        video.parent.mkdir(parents=True)
        video.touch()

        kodi_videos = {
            "smb://HYPERV/Data/Concerts/ALOK/2025 - TML - ALOK.mkv": 10,
        }

        result = _infer_path_mapping([video], kodi_videos)
        assert result is not None
        local_prefix, kodi_prefix = result
        assert local_prefix == str(tmp_path.resolve())
        assert kodi_prefix == "smb://HYPERV/Data"

    def test_infers_mapping_case_insensitive(self, tmp_path):
        """Handles case differences (local 'Afrojack' vs Kodi 'AFROJACK')."""
        video = tmp_path / "Concerts" / "Afrojack" / "video.mkv"
        video.parent.mkdir(parents=True)
        video.touch()

        kodi_videos = {
            "smb://HOST/Concerts/AFROJACK/video.mkv": 10,
        }

        result = _infer_path_mapping([video], kodi_videos)
        assert result is not None
        local_prefix, kodi_prefix = result
        # "Concerts", "Afrojack/AFROJACK", "video.mkv" all match case-insensitive
        assert local_prefix == str(tmp_path.resolve())
        assert kodi_prefix == "smb://HOST"

    def test_returns_none_when_no_match(self, tmp_path):
        video = tmp_path / "unique_file.mkv"
        video.touch()

        result = _infer_path_mapping([video], {"smb://X/other.mkv": 1})
        assert result is None

    def test_returns_none_for_empty_inputs(self):
        assert _infer_path_mapping([], {}) is None
        assert _infer_path_mapping([], {"smb://X/f.mkv": 1}) is None


class TestTranslatePath:

    def test_translates_local_to_kodi(self, tmp_path):
        video = tmp_path / "ALOK" / "video.mkv"
        video.parent.mkdir()
        video.touch()

        kodi_original = "smb://HYPERV/Data/Concerts/ALOK/video.mkv"
        kodi_lookup = {kodi_original.lower(): kodi_original}

        result = _translate_path(
            video,
            str(tmp_path.resolve()),
            "smb://HYPERV/Data/Concerts",
            kodi_lookup,
        )
        assert result == kodi_original

    def test_case_insensitive_folder_match(self, tmp_path):
        """Local 'Afrojack' matches Kodi 'AFROJACK'."""
        video = tmp_path / "Afrojack" / "video.mkv"
        video.parent.mkdir()
        video.touch()

        kodi_original = "smb://HOST/Concerts/AFROJACK/video.mkv"
        kodi_lookup = {kodi_original.lower(): kodi_original}

        result = _translate_path(
            video,
            str(tmp_path.resolve()),
            "smb://HOST/Concerts",
            kodi_lookup,
        )
        assert result == kodi_original

    def test_returns_none_for_outside_prefix(self, tmp_path):
        outside = tmp_path / "other" / "file.mkv"
        outside.parent.mkdir(parents=True)
        outside.touch()

        result = _translate_path(
            outside,
            str((tmp_path / "library").resolve()),
            "smb://X/lib",
            {},
        )
        assert result is None


class TestSyncLibrary:

    def _make_client(self, kodi_files: dict[str, int]):
        """Create a mock KodiClient with given file->id mapping."""
        client = MagicMock(spec=KodiClient)
        client.get_music_videos.return_value = kodi_files
        return client

    def test_auto_infers_mapping_and_refreshes(self, tmp_path):
        """Without explicit path_mapping, auto-detects from filenames."""
        video = tmp_path / "Concerts" / "ALOK" / "video.mkv"
        video.parent.mkdir(parents=True)
        video.touch()

        smb_path = "smb://HYPERV/Data/Concerts/ALOK/video.mkv"
        client = self._make_client({smb_path: 42})
        console = MagicMock()

        sync_library(client, [video], console, suppressed=True)

        client.refresh_music_video.assert_called_once_with(42)

    def test_case_insensitive_matching(self, tmp_path):
        """Local 'Afrojack' matches Kodi 'AFROJACK' via prefix mapping."""
        video1 = tmp_path / "Concerts" / "Afrojack" / "video1.mkv"
        video2 = tmp_path / "Concerts" / "Agents Of Time" / "video2.mkv"
        video1.parent.mkdir(parents=True)
        video1.touch()
        video2.parent.mkdir(parents=True)
        video2.touch()

        kodi_files = {
            "smb://HOST/Concerts/AFROJACK/video1.mkv": 10,
            "smb://HOST/Concerts/Agents Of Time/video2.mkv": 20,
        }
        client = self._make_client(kodi_files)
        console = MagicMock()

        sync_library(client, [video1, video2], console, suppressed=True)

        assert client.refresh_music_video.call_count == 2

    def test_explicit_path_mapping(self, tmp_path):
        """Explicit path_mapping overrides auto-detection."""
        video = tmp_path / "Artist" / "video.mkv"
        video.parent.mkdir()
        video.touch()

        smb_path = "smb://HOST/share/Artist/video.mkv"
        client = self._make_client({smb_path: 7})
        console = MagicMock()

        sync_library(
            client, [video], console,
            path_mapping={"local": str(tmp_path), "kodi": "smb://HOST/share"},
            suppressed=True,
        )

        client.refresh_music_video.assert_called_once_with(7)

    def test_falls_back_to_filename_match(self, tmp_path):
        """When prefix mapping fails, falls back to filename matching."""
        video = tmp_path / "video.mkv"
        video.touch()

        smb_path = "smb://HYPERV/Data/Concerts/Artist/video.mkv"
        client = self._make_client({smb_path: 10})
        console = MagicMock()

        sync_library(client, [video], console, suppressed=True)

        client.refresh_music_video.assert_called_once_with(10)

    def test_warns_on_unmatched_items(self, tmp_path, caplog):
        video = tmp_path / "not_in_kodi.mkv"
        video.touch()

        client = self._make_client({})
        console = MagicMock()

        import logging
        with caplog.at_level(logging.WARNING, logger="festival_organizer.kodi"):
            sync_library(client, [video], console, suppressed=True)

        client.refresh_music_video.assert_not_called()
        assert "Not in Kodi library" in caplog.text

    def test_empty_changed_paths_is_noop(self):
        client = MagicMock(spec=KodiClient)
        console = MagicMock()

        sync_library(client, [], console, suppressed=True)

        client.scan.assert_not_called()
        client.get_music_videos.assert_not_called()

    def test_refresh_before_scan_and_clean(self, tmp_path):
        """Refresh existing items first, then scan for new, then clean stale."""
        video = tmp_path / "video.mkv"
        video.touch()

        client = self._make_client({"smb://HOST/video.mkv": 1})
        console = MagicMock()
        call_order = []
        client.refresh_music_video.side_effect = lambda *a: call_order.append("refresh")
        client.scan.side_effect = lambda *a: call_order.append("scan")
        client.clean.side_effect = lambda: call_order.append("clean")

        sync_library(client, [video], console, suppressed=True)

        assert call_order == ["refresh", "scan", "clean"]

    def test_deduplicates_paths(self, tmp_path):
        """Duplicate paths (e.g. from album_poster expansion) are deduplicated."""
        video = tmp_path / "video.mkv"
        video.touch()

        client = self._make_client({"smb://HOST/video.mkv": 1})
        console = MagicMock()

        sync_library(client, [video, video, video], console, suppressed=True)

        client.refresh_music_video.assert_called_once_with(1)

    def test_quiet_suppresses_console(self, tmp_path):
        video = tmp_path / "video.mkv"
        video.touch()

        client = self._make_client({"smb://HOST/video.mkv": 1})
        console = MagicMock()

        sync_library(client, [video], console, quiet=True, suppressed=True)

        console.print.assert_not_called()
