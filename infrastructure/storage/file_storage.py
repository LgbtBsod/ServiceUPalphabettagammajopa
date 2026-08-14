"""
File Storage Implementation.

Хранилище файлов для документов, фото и других вложений.
"""

from pathlib import Path
from typing import Optional, List, BinaryIO
from datetime import datetime
import hashlib
import shutil
import logging

from core.base import LoggableMixin


logger = logging.getLogger(__name__)


class FileStorage(LoggableMixin):
    """
    Файловое хранилище.
    
    Features:
    - Хранение файлов по хешу имени (дедупликация)
    - Поддержка подпапок по датам
    - Метаданные файлов
    """
    
    def __init__(self, base_path: str = "./storage"):
        super().__init__()
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"FileStorage initialized: {base_path}")
    
    def save(
        self,
        content: bytes,
        filename: str,
        folder: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Сохраняет файл в хранилище.
        
        Args:
            content: Содержимое файла
            filename: Имя файла
            folder: Опциональная папка
            metadata: Метаданные
            
        Returns:
            Путь к сохраненному файлу
        """
        # Генерируем уникальный хеш для имени
        file_hash = hashlib.md5(
            content + datetime.now().isoformat().encode()
        ).hexdigest()[:12]
        
        # Создаем путь с датой
        date_path = datetime.now().strftime("%Y/%m/%d")
        if folder:
            file_path = self._base_path / folder / date_path / f"{file_hash}_{filename}"
        else:
            file_path = self._base_path / date_path / f"{file_hash}_{filename}"
        
        # Создаем директорию
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем файл
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Сохраняем метаданные
        if metadata:
            meta_path = file_path.with_suffix(".meta")
            import json
            with open(meta_path, "w") as f:
                json.dump(metadata, f)
        
        relative_path = str(file_path.relative_to(self._base_path))
        self.logger.debug(f"File saved: {relative_path}")
        
        return relative_path
    
    def get(self, file_path: str) -> Optional[bytes]:
        """Получает содержимое файла."""
        full_path = self._base_path / file_path
        
        if not full_path.exists():
            self.logger.warning(f"File not found: {file_path}")
            return None
        
        with open(full_path, "rb") as f:
            return f.read()
    
    def get_metadata(self, file_path: str) -> Optional[dict]:
        """Получает метаданные файла."""
        meta_path = self._base_path / (file_path + ".meta")
        
        if not meta_path.exists():
            return None
        
        import json
        with open(meta_path, "r") as f:
            return json.load(f)
    
    def delete(self, file_path: str) -> bool:
        """Удаляет файл из хранилища."""
        full_path = self._base_path / file_path
        meta_path = full_path.with_suffix(".meta")
        
        deleted = False
        
        if full_path.exists():
            full_path.unlink()
            deleted = True
        
        if meta_path.exists():
            meta_path.unlink()
        
        if deleted:
            self.logger.debug(f"File deleted: {file_path}")
        
        return deleted
    
    def exists(self, file_path: str) -> bool:
        """Проверяет существование файла."""
        return (self._base_path / file_path).exists()
    
    def list_files(self, folder: Optional[str] = None) -> List[str]:
        """Список файлов в папке."""
        search_path = self._base_path / folder if folder else self._base_path
        
        if not search_path.exists():
            return []
        
        files = []
        for path in search_path.rglob("*"):
            if path.is_file() and not path.suffix == ".meta":
                files.append(str(path.relative_to(self._base_path)))
        
        return files
    
    def get_size(self, file_path: str) -> int:
        """Получает размер файла в байтах."""
        full_path = self._base_path / file_path
        
        if not full_path.exists():
            return 0
        
        return full_path.stat().st_size
    
    def cleanup_empty_dirs(self) -> int:
        """Очищает пустые директории. Возвращает количество удаленных."""
        removed_count = 0
        
        # Проходим от глубоких к мелким
        for dirpath in sorted(self._base_path.rglob("*"), reverse=True):
            if dirpath.is_dir():
                try:
                    # Пытаемся удалить если пусто
                    dirpath.rmdir()
                    removed_count += 1
                    self.logger.debug(f"Removed empty directory: {dirpath}")
                except OSError:
                    # Не пусто, пропускаем
                    pass
        
        return removed_count


# Глобальный экземпляр
_global_storage: Optional[FileStorage] = None


def get_file_storage(base_path: str = "./storage") -> FileStorage:
    """Получает глобальное хранилище файлов."""
    global _global_storage
    if _global_storage is None:
        _global_storage = FileStorage(base_path)
    return _global_storage


def reset_file_storage() -> None:
    """Сбрасывает глобальное хранилище (для тестов)."""
    global _global_storage
    _global_storage = None
