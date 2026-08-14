"""
Модульная Архитектура v24.2 - Wrapper-Based Plugin System

Эта архитектура позволяет расширять функционал проекта простым добавлением файлов-оберток в папку modules/
без изменения ядра (core/) или основных сервисов.

Принципы:
1. Файлы-обертки: Каждый модуль имеет файл-обертку (module_*.py) с import * из реализации
2. Авто-регистрация: Реестр сканирует файлы module_*.py и legacy папки
3. Базовые классы: Единый интерфейс для всех модулей с авто-инъекцией логгера и исключений
4. DI Интеграция: Автоматическое внедрение зависимостей через ядро
5. Изоляция: Ошибки в модуле не ломают ядро

Структура:
/modules
  module_calls.py          # Файл-обертка: from plugins.calls import *
  module_db_access.py      # Файл-обертка: from plugins.db_access import *
  
/plugins (или modules/*_impl)
  /calls
    __init__.py            # Точка входа, экспортирует CallModule
    service.py             # Логика звонков
    exceptions.py          # Исключения модуля
    
  /db_access
    __init__.py            # Точка входа, экспортирует DBAccessModule
    repository.py          # Репозитории
    config.yaml            # Конфигурация

/core
  module_registry.py       # Реестр и загрузчик модулей
  base.py                  # Базовые классы с логгером и исключениями
"""

import importlib
import importlib.util
import pkgutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Type, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ModuleInfo:
    """Информация о зарегистрированном модуле"""
    name: str
    path: Path
    version: str = "1.0.0"
    description: str = ""
    author: str = "Unknown"
    enabled: bool = True
    instance: Any = None
    dependencies: List[str] = field(default_factory=list)
    wrapper_file: Optional[Path] = None  # Путь к файлу-обертке
    impl_path: Optional[Path] = None     # Путь к реализации
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "enabled": self.enabled,
            "dependencies": self.dependencies,
            "wrapper_file": str(self.wrapper_file) if self.wrapper_file else None,
            "impl_path": str(self.impl_path) if self.impl_path else None
        }


class ModuleBase:
    """
    Базовый класс для всех модулей.
    
    Автоматически предоставляет:
    - self.log - логгер (настраивается автоматически)
    - self.safe_execute() - безопасное выполнение с логированием
    - self.app - доступ к DI контейнеру
    - self.get_service() - получение сервиса из ядра
    - self.ModuleError - базовое исключение модуля
    
    Пример создания модуля:
    
    # plugins/calls/__init__.py
    from core.base import ModuleBase
    
    class CallModule(ModuleBase):
        name = "calls"
        version = "1.0.0"
        
        def on_init(self):
            self.log.info("Call module initialized")
            
        def on_start(self):
            # Получаем сервис из ядра
            call_service = self.get_service("call_service")
            self.log.info("Call module started")
    
    # modules/module_calls.py (файл-обертка)
    from plugins.calls import CallModule
    __all__ = ['CallModule']
    """
    
    name: str = "base_module"
    version: str = "1.0.0"
    description: str = "Base module"
    author: str = "System"
    dependencies: List[str] = []
    
    # Базовое исключение для всех модулей (может быть переопределено)
    ModuleError = Exception
    
    def __init__(self, app_container=None, module_info: Optional[ModuleInfo] = None):
        self._app = app_container
        self._module_info = module_info
        
        # Авто-настройка логгера с учетом пути реализации
        log_name = f"module.{self.name}"
        if module_info and module_info.impl_path:
            log_name = f"module.{module_info.impl_path.name}.{self.name}"
        
        self._log = logging.getLogger(log_name)
        
        # Авто-загрузка исключений из модуля если есть
        self._load_module_exceptions()
        
    def _load_module_exceptions(self):
        """Загружает исключения из модуля если они определены"""
        if hasattr(self.__class__, 'ModuleException'):
            self.ModuleError = self.__class__.ModuleException
    
    @property
    def log(self):
        return self._log
        
    @property
    def app(self):
        if self._app is None:
            raise RuntimeError("App container not injected")
        return self._app
        
    def get_service(self, service_name: str):
        """Получить сервис из DI контейнера"""
        return self.app.get_service(service_name)
        
    def get_repository(self, repo_name: str):
        """Получить репозиторий из DI контейнера"""
        return self.app.get_repository(repo_name)
        
    def safe_execute(self, func, default=None, raise_on_error=False):
        """Безопасное выполнение с автоматическим логированием"""
        try:
            return func()
        except self.ModuleError as e:
            self.log.warning(f"Business error in {self.name}: {e}")
            if raise_on_error:
                raise
            return default
        except Exception as e:
            self.log.exception(f"System error in {self.name}: {e}")
            if raise_on_error:
                raise self.ModuleError(str(e))
            return default
        
    def on_init(self):
        """Вызывается при инициализации модуля"""
        pass
        
    def on_start(self):
        """Вызывается при запуске приложения"""
        pass
        
    def on_stop(self):
        """Вызывается при остановке приложения"""
        pass
        
    def register_routes(self, router=None):
        """Регистрация API роутов (если есть HTTP сервер)"""
        pass
        
    def register_gui_components(self, gui_factory=None):
        """Регистрация GUI компонентов"""
        pass


