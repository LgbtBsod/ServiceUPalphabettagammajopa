"""
Тесты Модульной Системы v24.0

Проверка работы ModuleRegistry, ModuleBase и авто-загрузки модулей.
"""

import pytest
from pathlib import Path
import shutil
from core.module_registry import (
    ModuleRegistry, 
    ModuleBase, 
    ModuleInfo,
    get_module_registry,
    reset_module_registry
)


class TestModuleBase:
    """Тесты базового класса модуля"""
    
    def test_module_base_creation(self):
        """Создание экземпляра ModuleBase"""
        module = ModuleBase()
        assert module.name == "base_module"
        assert module.version == "1.0.0"
        
    def test_module_base_with_app_container(self, mock_app_container):
        """Инициализация с DI контейнером"""
        module = ModuleBase(app_container=mock_app_container)
        assert module.app == mock_app_container
        
    def test_module_base_without_app_container(self):
        """Попытка доступа к app без контейнера вызывает ошибку"""
        module = ModuleBase(app_container=None)
        with pytest.raises(RuntimeError, match="App container not injected"):
            _ = module.app
            
    def test_module_base_log_property(self):
        """Логгер создается автоматически"""
        module = ModuleBase()
        assert module.log is not None
        assert hasattr(module.log, 'info')
        
    def test_module_base_hooks_exist(self):
        """Хуки жизненного цикла существуют и не вызывают ошибок"""
        module = ModuleBase()
        module.on_init()  # Не должно вызывать исключений
        module.on_start()
        module.on_stop()
        
    def test_module_base_get_service(self, mock_app_container):
        """Получение сервиса из контейнера"""
        module = ModuleBase(app_container=mock_app_container)
        service = module.get_service("test_service")
        assert service == "test_service_instance"
        
    def test_module_base_get_repository(self, mock_app_container):
        """Получение репозитория из контейнера"""
        module = ModuleBase(app_container=mock_app_container)
        repo = module.get_repository("test_repo")
        assert repo == "test_repo_instance"


