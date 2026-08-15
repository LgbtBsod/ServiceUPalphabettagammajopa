# Модульная Архитектура v24.2 - Wrapper-Based Plugin System

## 📋 Обзор

Архитектура v24.2 реализует паттерн **File-Wrapper** для создания модулей без изменения ядра проекта. Это позволяет расширять функциональность простым добавлением файлов в папку `modules/`.

## 🎯 Принципы

1. **Файлы-обертки**: Каждый модуль имеет файл-обертку (`module_*.py`) который импортирует реализацию
2. **Авто-регистрация**: Реестр сканирует файлы `module_*.py` и legacy папки
3. **Базовые классы**: Единый интерфейс для всех модулей с авто-инъекцией логгера и исключений
4. **DI Интеграция**: Автоматическое внедрение зависимостей через ядро
5. **Изоляция**: Ошибки в модуле не ломают ядро

## 📁 Структура

```
/workspace
├── core/
│   ├── module_registry.py    # Реестр и загрузчик модулей
│   ├── base.py               # Базовые классы (ModuleBase, BaseService, etc.)
│   └── logging/              # Централизованное логирование
│       ├── logger.py
│       └── exceptions.py
│
├── modules/
│   ├── module_calls.py       # Файл-обертка: from plugins.calls import *
│   ├── module_db_access.py   # Файл-обертка: from plugins.db_access import *
│   └── _module_call.py       # Пример документации (не рабочий модуль)
│
├── plugins/ (или modules/*_impl)
│   ├── calls/
│   │   ├── __init__.py       # Точка входа, экспортирует CallModule
│   │   ├── service.py        # Логика звонков
│   │   ├── exceptions.py     # Исключения модуля
│   │   └── config.yaml       # Конфигурация
│   │
│   └── db_access/
│       ├── __init__.py       # Точка входа, экспортирует DBAccessModule
│       ├── repository.py     # Репозитории
│       └── config.yaml       # Конфигурация
│
└── tests/
    └── test_modules.py       # Тесты модульной системы
```

## 🚀 Как создать новый модуль

### Шаг 1: Создайте файл-обертку

Создайте файл `modules/module_myfeature.py`:

```python
# modules/module_myfeature.py
from plugins.myfeature import MyFeatureModule

__all__ = ["MyFeatureModule"]
```

**Важно**: 
- Имя файла должно начинаться с `module_`
- Файл должен импортировать класс модуля из реализации
- Укажите `__all__` для явного экспорта

### Шаг 2: Создайте папку реализации

Создайте папку `plugins/myfeature/` со следующей структурой:

```
plugins/myfeature/
├── __init__.py       # Точка входа
├── service.py        # Бизнес-логика
├── exceptions.py     # Исключения модуля
├── models.py         # Модели данных
└── config.yaml       # Конфигурация (опционально)
```

### Шаг 3: Реализуйте класс модуля

В `plugins/myfeature/__init__.py`:

```python
from core.module_registry import ModuleBase


class MyFeatureModule(ModuleBase):
    name = "myfeature"
    version = "1.0.0"
    description = "Модуль моей фичи"
    author = "Ваше Имя"
    dependencies = []  # Зависимости от других модулей

    def on_init(self):
        """Вызывается при инициализации модуля"""
        self.log.info(f"{self.name} initialized")

    def on_start(self):
        """Вызывается при запуске приложения"""
        self.log.info(f"{self.name} started")

        # Получаем сервис из ядра через DI
        my_service = self.get_service("my_service")

    def on_stop(self):
        """Вызывается при остановке приложения"""
        self.log.info(f"{self.name} stopped")
```

### Шаг 4: Используйте базовые возможности

Модуль автоматически получает:

```python
class MyFeatureModule(ModuleBase):
    def on_start(self):
        # 1. Логгер (авто-настроен с именем модуля)
        self.log.info("Starting feature")
        self.log.debug("Debug info")
        self.log.error("Error occurred")

        # 2. Безопасное выполнение с логированием
        result = self.safe_execute(
            lambda: self.risky_operation(), default=None, raise_on_error=False
        )

        # 3. Доступ к DI контейнеру
        order_service = self.get_service("order_service")
        client_repo = self.get_repository("client_repository")

        # 4. Обработка ошибок модуля
        try:
            self.do_something()
        except self.ModuleError as e:
            self.log.warning(f"Business error: {e}")
```

### Шаг 5: Добавьте исключения модуля (опционально)

В `plugins/myfeature/exceptions.py`:

```python
from core.logging.exceptions import CoreException


class MyFeatureError(CoreException):
    """Базовое исключение для модуля myfeature"""

    pass


class MyFeatureNotFoundError(MyFeatureError):
    """Ресурс не найден"""

    pass
```

В `plugins/myfeature/__init__.py`:

```python
from core.module_registry import ModuleBase
from .exceptions import MyFeatureError


class MyFeatureModule(ModuleBase):
    name = "myfeature"

    # Переопределяем базовое исключение
    ModuleError = MyFeatureError

    def on_init(self):
        self.log.info("Module initialized with custom exceptions")
```

## 📖 API Базового Класса

### ModuleBase

