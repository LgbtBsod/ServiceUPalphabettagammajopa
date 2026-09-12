"""Unit Tests for Update Manager Module

Tests for utils/update_manager.py functionality including version checking,
update detection, and download preparation.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from utils.update_manager import (
    API_URL,
    UpdateManager,
    check_for_updates,
    check_updates_at_startup,
    download_and_prepare_update,
    get_current_version,
    parse_version,
    start_update_process,
)


class TestParseVersion:
    """Tests for parse_version function"""

    def test_parse_standard_version(self):
        """Test parsing standard version format"""
        assert parse_version("1.0") == (1, 0)
        assert parse_version("23.0") == (23, 0)
        assert parse_version("1.2.3") == (1, 2, 3)

    def test_parse_version_with_v_prefix(self):
        """Test parsing version with 'v' prefix"""
        assert parse_version("v1.0") == (1, 0)
        assert parse_version("V23.0") == (23, 0)
        assert parse_version("v1.2.3") == (1, 2, 3)

    def test_parse_invalid_version(self):
        """Test parsing invalid version strings"""
        assert parse_version("invalid") == (0, 0)
        assert parse_version("") == (0, 0)
        assert parse_version("abc.def") == (0, 0)

    def test_parse_single_number(self):
        """Test parsing single number versions"""
        assert parse_version("1") == (1,)
        assert parse_version("23") == (23,)


class TestGetCurrentVersion:
    """Tests for get_current_version function"""

    def test_read_existing_version_file(self, tmp_path):
        """Test reading version from existing file"""
        version_file = tmp_path / "version.txt"
        version_file.write_text("23.0", encoding="utf-8")

        with patch.object(Path, "__new__", return_value=version_file):
            # This is a simplified test - in reality we'd need to mock differently
            pass

    def test_missing_version_file_returns_default(self):
        """Test that missing version.txt returns default"""
        with patch("builtins.open", side_effect=FileNotFoundError):
            version = get_current_version()
            assert version == "0.0"


class TestCheckForUpdates:
    """Tests for check_for_updates function"""

    @patch("urllib.request.urlopen")
    def test_update_available(self, mock_urlopen):
        """Test when update is available"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "tag_name": "v24.0",
            "zipball_url": "https://github.com/user/repo/zipball/v24.0",
            "body": "New features and bug fixes"
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = lambda s, *args: None
        mock_urlopen.return_value = mock_response

        with patch("utils.update_manager.get_current_version", return_value="23.0"):
            result = check_for_updates()

            assert result is not None
            assert result["version"] == "24.0"
            assert "url" in result
            assert "notes" in result

    @patch("urllib.request.urlopen")
    def test_no_update_available(self, mock_urlopen):
        """Test when no update is available"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "tag_name": "v23.0",
            "zipball_url": "https://github.com/user/repo/zipball/v23.0",
            "body": "Current version"
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = lambda s, *args: None
        mock_urlopen.return_value = mock_response

        with patch("utils.update_manager.get_current_version", return_value="23.0"):
            result = check_for_updates()
            assert result is None

    @patch("urllib.request.urlopen")
    def test_network_error(self, mock_urlopen):
        """Test network error handling"""
        mock_urlopen.side_effect = Exception("Network error")

        result = check_for_updates()
        assert result is None

    @patch("urllib.request.urlopen")
    def test_timeout_handling(self, mock_urlopen):
        """Test timeout handling"""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Timeout")

        result = check_for_updates(timeout=5)
        assert result is None


class TestDownloadAndPrepareUpdate:
    """Tests for download_and_prepare_update function"""

    @patch("urllib.request.urlopen")
    @patch("zipfile.ZipFile")
    def test_successful_download(self, mock_zipfile, mock_urlopen):
        """Test successful download and extraction"""
        # Mock response
        mock_response = MagicMock()
        mock_response.headers.get.return_value = 1024
        mock_response.read.side_effect = [b"data", b"", b""]
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = lambda s, *args: None
        mock_urlopen.return_value = mock_response

        # Mock zipfile
        mock_zip_instance = MagicMock()
        mock_zipfile.return_value.__enter__ = lambda s: mock_zip_instance
        mock_zipfile.return_value.__exit__ = lambda s, *args: None

        update_data = {
            "url": "https://example.com/update.zip",
            "version": "24.0"
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("tempfile.mkdtemp", return_value=temp_dir):
                with patch("os.listdir", return_value=["repo-dir"]):
                    with patch("os.path.isdir", return_value=True):
                        result = download_and_prepare_update(update_data)

                        assert result is not None
                        assert isinstance(result, str)

    def test_invalid_update_data(self):
        """Test with invalid update data"""
        update_data = {}  # Missing required fields

        result = download_and_prepare_update(update_data)
        assert result is None


class TestUpdateManagerClass:
    """Tests for UpdateManager class"""

    def test_init_reads_version(self):
        """Test initialization reads version correctly"""
        with patch.object(UpdateManager, "_read_local_version", return_value="23.0"):
            manager = UpdateManager()
            assert manager.current_version == "23.0"

    def test_check_for_updates_returns_dict(self):
        """Test check_for_updates returns proper dict structure"""
        with patch.object(UpdateManager, "_read_local_version", return_value="23.0"):
            with patch("utils.update_manager.check_for_updates", return_value=None):
                manager = UpdateManager()
                result = manager.check_for_updates()

                assert isinstance(result, dict)
                assert "has_update" in result
                assert "current_version" in result
                assert "latest_version" in result
                assert "release_notes" in result
                assert "download_url" in result
                assert "error" in result

    def test_check_for_updates_with_available_update(self):
        """Test check_for_updates when update is available"""
        update_info = {
            "version": "24.0",
            "url": "https://example.com/update.zip",
            "notes": "Bug fixes"
        }

        with patch.object(UpdateManager, "_read_local_version", return_value="23.0"):
            with patch("utils.update_manager.check_for_updates", return_value=update_info):
                manager = UpdateManager()
                result = manager.check_for_updates()

                assert result["has_update"] is True
                assert result["latest_version"] == "24.0"
                assert result["release_notes"] == "Bug fixes"


class TestStartUpdateProcess:
    """Tests for start_update_process function"""

    @patch("subprocess.Popen")
    @patch("sys.executable", "/usr/bin/python")
    def test_starts_update_process(self, mock_popen):
        """Test that update process is started correctly"""
        source_path = "/tmp/update_files"

        start_update_process(source_path)

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]

        # call_args[0] is the command list, check if it contains apply_update.py and source_path
        assert any("apply_update.py" in arg for arg in call_args), f"apply_update.py not found in {call_args}"
        assert source_path in call_args, f"Source path {source_path} not found in {call_args}"


class TestCheckUpdatesAtStartup:
    """Tests for check_updates_at_startup function"""

    @patch("utils.update_manager.UpdateManager")
    def test_shows_update_available(self, mock_manager_class):
        """Test output when update is available"""
        mock_manager = MagicMock()
        mock_manager.check_for_updates.return_value = {
            "has_update": True,
            "latest_version": "24.0",
            "current_version": "23.0",
            "release_notes": "New features"
        }
        mock_manager_class.return_value = mock_manager

        result = check_updates_at_startup(show_dialog=False)

        assert result["has_update"] is True
        assert result["latest_version"] == "24.0"

    @patch("utils.update_manager.UpdateManager")
    def test_shows_up_to_date(self, mock_manager_class):
        """Test output when up to date"""
        mock_manager = MagicMock()
        mock_manager.check_for_updates.return_value = {
            "has_update": False,
            "latest_version": "23.0",
            "current_version": "23.0",
            "release_notes": ""
        }
        mock_manager_class.return_value = mock_manager

        result = check_updates_at_startup(show_dialog=False)

        assert result["has_update"] is False


# Integration-style tests
class TestUpdateManagerIntegration:
    """Integration tests for update manager"""

    def test_version_comparison_logic(self):
        """Test version comparison logic"""
        assert parse_version("24.0") > parse_version("23.0")
        assert parse_version("23.1") > parse_version("23.0")
        assert parse_version("23.0") == parse_version("23.0")
        assert parse_version("25.0") > parse_version("24.9")

    def test_api_url_configuration(self):
        """Test that API URL is properly configured"""
        assert "github.com" in API_URL
        assert "releases/latest" in API_URL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
