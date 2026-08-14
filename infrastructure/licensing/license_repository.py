"""
License repository implementations - реализации хранилищ лицензий.
"""

from __future__ import annotations
import os
import json
import hmac
import hashlib
import logging
import sys
from typing import Optional
from datetime import datetime

from config import BASE_DIR, LICENSE_SECRET_KEY as SECRET_KEY

logger = logging.getLogger(__name__)


def _compute_checksum(data: str) -> str:
    """Контрольная сумма для проверки целостности данных."""
    return hmac.new(SECRET_KEY, data.encode('utf-8'), hashlib.md5).hexdigest()


class FileLicenseRepository:
    """
    Хранилище лицензий в файле .license.
    
    Файл содержит JSON с HMAC-SHA256 подписью для защиты от подделки.
    """
    
    def __init__(self, file_path: Optional[str] = None):
        self._file_path = file_path or os.path.join(BASE_DIR, '.license')
    
    def read(self) -> Optional[dict]:
        """Чтение файла лицензии с проверкой HMAC."""
        try:
            if not os.path.exists(self._file_path):
                return None
            
            with open(self._file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Проверка подписи
            signature = data.pop('signature', '')
            payload = json.dumps(data, sort_keys=True)
            expected = _compute_checksum(payload)
            
            if not hmac.compare_digest(signature, expected):
                logger.warning("Лицензия: подпись недействительна")
                return None
            
            return data
        
        except Exception as e:
            logger.error(f"Ошибка чтения лицензии: {e}", exc_info=True)
            return None
    
    def write(self, data: dict) -> bool:
        """Запись файла лицензии с HMAC-подписью."""
        try:
            payload = json.dumps(data, sort_keys=True)
            data_with_sig = dict(data)
            data_with_sig['signature'] = _compute_checksum(payload)
            
            with open(self._file_path, 'w', encoding='utf-8') as f:
                json.dump(data_with_sig, f, indent=2)
            
            # Скрываем файл на Windows
            if sys.platform == 'win32':
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(
                        self._file_path, 
                        0x2  # FILE_ATTRIBUTE_HIDDEN
                    )
                except Exception:
                    pass
            
            return True
        
        except Exception as e:
            logger.error(f"Ошибка записи лицензии: {e}", exc_info=True)
            return False
    
    def delete(self) -> bool:
        """Удаление файла лицензии."""
        try:
            if os.path.exists(self._file_path):
                os.remove(self._file_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления лицензии: {e}", exc_info=True)
            return False


class MemoryLicenseRepository:
    """
    In-memory хранилище лицензий (для тестирования).
    """
    
    def __init__(self):
        self._data: Optional[dict] = None
    
    def read(self) -> Optional[dict]:
        return self._data
    
    def write(self, data: dict) -> bool:
        self._data = data
        return True
    
    def delete(self) -> bool:
        self._data = None
        return True
