#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Менеджер резервного копирования"""

import os
import shutil
import zipfile
from datetime import datetime
from typing import Optional

from config import BACKUP_DIR


class BackupManager:
    """Класс для управления резервными копиями"""
    
    def __init__(self, settings):
        self.settings = settings
        self.backup_path = settings.get('backup_path', BACKUP_DIR)
        self.create_backup_dir()
    
    def create_backup_dir(self):
        """Создание директории для бэкапов"""
        try:
            if not os.path.exists(self.backup_path):
                os.makedirs(self.backup_path)
        except Exception as e:
            print(f"Ошибка создания директории бэкапов: {e}")
    
    def create_backup(self, db_path: str) -> Optional[str]:
        """Создание резервной копии"""
        if not self.settings.get('auto_backup'):
            return None
        
        try:
            # Не создаём пустой/несуществующий бэкап (раньше это маскировало ошибки БД)
            if not db_path or not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
                print("Пропуск бэкапа: файл БД отсутствует или пуст")
                return None
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"backup_{timestamp}.db"
            backup_file = os.path.join(self.backup_path, backup_name)
            
            shutil.copy2(db_path, backup_file)
            
            if self.settings.get('compress_backups'):
                with zipfile.ZipFile(backup_file + '.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(backup_file, os.path.basename(backup_file))
                os.remove(backup_file)
                backup_file += '.zip'
            
            self.cleanup_old_backups()
            return backup_file
        except Exception as e:
            print(f"Ошибка создания бэкапа: {e}")
            return None
    
    def cleanup_old_backups(self):
        """Очистка старых резервных копий"""
        try:
            max_count = self.settings.get('backup_count', 10)
            backups = []
            
            for file in os.listdir(self.backup_path):
                if file.startswith('backup_'):
                    file_path = os.path.join(self.backup_path, file)
                    backups.append((os.path.getmtime(file_path), file_path))
            
            backups.sort(reverse=True)
            
            for i in range(max_count, len(backups)):
                try:
                    os.remove(backups[i][1])
                except OSError as e:
                    print(f"Не удалось удалить старый бэкап {backups[i][1]}: {e}")
        except Exception as e:
            print(f"Ошибка очистки бэкапов: {e}")