class TestModuleRegistry:
    """Тесты реестра модулей"""
    
    @pytest.fixture
    def registry(self, tmp_path):
        """Создание реестра с временной папкой modules"""
        reset_module_registry()
        return ModuleRegistry(modules_path=tmp_path)
        
    def test_discover_modules_empty_directory(self, registry, tmp_path):
        """Обнаружение модулей в пустой папке"""
        discovered = registry.discover_modules()
        assert len(discovered) == 0
        
    def test_discover_modules_no_init_py(self, registry, tmp_path):
        """Папка без __init__.py игнорируется"""
        module_dir = tmp_path / "invalid_module"
        module_dir.mkdir()
        (module_dir / "module.py").write_text("pass")
        
        discovered = registry.discover_modules()
        assert len(discovered) == 0
        
    def test_discover_modules_valid_module(self, registry, tmp_path):
        """Обнаружение валидного модуля"""
        module_dir = tmp_path / "test_module"
        module_dir.mkdir()
        
        init_file = module_dir / "__init__.py"
        init_file.write_text("""
from core.module_registry import ModuleBase

MODULE_NAME = "test_module"
MODULE_VERSION = "1.0.0"
MODULE_DESCRIPTION = "Test module"
MODULE_AUTHOR = "Tester"
MODULE_DEPENDENCIES = []

class TestModule(ModuleBase):
    name = MODULE_NAME
    version = MODULE_VERSION
    
registry_test_status = "ok"
""")
        
        discovered = registry.discover_modules()
        assert len(discovered) == 1
        assert "test_module" in discovered
        
    def test_initialize_all(self, registry, tmp_path, mock_app_container):
        """Инициализация всех модулей"""
        module_dir = tmp_path / "init_test_module"
        module_dir.mkdir()
        
        init_file = module_dir / "__init__.py"
        init_file.write_text("""
from core.module_registry import ModuleBase

MODULE_NAME = "init_test_module"

class InitTestModule(ModuleBase):
    name = MODULE_NAME
    init_called = False
    
    def on_init(self):
        self.init_called = True
        self.log.info("Init called")
""")
        
        registry.discover_modules()
        initialized = registry.initialize_all(mock_app_container)
        
        assert "init_test_module" in initialized
        assert initialized["init_test_module"].init_called is True
        
    def test_start_all(self, registry, tmp_path, mock_app_container):
        """Запуск всех модулей"""
        module_dir = tmp_path / "start_test_module"
        module_dir.mkdir()
        
        init_file = module_dir / "__init__.py"
        init_file.write_text("""
from core.module_registry import ModuleBase

MODULE_NAME = "start_test_module"

class StartTestModule(ModuleBase):
    name = MODULE_NAME
    start_called = False
    
    def on_start(self):
        self.start_called = True
""")
        
        registry.discover_modules()
        registry.initialize_all(mock_app_container)
        registry.start_all()
        
        module = registry.get_module("start_test_module")
        assert module.start_called is True
        
    def test_stop_all(self, registry, tmp_path, mock_app_container):
        """Остановка всех модулей"""
        module_dir = tmp_path / "stop_test_module"
        module_dir.mkdir()
        
        init_file = module_dir / "__init__.py"
        init_file.write_text("""
from core.module_registry import ModuleBase

MODULE_NAME = "stop_test_module"

class StopTestModule(ModuleBase):
    name = MODULE_NAME
    stop_called = False
    
    def on_stop(self):
        self.stop_called = True
""")
        
        registry.discover_modules()
        registry.initialize_all(mock_app_container)
        registry.start_all()
        registry.stop_all()
        
        module = registry.get_module("stop_test_module")
        assert module.stop_called is True
        
    def test_list_modules(self, registry, tmp_path):
        """Получение списка модулей с метаданными"""
        module_dir = tmp_path / "list_test_module"
        module_dir.mkdir()
        
        init_file = module_dir / "__init__.py"
        init_file.write_text("""
from core.module_registry import ModuleBase

MODULE_NAME = "list_test_module"
MODULE_VERSION = "2.0.0"
MODULE_DESCRIPTION = "List test"
MODULE_AUTHOR = "Tester"

class ListTestModule(ModuleBase):
    name = MODULE_NAME
""")
        
        registry.discover_modules()
        modules_list = registry.list_modules()
        
        assert len(modules_list) == 1
        assert modules_list[0]["name"] == "list_test_module"
        assert modules_list[0]["version"] == "2.0.0"
        assert modules_list[0]["description"] == "List test"
        
    def test_module_error_isolation(self, registry, tmp_path, mock_app_container):
        """Ошибки в модуле не ломают другие модули"""
        # Валидный модуль
        valid_dir = tmp_path / "valid_module"
        valid_dir.mkdir()
        (valid_dir / "__init__.py").write_text("""
from core.module_registry import ModuleBase
class ValidModule(ModuleBase):
    name = "valid_module"
""")
        
        # Модуль с ошибкой в on_init
        invalid_dir = tmp_path / "invalid_module"
        invalid_dir.mkdir()
        (invalid_dir / "__init__.py").write_text("""
from core.module_registry import ModuleBase
class InvalidModule(ModuleBase):
    name = "invalid_module"
    def on_init(self):
        raise RuntimeError("Intentional error")
""")
        
        registry.discover_modules()
        initialized = registry.initialize_all(mock_app_container)
        
        # Валидный модуль должен инициализироваться
        assert "valid_module" in initialized
        
        # Неважный модуль должен быть помечен как disabled
        info = registry.modules.get("invalid_module")
        assert info is not None
        assert info.enabled is False


class TestGlobalRegistry:
    """Тесты глобального реестра"""
    
    def test_get_module_registry_singleton(self, tmp_path):
        """Глобальный реестр - singleton"""
        reset_module_registry()
        
        registry1 = get_module_registry(tmp_path)
        registry2 = get_module_registry(tmp_path)
        
        assert registry1 is registry2
        
    def test_reset_module_registry(self, tmp_path):
        """Сброс глобального реестра"""
        reset_module_registry()
        
        registry1 = get_module_registry(tmp_path)
        reset_module_registry()
        registry2 = get_module_registry(tmp_path)
        
        assert registry1 is not registry2


@pytest.fixture
def mock_app_container():
    """Моковый DI контейнер"""
    class MockContainer:
        def get_service(self, name):
            return f"{name}_instance"
            
        def get_repository(self, name):
            return f"{name}_instance"
            
    return MockContainer()


# Интеграционный тест с реальным example_module
class TestExampleModuleIntegration:
    """Интеграционные тесты с example_module"""
    
    def test_example_module_discovery(self):
        """Обнаружение example_module из modules/"""
        reset_module_registry()
        registry = ModuleRegistry(modules_path=Path("./modules"))
        
        discovered = registry.discover_modules()
        
        assert "example_module" in discovered
        
    def test_example_module_initialization(self, mock_app_container):
        """Инициализация example_module"""
        reset_module_registry()
        registry = ModuleRegistry(modules_path=Path("./modules"))
        
        registry.discover_modules()
        initialized = registry.initialize_all(mock_app_container)
        
        assert "example_module" in initialized
        
    def test_example_module_lifecycle(self, mock_app_container):
        """Жизненный цикл example_module"""
        reset_module_registry()
        registry = ModuleRegistry(modules_path=Path("./modules"))
        
        registry.discover_modules()
        registry.initialize_all(mock_app_container)
        registry.start_all()
        
        module = registry.get_module("example_module")
        assert module is not None
        
        registry.stop_all()
