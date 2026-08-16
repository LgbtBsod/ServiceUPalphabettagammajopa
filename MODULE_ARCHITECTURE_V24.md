# 🧩 Модульная Архитектура v24.0

> **⚠️ УСТАРЕЛО (см. AUDIT_REPORT_v21.md):** `core/module_registry.py`+
> `core/module_loader.py`+`modules/` удалены этой сессией как мёртвый код.
> Живая plugin-система — `core/plugin_system.py` + `plugins/`.

## Plugin System для Расширения Без Изменения Ядра

### 📖 Описание

Архитектура v24.0 реализует **плагин-систему**, которая позволяет расширять функционал приложения простым добавлением файлов в папку `modules/` **без изменения ядра** (`core/`) или основных сервисов.

### 🎯 Принципы

1. **Авто-регистрация**: Модули сканируются при старте приложения
2. **Базовые классы**: Единый интерфейс `ModuleBase` для всех модулей
3. **DI Интеграция**: Автоматическое внедрение зависимостей через контейнер
4. **Изоляция**: Ошибки в модуле не ломают ядро и другие модули
5. **Горячая перезагрузка**: Возможность обновлять модули без рестарта (опционально)
6. **Zero Modification**: Не требуется изменение кода ядра для добавления новых фич

### 📁 Структура

```
/workspace
├── core/
│   ├── module_registry.py    # Реестр и загрузчик модулей
│   ├── module_loader.py      # Интеграция с приложением
│   └── __init__.py           # Экспорт: ModuleBase, ModuleRegistry...
│
├── modules/                   # Папка для всех модулей расширения
│   ├── example_module/        # Пример модуля
│   │   ├── __init__.py        # Точка входа с метаданными
│   │   └── module.py          # Логика модуля (опционально)
│   │
│   └── my_custom_module/      # Ваш новый модуль
│       ├── __init__.py
│       ├── handlers.py
│       ├── config.yaml
│       └── gui_panel.py
│
└── main.py                    # Точка входа приложения
```

### 🚀 Быстрый Старт

#### Шаг 1: Создать папку модуля

```bash
mkdir -p modules/my_awesome_module
```

#### Шаг 2: Создать `__init__.py` с метаданными

```python
# modules/my_awesome_module/__init__.py
from core import ModuleBase

MODULE_NAME = "my_awesome_module"
MODULE_VERSION = "1.0.0"
MODULE_DESCRIPTION = "Мой крутой модуль для чего-то важного"
MODULE_AUTHOR = "Your Name"
MODULE_DEPENDENCIES = []  # Зависимости от других модулей


class MyAwesomeModule(ModuleBase):
    name = MODULE_NAME
    version = MODULE_VERSION
    description = MODULE_DESCRIPTION
    author = MODULE_AUTHOR
    dependencies = MODULE_DEPENDENCIES
    
    def on_init(self):
        self.log.info(f"✅ {self.name} инициализирован")
        
    def on_start(self):
        self.log.info(f"▶️ {self.name} запущен")
        # Доступ к сервисам:
        order_service = self.get_service("order_service")
        
    def on_stop(self):
        self.log.info(f"⏹️ {self.name} остановлен")
        
    def register_gui_components(self, gui_factory=None):
        # Регистрация своих GUI панелей
        pass
        
    def register_routes(self, router=None):
        # Регистрация API endpoints
        pass


__all__ = ["MyAwesomeModule"]
```

#### Шаг 3: Запустить приложение

Приложение автоматически обнаружит и загрузит ваш модуль!

```python
# В main.py или core/application.py
from core import initialize_modules, shutdown_modules, get_app

app = get_app()
initialize_modules(app_container=app.container)  # Авто-загрузка modules/
# ... работа приложения ...
shutdown_modules()  # Корректная остановка
```

### 🔌 API Базового Класса

#### ModuleBase

| Метод/Свойство | Описание |
|---------------|----------|
| `name` | Имя модуля (уникальное) |
| `version` | Версия по semver |
| `description` | Описание |
| `author` | Автор |
| `dependencies` | Список зависимостей (имена других модулей) |
| `log` | Логгер (автоматически создается) |
| `app` | DI контейнер приложения |
| `get_service(name)` | Получить сервис из контейнера |
| `get_repository(name)` | Получить репозиторий из контейнера |
| `on_init()` | Хук инициализации |
| `on_start()` | Хук запуска после старта приложения |
| `on_stop()` | Хук остановки перед закрытием |
| `register_gui_components(factory)` | Регистрация GUI компонентов |
| `register_routes(router)` | Регистрация HTTP роутов |

### 📊 ModuleRegistry

| Метод | Описание |
|-------|----------|
| `discover_modules()` | Сканирование папки modules/ |
| `initialize_all(container)` | Инициализация всех модулей |
| `start_all()` | Запуск всех модулей |
| `stop_all()` | Остановка всех модулей |
| `get_module(name)` | Получить экземпляр по имени |
| `list_modules()` | Список всех модулей с метаданными |

### 🎁 Преимущества

#### Для Разработчиков

✅ **Простота расширения**: Просто добавь файл в папку  
✅ **Изоляция**: Баги в модуле не ломают всё приложение  
✅ **DI из коробки**: Доступ ко всем сервисам через `self.get_service()`  
✅ **Логирование**: Автоматический логгер `self.log`  
✅ **Тестируемость**: Легко мокировать и тестировать отдельно  

#### Для Бизнеса