class ModuleRegistry:
    """
    Реестр и загрузчик модулей.
    
    Автоматически сканирует папку modules/ и загружает все модули.
    Управляет жизненным циклом: init -> start -> stop
    
    Использование:
        registry = ModuleRegistry(modules_path=Path("./modules"))
        registry.discover_modules()
        registry.initialize_all(app_container)
        registry.start_all()
        # ... работа приложения ...
        registry.stop_all()
    """
    
    def __init__(self, modules_path: Optional[Path] = None):
        self.modules_path = modules_path or Path(__file__).parent.parent / "modules"
        self.modules: Dict[str, ModuleInfo] = {}
        self._module_classes: Dict[str, Type[ModuleBase]] = {}
        
    def discover_modules(self) -> List[str]:
        """
        Сканирует папку modules/ и находит все доступные модули.
        
        Поддерживает два формата:
        1. Файлы-обертки: module_*.py (импортируют из plugins/*)
        2. Legacy папки: */__init__.py (старый формат)
        
        Возвращает список имен найденных модулей.
        """
        if not self.modules_path.exists():
            self.modules_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created modules directory: {self.modules_path}")
            return []
            
        discovered = []
        
        # 1. Сканируем файлы-обертки (module_*.py)
        for wrapper_file in self.modules_path.glob("module_*.py"):
            if wrapper_file.name.startswith("_"):
                continue
                
            try:
                # Загружаем файл-обертку
                spec = importlib.util.spec_from_file_location(
                    f"modules.{wrapper_file.stem}", 
                    wrapper_file
                )
                if spec is None or spec.loader is None:
                    continue
                    
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Ищем классы-наследники ModuleBase
                module_class = None
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, ModuleBase) and 
                        attr is not ModuleBase):
                        module_class = attr
                        break
                        
                if module_class is None:
                    logger.warning(f"No ModuleBase subclass found in {wrapper_file.name}")
                    continue
                
                # Читаем метаданные из класса или файла
                name = getattr(module_class, 'name', wrapper_file.stem.replace('module_', ''))
                version = getattr(module_class, 'version', '1.0.0')
                description = getattr(module_class, 'description', '')
                author = getattr(module_class, 'author', 'Unknown')
                deps = getattr(module_class, 'dependencies', [])
                
                # Пытаемся найти путь к реализации через __file__ модуля
                impl_path = None
                if hasattr(module, '__file__') and module.__file__:
                    # Предполагаем что реализация в соседней папке с тем же именем
                    potential_impl = self.modules_path / f"{name}_impl"
                    if potential_impl.exists():
                        impl_path = potential_impl
                    # Или ищем в plugins/
                    plugins_impl = self.modules_path.parent / "plugins" / name
                    if plugins_impl.exists():
                        impl_path = plugins_impl
                
                module_info = ModuleInfo(
                    name=name,
                    path=Path(wrapper_file),
                    version=version,
                    description=description,
                    author=author,
                    dependencies=deps,
                    wrapper_file=Path(wrapper_file),
                    impl_path=impl_path
                )
                
                self.modules[name] = module_info
                self._module_classes[name] = module_class
                discovered.append(name)
                
                logger.info(f"Discovered wrapper module: {name} v{version} (impl: {impl_path.name if impl_path else 'N/A'})")
                
            except Exception as e:
                logger.exception(f"Failed to discover wrapper module {wrapper_file.name}: {e}")
        
        # 2. Сканируем legacy папки (для обратной совместимости)
        for item in self.modules_path.iterdir():
            if not item.is_dir():
                continue
                
            if item.name.startswith("_") or item.name.startswith("."):
                continue
            
            # Пропускаем если это уже обработано как impl для wrapper
            if item.name.endswith("_impl"):
                continue
                
            module_file = item / "__init__.py"
            if not module_file.exists():
                continue
                
            # Пропускаем если модуль уже загружен через wrapper
            if item.stem in self.modules:
                continue
                
            try:
                # Загружаем метаданные модуля
                spec = importlib.util.spec_from_file_location(
                    f"modules.{item.name}", 
                    module_file
                )
                if spec is None or spec.loader is None:
                    continue
                    
                module = importlib.util.module_from_spec(spec)
                
                # Временная загрузка для чтения метаданных
                spec.loader.exec_module(module)
                
                # Читаем метаданные
                name = getattr(module, "MODULE_NAME", item.name)
                version = getattr(module, "MODULE_VERSION", "1.0.0")
                description = getattr(module, "MODULE_DESCRIPTION", "")
                author = getattr(module, "MODULE_AUTHOR", "Unknown")
                deps = getattr(module, "MODULE_DEPENDENCIES", [])
                
                # Находим класс модуля (наследник ModuleBase)
                module_class = None
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, ModuleBase) and 
                        attr is not ModuleBase):
                        module_class = attr
                        break
                        
                if module_class is None:
                    logger.warning(f"No ModuleBase subclass found in {item.name}")
                    continue
                
                module_info = ModuleInfo(
                    name=name,
                    path=item,
                    version=version,
                    description=description,
                    author=author,
                    dependencies=deps,
                    impl_path=item  # Для legacy папок path = impl_path
                )
                
                self.modules[name] = module_info
                self._module_classes[name] = module_class
                discovered.append(name)
                
                logger.info(f"Discovered legacy module: {name} v{version}")
                
            except Exception as e:
                logger.exception(f"Failed to discover legacy module {item.name}: {e}")
                
        return discovered
        
    def initialize_all(self, app_container) -> Dict[str, ModuleBase]:
        """
        Инициализирует все обнаруженные модули.
        
        Создает экземпляры модулей и вызывает on_init().
        Передаёт module_info в конструктор для доступа к метаданным.
        """
        initialized = {}
        
        # Сортируем по зависимостям (простая топологическая сортировка)
        sorted_modules = self._sort_by_dependencies()
        
        for name in sorted_modules:
            if name not in self._module_classes:
                continue
                
            module_class = self._module_classes[name]
            module_info = self.modules[name]
            
            try:
                # Создаем экземпляр с инъекцией контейнера и метаданных
                instance = module_class(app_container=app_container, module_info=module_info)
                module_info.instance = instance
                
                # Вызываем hook инициализации
                instance.on_init()
                
                initialized[name] = instance
                logger.info(f"Initialized module: {name}")
                
            except Exception as e:
                logger.exception(f"Failed to initialize module {name}: {e}")
                module_info.enabled = False
                
        return initialized
        
    def start_all(self):
        """Запускает все инициализированные модули (вызывает on_start)"""
        for name, info in self.modules.items():
            if not info.enabled or info.instance is None:
                continue
                
            try:
                info.instance.on_start()
                logger.info(f"Started module: {name}")
            except Exception as e:
                logger.exception(f"Failed to start module {name}: {e}")
                
    def stop_all(self):
        """Останавливает все модули (вызывает on_stop)"""
        for name, info in reversed(list(self.modules.items())):
            if not info.enabled or info.instance is None:
                continue
                
            try:
                info.instance.on_stop()
                logger.info(f"Stopped module: {name}")
            except Exception as e:
                logger.exception(f"Failed to stop module {name}: {e}")
                
    def get_module(self, name: str) -> Optional[ModuleBase]:
        """Получить экземпляр модуля по имени"""
        info = self.modules.get(name)
        return info.instance if info else None
        
    def list_modules(self) -> List[Dict]:
        """Список всех модулей с метаданными"""
        return [info.to_dict() for info in self.modules.values()]
        
    def _sort_by_dependencies(self) -> List[str]:
        """Простая топологическая сортировка по зависимостям"""
        # TODO: Реализовать полноценную топологическую сортировку
        return list(self.modules.keys())


# Глобальный экземпляр реестра (singleton)
_global_registry: Optional[ModuleRegistry] = None


def get_module_registry(modules_path: Optional[Path] = None) -> ModuleRegistry:
    """Получить глобальный реестр модулей"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ModuleRegistry(modules_path)
    return _global_registry


def reset_module_registry():
    """Сбросить глобальный реестр (для тестов)"""
    global _global_registry
    _global_registry = None
