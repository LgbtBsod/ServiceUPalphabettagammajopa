"""
Backup Application Services - Use Cases для резервного копирования.

Следует принципам:
- SRP: каждый метод решает одну задачу
- Strategy Pattern: разные стратегии бэкапа
- Multi-threading: асинхронное создание бэкапов
"""

from __future__ import annotations

import logging
import shutil
import gzip
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Protocol
from concurrent.futures import ThreadPoolExecutor, Future

from shared.kernel import UnitOfWork

logger = logging.getLogger(__name__)


class UnitOfWorkFactory(Protocol):
    """Протокол фабрики Unit of Work."""
    def __call__(self) -> UnitOfWork: ...


@dataclass(slots=True)
class BackupResult:
    """Результат создания бэкапа."""
    backup_id: str
    file_path: str
    size_bytes: int
    success: bool
    message: str = ""
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            object.__setattr__(self, 'created_at', datetime.now())
    
    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


@dataclass(slots=True)
class BackupInfo:
    """Информация о существующем бэкапе."""
    file_path: str
    size_bytes: int
    created_at: datetime
    checksum: str


class BackupService:
    """
    Сервис приложения для резервного копирования и восстановления.
    
    Поддерживает:
    - Полные бэкапы БД
    - Сжатие gzip
    - Автоматическая ротация старых бэкапов
    - Асинхронное создание
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        backup_dir: str,
        max_backups: int = 10,
        max_workers: int = 1,
    ):
        self._uow_factory = uow_factory
        self._backup_dir = Path(backup_dir)
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._max_backups = max_backups
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def create_backup(self, db_path: str) -> Future[BackupResult]:
        """
        Асинхронное создание бэкапа базы данных (Command).
        
        Args:
            db_path: Путь к файлу базы данных.
            
        Returns:
            Future с результатом создания бэкапа.
        """
        return self._executor.submit(
            self._create_backup_sync,
            db_path,
        )

    def _create_backup_sync(self, db_path: str) -> BackupResult:
        """Синхронное создание бэкапа (внутренний метод)."""
        try:
            backup_id = f"BACKUP_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            source = Path(db_path)
            
            if not source.exists():
                return BackupResult(
                    backup_id="",
                    file_path="",
                    size_bytes=0,
                    success=False,
                    message=f"База данных не найдена: {db_path}",
                )
            
            # Создаем временную копию
            temp_backup = self._backup_dir / f"{backup_id}_temp.db"
            shutil.copy2(source, temp_backup)
            
            # Сжимаем gzip
            compressed_path = self._backup_dir / f"{backup_id}.db.gz"
            with open(temp_backup, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Удаляем временный файл
            temp_backup.unlink()
            
            # Получаем размер
            size_bytes = compressed_path.stat().st_size
            
            # Ротация старых бэкапов
            self._rotate_old_backups()
            
            logger.info(f"Бэкап создан: {compressed_path} ({size_bytes / 1024 / 1024:.2f} MB)")
            
            return BackupResult(
                backup_id=backup_id,
                file_path=str(compressed_path),
                size_bytes=size_bytes,
                success=True,
            )
            
        except Exception as e:
            logger.error(f"Ошибка создания бэкапа: {e}", exc_info=True)
            return BackupResult(
                backup_id="",
                file_path="",
                size_bytes=0,
                success=False,
                message=str(e),
            )

    def restore_backup(self, backup_path: str, target_db_path: str) -> bool:
        """
        Восстановление из бэкапа (Command).
        
        Args:
            backup_path: Путь к файлу бэкапа (.db.gz).
            target_db_path: Путь для восстановления базы данных.
            
        Returns:
            True если успешно.
        """
        try:
            backup_file = Path(backup_path)
            target = Path(target_db_path)
            
            if not backup_file.exists():
                logger.error(f"Бэкап не найден: {backup_path}")
                return False
            
            # Создаем бэкап текущей БД перед восстановлением
            if target.exists():
                pre_restore_backup = self._backup_dir / f"PRE_RESTORE_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db.gz"
                with open(target, 'rb') as f_in:
                    with gzip.open(pre_restore_backup, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                logger.info(f"Создан превентивный бэкап: {pre_restore_backup}")
            
            # Распаковываем бэкап
            with gzip.open(backup_file, 'rb') as f_in:
                with open(target, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            logger.info(f"Восстановление из бэкапа: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка восстановления: {e}", exc_info=True)
            return False

    def list_backups(self) -> List[BackupInfo]:
        """Получение списка всех бэкапов (Query)."""
        backups = []
        
        for file_path in self._backup_dir.glob("*.db.gz"):
            try:
                stat = file_path.stat()
                backups.append(BackupInfo(
                    file_path=str(file_path),
                    size_bytes=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_mtime),
                    checksum="",  # Можно добавить вычисление checksum
                ))
            except Exception as e:
                logger.warning(f"Ошибка чтения бэкапа {file_path}: {e}")
        
        # Сортировка по дате (новые сначала)
        backups.sort(key=lambda x: x.created_at, reverse=True)
        return backups

    def delete_backup(self, backup_path: str) -> bool:
        """Удаление бэкапа (Command)."""
        try:
            backup_file = Path(backup_path)
            if backup_file.exists():
                backup_file.unlink()
                logger.info(f"Бэкап удален: {backup_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка удаления бэкапа: {e}", exc_info=True)
            return False

    def _rotate_old_backups(self) -> None:
        """Удаление старых бэкапов за пределами лимита."""
        backups = self.list_backups()
        
        if len(backups) > self._max_backups:
            # Удаляем самые старые
            for backup in backups[self._max_backups:]:
                self.delete_backup(backup.file_path)
                logger.info(f"Удален старый бэкап: {backup.file_path}")

    def get_backup_stats(self) -> dict:
        """Статистика по бэкапам (Query)."""
        backups = self.list_backups()
        
        if not backups:
            return {
                'count': 0,
                'total_size_bytes': 0,
                'oldest_backup': None,
                'newest_backup': None,
            }
        
        total_size = sum(b.size_bytes for b in backups)
        
        return {
            'count': len(backups),
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'oldest_backup': backups[-1].file_path if backups else None,
            'newest_backup': backups[0].file_path if backups else None,
        }

    def shutdown(self) -> None:
        """Корректное завершение работы сервиса."""
        self._executor.shutdown(wait=True)
