#!/usr/bin/env python3

"""Менеджер резервного копирования"""

import logging
import os
import shutil
import zipfile
from datetime import datetime

from config import BACKUP_DIR

logger = logging.getLogger(__name__)


class BackupManager:
    """Класс для управления резервными копиями"""

    def __init__(self, settings):
        self.settings = settings
        self.create_backup_dir()

    @property
    def backup_path(self) -> str:
        """Читает путь для бэкапов ИЗ SettingsManager при каждом обращении,
        а не один раз в __init__.

        Раньше кэшировался в self.backup_path на конструкторе — правка пути
        в "Настройки → Резервное копирование" (gui/dialogs/settings.py,
        settings.set("backup_path", ...)) молча не действовала до
        перезапуска приложения: create_backup()/cleanup_old_backups()
        продолжали писать/чистить по старому пути весь остаток сессии.

        DEFAULT_SETTINGS["backup_path"] хранит "" (utils/constants.py), а не
        отсутствие ключа — settings.get("backup_path", BACKUP_DIR) поэтому
        всегда возвращал "" вместо фолбэка на BACKUP_DIR. os.path.join("", x)
        == x, так что бэкап писался бare-именем в текущую рабочую директорию
        процесса (непредсказуемо для GUI/exe), а os.makedirs("")/os.listdir("")
        падали (проглатывались) — pruning по backup_count не работал вообще.
        gui/dialogs/settings.py уже использует идиому `or BACKUP_DIR`.
        """
        return self.settings.get("backup_path") or BACKUP_DIR

    def create_backup_dir(self):
        """Создание директории для бэкапов"""
        try:
            if not os.path.exists(self.backup_path):
                os.makedirs(self.backup_path)
        except Exception as e:
            logger.error(f"Ошибка создания директории бэкапов: {e}", exc_info=True)

    def create_backup(self, db_path: str) -> str | None:
        """Создание резервной копии"""
        if not self.settings.get("auto_backup"):
            return None

        try:
            # Не создаём пустой/несуществующий бэкап (раньше это маскировало ошибки БД)
            if (
                not db_path
                or not os.path.exists(db_path)
                or os.path.getsize(db_path) == 0
            ):
                logger.warning("Пропуск бэкапа: файл БД отсутствует или пуст")
                return None

            # backup_path теперь читается live (см. свойство выше) — если
            # пользователь только что сменил путь в настройках, новая папка
            # ещё может не существовать; create_backup_dir() создаёт её
            # заново, если нужно (дёшево — no-op, если папка уже есть).
            self.create_backup_dir()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}.db"
            backup_file = os.path.join(self.backup_path, backup_name)

            shutil.copy2(db_path, backup_file)

            if self.settings.get("compress_backups"):
                with zipfile.ZipFile(
                    backup_file + ".zip", "w", zipfile.ZIP_DEFLATED
                ) as zipf:
                    zipf.write(backup_file, os.path.basename(backup_file))
                os.remove(backup_file)
                backup_file += ".zip"

            self.cleanup_old_backups()
            return backup_file
        except Exception as e:
            logger.error(f"Ошибка создания бэкапа: {e}", exc_info=True)
            return None

    def cleanup_old_backups(self):
        """Очистка старых резервных копий"""
        try:
            max_count = self.settings.get("backup_count", 10)
            backups = []

            for file in os.listdir(self.backup_path):
                if file.startswith("backup_"):
                    file_path = os.path.join(self.backup_path, file)
                    backups.append((os.path.getmtime(file_path), file_path))

            backups.sort(reverse=True)

            for i in range(max_count, len(backups)):
                try:
                    os.remove(backups[i][1])
                except OSError as e:
                    logger.warning(
                        f"Не удалось удалить старый бэкап {backups[i][1]}: {e}"
                    )
        except Exception as e:
            logger.error(f"Ошибка очистки бэкапов: {e}", exc_info=True)
