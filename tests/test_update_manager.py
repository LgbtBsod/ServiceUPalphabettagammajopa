"""Тесты self-updater (utils.update_manager.AutoUpdater)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from utils.update_manager import (
    AutoUpdater,
    DownloadProgress,
    UpdateError,
    normalize_version,
)


@pytest.fixture
def updater() -> AutoUpdater:
    return AutoUpdater(current_version="1.0.0")


class TestVersioning:
    def test_normalize_strips_prefix_and_space(self):
        assert normalize_version("v1.2.3") == "1.2.3"
        assert normalize_version("V1.2.3") == "1.2.3"
        assert normalize_version("v.1.2.3") == "1.2.3"
        assert normalize_version(" 1.2.3 \n") == "1.2.3"

    def test_is_newer(self, updater):
        assert updater._is_newer_version("2.0.0", "1.0.0") is True
        assert updater._is_newer_version("1.0.1", "1.0.0") is True
        assert updater._is_newer_version("1.0.0", "1.0.0") is False
        assert updater._is_newer_version("0.9.9", "1.0.0") is False

    def test_is_newer_beta(self, updater):
        """PEP 440: 1.0.0b1 < 1.0.0 < 1.0.1 — важно для схемы версий проекта."""
        assert updater._is_newer_version("1.0.0", "1.0.0b1") is True
        assert updater._is_newer_version("1.0.0b2", "1.0.0b1") is True
        assert updater._is_newer_version("1.0.0b1", "1.0.0") is False


class TestSha256Verification:
    _URL = (
        "https://github.com/o/r/releases/download/v9.9.9/ServiceUP-linux"
    )

    @pytest.fixture
    def payload(self, tmp_path) -> Path:
        p = tmp_path / "update.bin"
        p.write_bytes(b"binary-payload-xxxxx")
        return p

    def test_matching_hash_passes(self, updater, payload):
        good = updater._calculate_checksum(payload)
        with patch.object(updater, "_http_text", return_value=f"{good}  ServiceUP-linux\n"):
            ok, detail = updater._verify_sha256(payload, self._URL)
        assert ok is True and "проверено" in detail

    def test_mismatching_hash_fails_closed(self, updater, payload):
        with patch.object(updater, "_http_text", return_value=f"{'0' * 64}  x\n"):
            ok, _ = updater._verify_sha256(payload, self._URL)
        assert ok is False

    def test_missing_sums_file_does_not_block(self, updater, payload):
        with patch.object(updater, "_http_text", return_value=None):
            ok, detail = updater._verify_sha256(payload, self._URL)
        assert ok is True and "пропущено" in detail

    def test_source_zipball_url_is_skipped(self, updater, payload):
        ok, detail = updater._verify_sha256(
            payload, "https://api.github.com/repos/o/r/zipball/v9.9.9"
        )
        assert ok is True and "пропущено" in detail


class TestAssets:
    def test_platform_asset(self, updater):
        updater.is_frozen = False
        assert updater._platform_asset() is None

        updater.is_frozen = True
        with patch.object(sys, "platform", "win32"):
            assert updater._platform_asset() == "ServiceUP-windows.exe"
        with patch.object(sys, "platform", "darwin"):
            assert updater._platform_asset() == "ServiceUP-macos"
        with patch.object(sys, "platform", "linux"):
            assert updater._platform_asset() == "ServiceUP-linux"

    def test_asset_keywords(self, updater):
        updater.is_frozen = False
        assert ".zip" in updater._asset_keywords()

        updater.is_frozen = True
        with patch.object(sys, "platform", "win32"):
            assert "windows" in updater._asset_keywords()
        with patch.object(sys, "platform", "linux"):
            assert "linux" in updater._asset_keywords()

    def test_resolve_download_url_by_platform(self, updater):
        release = {
            "assets": [
                {"name": "ServiceUP-windows.exe", "browser_download_url": "u/win"},
                {"name": "ServiceUP-linux", "browser_download_url": "u/linux"},
            ]
        }
        updater.is_frozen = True
        with patch.object(sys, "platform", "win32"):
            assert updater._resolve_download_url(release) == "u/win"
        with patch.object(sys, "platform", "linux"):
            assert updater._resolve_download_url(release) == "u/linux"

    def test_pick_release_skips_drafts_and_missing_assets(self, updater):
        updater.is_frozen = False
        releases = [
            {"tag_name": "v3.0.0", "draft": True},
            {
                "tag_name": "v2.0.0", "draft": False,
                "assets": [{"name": "x.zip", "browser_download_url": "u/zip"}],
            },
        ]
        chosen = updater._pick_release(releases)
        assert chosen and chosen["tag_name"] == "v2.0.0"

        with patch.object(updater, "_resolve_download_url", return_value=None):
            assert updater._pick_release([{"tag_name": "v2.0.0", "draft": False}]) is None


class TestDiscovery:
    @patch("utils.update_manager.urlopen")
    def test_check_via_web(self, mock_urlopen, updater):
        resp = MagicMock()
        resp.read.return_value = (
            b'<feed><link href="https://github.com/LgbtBsod/ServiceUPalphabettagammajopa'
            b'/releases/tag/v2.0.0"/></feed>'
        )
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = resp
        with (
            patch.object(updater, "_asset_available", return_value=True),
            patch.object(updater, "_platform_asset", return_value="ServiceUP-linux"),
        ):
            updater.is_frozen = True
            has, version, url = updater._check_via_web()
        assert has is True
        assert version == "v2.0.0"
        assert "v2.0.0" in url

    def test_run_update_check_no_update(self, updater):
        with patch.object(updater, "check_for_updates", return_value=(False, "1.0.0", None)):
            assert updater.run_update_check(auto=False) is False

    def test_run_update_check_auto_downloads(self, updater):
        with (
            patch.object(updater, "check_for_updates", return_value=(True, "2.0.0", "u/update.zip")),
            patch.object(updater, "download_update", return_value=True) as dl,
        ):
            assert updater.run_update_check(auto=True) is True
            dl.assert_called_once()


class TestDownloadAndBackup:
    @patch("utils.update_manager.urlopen")
    def test_download_with_progress(self, mock_urlopen, updater):
        resp = MagicMock()
        resp.getheader.return_value = "2048"
        resp.read.side_effect = [b"x" * 512] * 4 + [b""]
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = resp

        cb = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "u.zip"
            ok, err = updater._download_with_progress("https://example.com/u.zip", dest, cb)
            assert ok is True, err
            assert err == ""
            assert cb.called
            assert dest.stat().st_size == 2048

    def test_checksum(self, updater):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            p = Path(f.name)
        try:
            assert updater._calculate_checksum(p) == (
                "6ae8a75555209fd6c44157c0aed8016e763ff435a19cf186f76863140143ff72"
            )
        finally:
            p.unlink()

    def test_backup_and_restore(self, updater):
        with tempfile.TemporaryDirectory() as tmp:
            updater.app_dir = Path(tmp)
            (updater.app_dir / "version.txt").write_text("1.0.0")
            (updater.app_dir / "service_center.config").write_text("{}")

            backup = updater._create_backup()
            assert backup and (backup / "version.txt").exists()
            assert (backup / "service_center.config").exists()

            (updater.app_dir / "version.txt").write_text("9.9.9")
            assert updater._restore_from_backup() is True
            assert (updater.app_dir / "version.txt").read_text() == "1.0.0"

    def test_backup_and_restore_covers_data_folder(self, updater):
        """Пользовательская БД лежит в data/ — бэкап/откат должны её захватывать."""
        with tempfile.TemporaryDirectory() as tmp:
            updater.app_dir = Path(tmp)
            (updater.app_dir / "version.txt").write_text("1.0.0")
            (updater.app_dir / "data").mkdir()
            (updater.app_dir / "data" / "serviceup.db").write_text("real-data")

            backup = updater._create_backup()
            assert backup and (backup / "data" / "serviceup.db").read_text() == "real-data"

            (updater.app_dir / "data" / "serviceup.db").write_text("corrupted-by-update")
            assert updater._restore_from_backup() is True
            assert (updater.app_dir / "data" / "serviceup.db").read_text() == "real-data"

    def test_copy_update_files_never_overwrites_data_folder(self, updater):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            (src / "data").mkdir(parents=True)
            (src / "data" / "serviceup.db").write_text("release-placeholder")
            (src / "main.py").write_text("# main")

            dest = Path(tmp) / "dest"
            (dest / "data").mkdir(parents=True)
            (dest / "data" / "serviceup.db").write_text("user-data")
            updater.app_dir = dest

            updater._copy_update_files(src)

            assert (dest / "data" / "serviceup.db").read_text() == "user-data"

    def test_copy_update_files_skips_junk(self, updater):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            (src / "venv").mkdir(parents=True)
            (src / "venv" / "python").write_text("x")
            (src / "main.py").write_text("# main")
            (src / "gui").mkdir()
            (src / "gui" / "app.py").write_text("# app")
            (src / "service_center.db").write_text("legacy-db")

            dest = Path(tmp) / "dest"
            dest.mkdir()
            updater.app_dir = dest
            copied = updater._copy_update_files(src)
            assert copied == 2  # main.py + gui/app.py; venv/ и service_center.db пропущены
            assert (dest / "main.py").exists()
            assert (dest / "gui" / "app.py").exists()
            assert not (dest / "venv").exists()
            assert not (dest / "service_center.db").exists()

    def test_update_version_file(self, updater):
        with tempfile.TemporaryDirectory() as tmp:
            updater.app_dir = Path(tmp)
            updater._update_version_file("v2.5.0")
            assert (updater.app_dir / "version.txt").read_text().strip() == "2.5.0"


class TestProgressAndErrors:
    def test_download_progress_props(self):
        p = DownloadProgress(bytes_downloaded=50, total_bytes=100, speed_bps=1024 * 1024)
        assert p.percent == 50.0
        assert p.is_complete is False
        assert p.speed_mbps == 1.0
        p.bytes_downloaded = 100
        assert p.is_complete is True

    def test_update_error(self):
        assert UpdateError("x", recoverable=True).recoverable is True
        assert UpdateError("y", recoverable=False).recoverable is False


class TestCheckUpdatesAtStartup:
    def test_skips_recent(self):
        with patch("utils.update_manager._recently_checked", return_value=True):
            from utils.update_manager import check_updates_at_startup

            result = check_updates_at_startup()
            assert result["has_update"] is False

    @patch("utils.update_manager._recently_checked", return_value=False)
    @patch("utils.update_manager.AutoUpdater")
    def test_marks_checked(self, mock_cls, _recent):
        inst = Mock()
        inst.check_for_updates.return_value = (False, "1.0.0", None)
        inst._rate_limited = False
        inst._network_reachable = True
        mock_cls.return_value = inst
        from utils.update_manager import check_updates_at_startup

        with patch("utils.update_manager._mark_checked") as mark:
            check_updates_at_startup()
            mark.assert_called_once()

    @patch("utils.update_manager._recently_checked", return_value=False)
    @patch("utils.update_manager.AutoUpdater")
    def test_reports_available_update(self, mock_cls, _recent):
        inst = Mock()
        inst.check_for_updates.return_value = (True, "v2.0.0", "https://example.com/asset")
        inst._rate_limited = False
        inst._network_reachable = True
        mock_cls.return_value = inst
        from utils.update_manager import check_updates_at_startup

        with patch("utils.update_manager._mark_checked"):
            result = check_updates_at_startup()
        assert result["has_update"] is True
        assert result["latest_version"] == "2.0.0"
        assert result["download_url"] == "https://example.com/asset"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