✅ **Быстрая разработка**: Новые фичи без риска сломать ядро  
✅ **Масштабируемость**: Можно создавать модули для разных клиентов  
✅ **Plugin Market**: Возможность продавать модули как дополнения  
✅ **A/B тестирование**: Включение/выключение фич конфигом  

### 📝 Примеры Использования

#### Пример 1: Модуль для Telegram-бота

```python
# modules/telegram_bot/__init__.py
from core import ModuleBase
import asyncio

MODULE_NAME = "telegram_bot"
MODULE_VERSION = "1.0.0"
MODULE_DESCRIPTION = "Telegram бот для уведомлений клиентов"
MODULE_AUTHOR = "ServiceUP Team"
MODULE_DEPENDENCIES = ["notification_service"]


class TelegramBotModule(ModuleBase):
    name = MODULE_NAME
    version = MODULE_VERSION
    description = MODULE_DESCRIPTION
    author = MODULE_AUTHOR
    dependencies = MODULE_DEPENDENCIES

    def on_init(self):
        self.bot_token = None  # Загрузить из конфига
        self.log.info("🤖 Telegram Bot модуль инициализирован")

    def on_start(self):
        config = self.get_service("config_service")
        self.bot_token = config.get("telegram.bot_token")

        # Запуск поллинга в фоне
        asyncio.create_task(self._run_polling())

    async def _run_polling(self):
        from aiogram import Bot, Dispatcher

        bot = Bot(token=self.bot_token)
        dp = Dispatcher()

        @dp.message()
        async def handle_message(message):
            # Обработка команд
            pass

        await dp.start_polling(bot)

    def on_stop(self):
        self.log.info("🤖 Telegram Bot остановлен")
```

#### Пример 2: Модуль с GUI панелью

```python
# modules/analytics_dashboard/__init__.py
from core import ModuleBase

MODULE_NAME = "analytics_dashboard"
MODULE_VERSION = "1.0.0"
MODULE_DESCRIPTION = "Панель аналитики с графиками"


class AnalyticsDashboardModule(ModuleBase):
    name = MODULE_NAME

    def register_gui_components(self, gui_factory=None):
        if gui_factory is None:
            return

        from .gui.analytics_panel import AnalyticsPanel

        # Регистрация панели в главном окне
        gui_factory.register_panel(
            "analytics", AnalyticsPanel, title="Аналитика", icon="chart_icon.png"
        )

        self.log.info("📊 Панель аналитики зарегистрирована")
```

#### Пример 3: Модуль с REST API

```python
# modules/web_api/__init__.py
from core import ModuleBase

MODULE_NAME = "web_api"
MODULE_VERSION = "2.0.0"
MODULE_DEPENDENCIES = ["auth_service"]


class WebAPIModule(ModuleBase):
    name = MODULE_NAME
    dependencies = MODULE_DEPENDENCIES
    
    def register_routes(self, router=None):
        if router is None:
            return
            
        @router.get("/api/v1/stats")
        async def get_stats():
            analytics = self.get_service("analytics_service")
            return analytics.get_summary()
            
        @router.post("/api/v1/orders")
        async def create_order(data: dict):
            order_service = self.get_service("order_service")
            return order_service.create(**data)
            
        self.log.info("🌐 API роуты зарегистрированы")
```

### 🔧 Конфигурация

Модули могут иметь свой конфиг:

```yaml
# modules/my_module/config.yaml
module:
  enabled: true
  log_level: INFO
  
settings:
  api_key: "${ENV_API_KEY}"  # Переменные окружения
  timeout: 30
  retry_count: 3
```

Загрузка конфига в модуле:

```python
def on_init(self):
    config_path = self.module_info.path / "config.yaml"
    if config_path.exists():
        import yaml

        with open(config_path) as f:
            self.config = yaml.safe_load(f)
```

### 🧪 Тестирование Модулей

```python
# tests/test_my_module.py
import pytest
from modules.my_module import MyModule
from core import CoreContainer


@pytest.fixture
def app_container():
    container = CoreContainer()
    container.wire(modules=["application", "infrastructure"])
    return container


def test_module_initialization(app_container):
    module = MyModule(app_container=app_container)
    module.on_init()
    assert module.name == "my_module"


def test_module_service_access(app_container):
    module = MyModule(app_container=app_container)
    service = module.get_service("order_service")
    assert service is not None
```

### 🎯 Best Practices

1. **Имена модулей**: Уникальные, lowercase, snake_case
2. **Версионирование**: Semver (major.minor.patch)
3. **Зависимости**: Минимизировать, указывать явно
4. **Логирование**: Использовать `self.log`, не создавать свои логи
5. **Исключения**: Ловить свои, не ломать другие модули
6. **Ресурсы**: Освобождать в `on_stop()`
7. **Конфиги**: Выносить в config.yaml, не хардкодить

### 📈 Roadmap

- [ ] Горячая перезагрузка модулей без рестарта
- [ ] UI для управления модулями (вкл/выкл)
- [ ] Marketplace модулей
- [ ] Зависимости между модулями (топологическая сортировка)
- [ ] Песочница для небезопасных модулей
- [ ] Статистика использования модулей

### 📚 Ссылки

- [Core Module Registry](../core/module_registry.py) - Исходный код реестра
- [Example Module](../modules/example_module/__init__.py) - Пример модуля
- [Base Classes](../core/base.py) - Базовые классы архитектуры

---

**ServiceUP v24.0** - Модульная архитектура для коммерческого использования  
© 2025 ServiceUP Team
