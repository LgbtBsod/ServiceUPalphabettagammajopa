#!/usr/bin/env python3

"""Тесты для managers/backup.py::BackupManager — не имел ни одного теста,
несмотря на реальную ветвящуюся логику (выключатель auto_backup, guard на
отсутствующий/пустой файл БД, zip-then-delete при compress_backups,
mtime-сортированный pruning по backup_count, проглатывание OSError при
чистке). Единственная линия защиты от потери данных, если бэкапы молча
перестанут работать — см. также backup_path's docstring про уже один раз
случившийся здесь класс бага (закэшированный путь молчал до рестарта)."""

import os
import time
from pathlib import Path

import pytest

from managers.backup import BackupManager
from managers.settings import SettingsManager


@pytest.fixture
def settings(tmp_path) -> SettingsManager:
    mgr = SettingsManager(config_file=str(tmp_path / "config.json"))
    mgr.set("auto_backup", True)
    mgr.set("backup_path", str(tmp_path / "backups"))
    mgr.set("backup_count", 10)
    mgr.set("compress_backups", False)
    return mgr


@pytest.fixture
def db_file(tmp_path) -> str:
    path = tmp_path / "serviceup.db"
    path.write_bytes(b"fake sqlite content")
    return str(path)


class TestCreateBackup:
    def test_noop_when_auto_backup_disabled(self, settings, db_file):
        settings.set("auto_backup", False)
        mgr = BackupManager(settings)

        result = mgr.create_backup(db_file)

        assert result is None

    def test_noop_when_db_path_missing(self, settings, tmp_path):
        mgr = BackupManager(settings)

        result = mgr.create_backup(str(tmp_path / "does_not_exist.db"))

        assert result is None

    def test_noop_when_db_path_empty_string(self, settings):
        mgr = BackupManager(settings)

        assert mgr.create_backup("") is None
        assert mgr.create_backup(None) is None

    def test_noop_when_db_file_is_empty(self, settings, tmp_path):
        empty_db = tmp_path / "empty.db"
        empty_db.write_bytes(b"")
        mgr = BackupManager(settings)

        result = mgr.create_backup(str(empty_db))

        assert result is None

    def test_copies_db_file_to_backup_path(self, settings, db_file, tmp_path):
        mgr = BackupManager(settings)

        result = mgr.create_backup(db_file)

        assert result is not None
        assert result.endswith(".db")
        backup_path = Path(result)
        assert backup_path.exists()
        assert backup_path.read_bytes() == b"fake sqlite content"

    def test_compress_backups_produces_zip_and_removes_the_raw_copy(self, settings, db_file):
        settings.set("compress_backups", True)
        mgr = BackupManager(settings)

        result = mgr.create_backup(db_file)

        assert result is not None
        assert result.endswith(".zip")
        assert Path(result).exists()
        assert not Path(result[: -len(".zip")]).exists()

    def test_backup_path_change_takes_effect_immediately(self, settings, db_file, tmp_path):
        """backup_path — свойство, читающее settings.get() при каждом
        обращении (см. docstring в managers/backup.py про уже случившийся
        здесь баг с кэшированием) — смена пути на лету должна применяться
        без пересоздания BackupManager."""
        mgr = BackupManager(settings)
        new_path = tmp_path / "new_backups"
        settings.set("backup_path", str(new_path))

        result = mgr.create_backup(db_file)

        assert result is not None
        assert str(new_path) in result


class TestCleanupOldBackups:
    def test_prunes_down_to_backup_count_keeping_the_newest(self, settings, tmp_path):
        settings.set("backup_count", 2)
        mgr = BackupManager(settings)
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        paths = []
        for i in range(4):
            p = backup_dir / f"backup_{i}.db"
            p.write_bytes(b"x")
            os_time = time.time() + i  # гарантированно растущий mtime
            os.utime(p, (os_time, os_time))
            paths.append(p)

        mgr.cleanup_old_backups()

        remaining = sorted(backup_dir.glob("backup_*.db"))
        assert len(remaining) == 2
        # Оставшиеся — два САМЫХ НОВЫХ (backup_2, backup_3), не первые по имени.
        remaining_names = {p.name for p in remaining}
        assert remaining_names == {"backup_2.db", "backup_3.db"}

    def test_does_not_touch_files_not_matching_the_backup_prefix(self, settings, tmp_path):
        settings.set("backup_count", 0)
        mgr = BackupManager(settings)
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "backup_old.db").write_bytes(b"x")
        (backup_dir / "readme.txt").write_bytes(b"not a backup")

        mgr.cleanup_old_backups()

        assert not (backup_dir / "backup_old.db").exists()
        assert (backup_dir / "readme.txt").exists()

    def test_backup_count_zero_removes_all_backups_without_crashing(self, settings, tmp_path):
        settings.set("backup_count", 0)
        mgr = BackupManager(settings)
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "backup_a.db").write_bytes(b"x")
        (backup_dir / "backup_b.db").write_bytes(b"x")

        mgr.cleanup_old_backups()  # не должно бросить

        assert list(backup_dir.glob("backup_*.db")) == []

    def test_missing_backup_dir_does_not_raise(self, settings, tmp_path):
        missing_dir = tmp_path / "never_created"
        settings.set("backup_path", str(missing_dir))
        mgr = BackupManager(settings)
        # __init__ уже создал папку (create_backup_dir()) — убираем её
        # снова, чтобы реально проверить сценарий отсутствующей директории,
        # а не просто пустой существующей.
        missing_dir.rmdir()
        assert not missing_dir.exists()

        mgr.cleanup_old_backups()  # os.listdir на несуществующей папке — не должно бросить наружу
