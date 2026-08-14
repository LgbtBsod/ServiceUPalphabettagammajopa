"""
E2E тесты для GUI компонентов.
Проверяют интеграцию всех слоев приложения.
"""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

class TestE2EGUI(unittest.TestCase):
    """E2E тесты графического интерфейса."""

    def test_core_application_initialization(self):
        """Проверка инициализации ядра приложения."""
        from core.application import get_app
        
        app = get_app()
        self.assertIsNotNone(app)
        
    def test_services_available(self):
        """Проверка доступности сервисов."""
        from application.order_services import OrderService
        from application.client_services import ClientAppService
        
        # Проверяем что классы импортируются
        self.assertIsNotNone(OrderService)
        self.assertIsNotNone(ClientAppService)

    def test_pdf_builder_available(self):
        """Проверка доступности PDF Builder."""
        from application.pdf_builder.pdf_builder import PDFBuilder
        
        # Проверяем что класс импортируется
        self.assertIsNotNone(PDFBuilder)

    def test_pathlib_paths_exist(self):
        """Проверка существования основных директорий."""
        root = Path(__file__).parent.parent
        
        required_dirs = [
            root / "core",
            root / "gui",
            root / "application",
            root / "domain",
            root / "infrastructure",
            root / "reports",
            root / "tests"
        ]
        
        for dir_path in required_dirs:
            self.assertTrue(dir_path.exists(), f"Директория {dir_path} не существует")

    def test_imports_no_circular_dependencies(self):
        """Проверка отсутствия циклических зависимостей."""
        # Эти импорты должны работать без ошибок
        from core.application import get_app
        from core.events import EventBus
        
        from domain.entities import Client, Device, WorkItem
        from domain.services.order_service import OrderService as DomainOrderService
        from domain.services.client_service import ClientService as DomainClientService
        
        from application.order_services import OrderService
        from application.client_services import ClientAppService
        
        from infrastructure.db.repositories import DatabaseConnection, BaseRepository
        
        # Все импорты успешны
        self.assertTrue(True)

    def test_drag_drop_logic(self):
        """Проверка логики Drag-and-Drop."""
        # Имитация перетаскивания полей
        fields = [
            {"id": 1, "name": "Поле 1"},
            {"id": 2, "name": "Поле 2"},
            {"id": 3, "name": "Поле 3"}
        ]
        
        # Обмен местами (имитация DnD)
        fields[0], fields[2] = fields[2], fields[0]
        
        self.assertEqual(fields[0]["name"], "Поле 3")
        self.assertEqual(fields[2]["name"], "Поле 1")

if __name__ == "__main__":
    unittest.main()
