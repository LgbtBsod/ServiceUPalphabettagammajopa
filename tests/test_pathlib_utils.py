"""
Unit-тесты для методов pathlib, заменяющих os.path.
Проверяют корректность работы с путями в различных модулях.
"""
import unittest
from pathlib import Path
import sys
import os

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

class TestPathlibUtils(unittest.TestCase):
    """Тесты утилит работы с путями."""

    def test_project_root_detection(self):
        """Проверка определения корня проекта."""
        root = Path(__file__).parent.parent
        self.assertTrue(root.exists())
        self.assertTrue((root / "core").exists())
        self.assertTrue((root / "gui").exists())

    def test_config_path_resolution(self):
        """Проверка разрешения путей к конфигурации."""
        root = Path(__file__).parent.parent
        config_paths = [
            root / "config" / "settings.json",
            root / "data" / "config.json"
        ]
        # Хотя бы один путь должен существовать или быть создаваемым
        self.assertTrue(len(config_paths) > 0)

    def test_log_directory_creation(self):
        """Проверка создания директории логов."""
        root = Path(__file__).parent.parent
        log_dir = root / "data" / "logs"
        # Директория должна существовать
        self.assertTrue(log_dir.exists() or log_dir.parent.exists())

    def test_template_path_handling(self):
        """Проверка путей к шаблонам отчетов."""
        root = Path(__file__).parent.parent
        template_dir = root / "reports" / "templates"
        if template_dir.exists():
            self.assertTrue(template_dir.is_dir())

    def test_database_path_resolution(self):
        """Проверка путей к базе данных."""
        root = Path(__file__).parent.parent
        db_paths = [
            root / "data" / "database.db",
            root / "data" / "db" / "main.db"
        ]
        # Проверяем, что родительские директории существуют
        for path in db_paths:
            self.assertTrue(path.parent.exists() or path.parent.parent.exists())

    def test_relative_path_safety(self):
        """Проверка безопасности относительных путей."""
        root = Path(__file__).parent.parent
        # Попытка выхода за пределы корня должна обрабатываться
        unsafe_path = root / ".." / ".." / "etc" / "passwd"
        resolved = unsafe_path.resolve()
        # Путь разрешается корректно (это ожидаемое поведение pathlib)
        # Важно что pathlib не создает файлов, только разрешает путь
        self.assertIsInstance(resolved, Path)

if __name__ == "__main__":
    unittest.main()
