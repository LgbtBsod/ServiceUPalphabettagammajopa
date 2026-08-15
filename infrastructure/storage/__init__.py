"""Storage Infrastructure Layer.

Хранилища файлов и документов.
"""

from infrastructure.storage.file_storage import (
    FileStorage,
    get_file_storage,
    reset_file_storage,
)

__all__ = [
    "FileStorage",
    "get_file_storage",
    "reset_file_storage",
]