| Метод/Свойство | Описание |
|----------------|----------|
| `name` | Имя модуля (строка) |
| `version` | Версия модуля (семантическая) |
| `description` | Описание модуля |
| `author` | Автор модуля |
| `dependencies` | Список зависимостей от других модулей |
| `ModuleError` | Базовый класс исключений модуля |
| `log` | Логгер (настраивается автоматически) |
| `app` | DI контейнер приложения |
| `get_service(name)` | Получить сервис из DI контейнера |
| `get_repository(name)` | Получить репозиторий из DI контейнера |
| `safe_execute(func, default, raise_on_error)` | Безопасное выполнение с логированием |
| `on_init()` | Hook инициализации |
| `on_start()` | Hook запуска |
| `on_stop()` | Hook остановки |
| `register_routes(router)` | Регистрация API роутов |
| `register_gui_components(factory)` | Регистрация GUI компонентов |

## 🔍 Как работает реестр

### Discover Modules

Реестр сканирует два формата:

1. **Файлы-обертки** (`module_*.py`):
   - Загружает файл
   - Ищет классы-наследники `ModuleBase`
   - Читает метаданные из класса
   - Пытается найти папку реализации (`{name}_impl` или `plugins/{name}`)

2. **Legacy папки** (`*/__init__.py`):
   - Для обратной совместимости
   - Пропускает если модуль уже загружен через wrapper
   - Пропускает папки `*_impl`

### Initialize Modules

1. Сортирует модули по зависимостям (топологическая сортировка)
2. Создает экземпляр с `app_container` и `module_info`
3. Вызывает `on_init()` хук
4. Сохраняет экземпляр в реестр

## 📊 Примеры использования

### Пример 1: Простой модуль без зависимостей

```python
# modules/module_logger.py
from plugins.logger import LoggerModule

__all__ = ["LoggerModule"]

# plugins/logger/__init__.py
from core.module_registry import ModuleBase


class LoggerModule(ModuleBase):
    name = "logger"
    version = "1.0.0"

    def on_start(self):
        self.log.info("Logger module started")
```

### Пример 2: Модуль с зависимостями

```python
# modules/module_crm.py
from plugins.crm import CRMModule

__all__ = ["CRMModule"]

# plugins/crm/__init__.py
from core.module_registry import ModuleBase


class CRMModule(ModuleBase):
    name = "crm"
    version = "2.0.0"
    dependencies = [
        "clients",
        "orders",
    ]  # Требуется чтобы эти модули загрузились раньше

    def on_start(self):
        client_service = self.get_service("client_service")
        order_service = self.get_service("order_service")
        self.log.info("CRM module started with dependencies")
```

### Пример 3: Модуль с GUI компонентами

```python
# plugins/dashboard/__init__.py
from core.module_registry import ModuleBase


class DashboardModule(ModuleBase):
    name = "dashboard"

    def register_gui_components(self, gui_factory):
        """Регистрация GUI компонентов"""
        panel = DashboardPanel(gui_factory.main_window)
        gui_factory.register_panel("dashboard", panel)
        self.log.info("Dashboard GUI components registered")
```

### Пример 4: Модуль с HTTP API

```python
# plugins/api/__init__.py
from core.module_registry import ModuleBase


class ApiModule(ModuleBase):
    name = "api"

    def register_routes(self, router):
        """Регистрация API роутов"""

        @router.get("/api/v1/status")
        async def get_status():
            return {"status": "ok", "module": self.name}

        self.log.info("API routes registered")
```

## ✅ Преимущества архитектуры

1. **Без изменения ядра**: Новые модули добавляются без правки `core/`
2. **Простое расширение**: Достаточно добавить 2 файла (wrapper + impl)
3. **Изоляция**: Ошибки в модуле не ломают всё приложение
4. **Автоматизация**: Логгер, DI, исключения настраиваются автоматически
5. **Гибкость**: Поддержка legacy папок для обратной совместимости
6. **Тестируемость**: Модули легко мокировать через базовые классы

## 🧪 Тестирование

```python
# tests/test_my_module.py
import pytest
from unittest.mock import Mock
from plugins.myfeature import MyFeatureModule


def test_module_initialization():
    app_container = Mock()
    module = MyFeatureModule(app_container=app_container)

    assert module.name == "myfeature"
    assert module.version == "1.0.0"
    assert module.log is not None


def test_module_safe_execute():
    app_container = Mock()
    module = MyFeatureModule(app_container=app_container)

    result = module.safe_execute(lambda: 42, default=0)
    assert result == 42

    result = module.safe_execute(lambda: 1 / 0, default=0)
    assert result == 0  # Без падения, с логированием
```

## 📝 Changelog

### v24.2 (Текущая)
- ✅ Добавлен паттерн File-Wrapper для модулей
- ✅ Авто-загрузка исключений из модулей
- ✅ Поддержка двух форматов (wrappers + legacy)
- ✅ Передача `module_info` в конструктор модуля
- ✅ Улучшенное логирование с учетом пути реализации

### v24.1
- ✅ Базовые классы для сервисов, репозиториев, GUI
- ✅ Mixins для логирования и обработки исключений
- ✅ DI интеграция через базовые классы

### v24.0
- ✅ Первая версия модульной системы
- ✅ Авто-регистрация модулей
- ✅ Жизненный цикл (init/start/stop)

## 🎯 Следующие шаги

1. Создать рабочие модули-примеры (`module_calls.py`, `module_db_access.py`)
2. Добавить документацию по созданию GUI компонентов
3. Реализовать полноценную топологическую сортировку зависимостей
4. Добавить поддержку горячей перезагрузки модулей
5. Создать CLI для управления модулями (`module create`, `module list`, etc.)
