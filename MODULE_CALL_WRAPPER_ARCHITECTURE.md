# 🎯 Модульная Архитектура v24.1 - Module Call Wrapper

## Обзор

Реализована архитектура **"Module Call Wrapper"** - единая точка входа для всех модулей, которая автоматически предоставляет все необходимые зависимости из ядра без необходимости редактирования базовых классов.

## Ключевые Преимущества

### 1. **Простота Добавления Модулей**
Теперь для создания нового модуля достаточно:
```python
# modules/my_module_impl/__init__.py
from modules._module_call import ModuleBase, log, CoreException

class MyModule(ModuleBase):
    name = "my_module"
    version = "1.0.0"
    
    def on_init(self):
        self.log.info("Module initialized")
```

### 2. **Единый Импорт Всех Зависимостей**
Файл `modules/_module_call.py` автоматически импортирует:
- ✅ **Логгер** - `log`, `get_logger`
- ✅ **Исключения** - `CoreException`, `ServiceException`, `RepositoryException`
- ✅ **Базовые классы** - `ModuleBase`, `BaseService`, `BaseRepository`, `BaseViewModel`
- ✅ **DI Контейнер** - `CoreApplication`

### 3. **Никаких Изменений в Ядре**
При добавлении новых модулей:
- ❌ Не нужно менять `core/base.py`
- ❌ Не нужно менять `core/module_registry.py`
- ❌ Не нужно менять `core/logging/exceptions.py`
- ✅ Просто создайте файл в `modules/` и используйте готовый wrapper

## Структура

```
/workspace
├── core/
│   ├── base.py              # Базовые классы (не требует изменений)
│   ├── module_registry.py   # Реестр модулей (авто-сканирование)
│   └── logging/
│       ├── logger.py        # Централизованный логгер
│       └── exceptions.py    # Все исключения проекта
│
└── modules/
    ├── _module_call.py      # ⭐ НОВАЯ ТОЧКА ВХОДА ⭐
    │   - Импортирует всё из core/
    │   - Предоставляет ModuleBase с авто-логгером
    │   - Экспортирует все зависимости
    │
    ├── billing.py           # Файл-обертка (метаданные)
    └── billing_impl/        # Папка реализации
        ├── __init__.py      # Использует: from modules._module_call import ...
        ├── service.py       # Бизнес-логика
        └── exceptions.py    # Исключения модуля
```

## Пример Использования

### Шаг 1: Создайте файл-обертку (метаданные)
```python
# modules/crm_integration.py
MODULE_NAME = "crm_integration"
MODULE_IMPL_PATH = "crm_integration_impl"
MODULE_VERSION = "1.0.0"
MODULE_DESCRIPTION = "Интеграция с CRM системами"
MODULE_AUTHOR = "Development Team"
MODULE_DEPENDENCIES = ["billing"]
```

### Шаг 2: Создайте папку реализации
```
modules/crm_integration_impl/
  ├── __init__.py      # Точка входа
  ├── sync_service.py  # Синхронизация данных
  ├── mapping.py       # Маппинг полей
  └── config.yaml      # Конфигурация
```

### Шаг 3: Используйте Wrapper в модуле
```python
# modules/crm_integration_impl/__init__.py
from modules._module_call import ModuleBase, log, CoreException, ServiceException

class CRMIntegrationModule(ModuleBase):
    name = "crm_integration"
    version = "1.0.0"
    
    def on_init(self):
        self.log.info(f"🔗 {self.name} v{self.version} инициализирован")
        
        # Безопасное выполнение с авто-логированием
        result = self.safe_execute(
            lambda: self._connect_to_crm(),
            default=None,
            raise_on_error=False
        )
        
    def _connect_to_crm(self):
        # Бизнес-логика подключения к CRM
        return {"status": "connected"}
    
    def on_start(self):
        # Получение сервиса из DI контейнера
        order_service = self.get_service("order_service")
        self.log.info("▶️ Модуль запущен")
        
    def on_stop(self):
        self.log.info("⏹️ Модуль остановлен")

__all__ = ["CRMIntegrationModule"]
```

## Что Автоматически Доступно в Модуле

Наследуя `ModuleBase` из `_module_call`, вы получаете:

| Метод/Свойство | Описание |
|----------------|----------|
| `self.log` | Логгер с именем модуля (`module.billing`) |
| `self.safe_execute(func, default, raise_on_error)` | Безопасное выполнение с обработкой исключений |
| `self.app` | Доступ к DI контейнеру (CoreApplication) |
| `self.get_service(ServiceType)` | Получение сервиса из контейнера |
| `self.get_repository(RepoType)` | Получение репозитория из контейнера |
| `self.on_init()` | Hook инициализации (переопределить) |
| `self.on_start()` | Hook запуска (переопределить) |
| `self.on_stop()` | Hook остановки (переопределить) |

## Тестирование

```bash
# Проверка импортов
python -c "from modules._module_call import ModuleBase, log, CoreException; print('✅ OK')"

# Проверка модуля
python -c "from modules.billing_impl import BillingModule; m = BillingModule(); m.on_init()"
```

## Миграция Существующих Модулей

### До (v24.0):
```python
from core.module_registry import ModuleBase
import logging
from core.logging.exceptions import CoreException

logger = logging.getLogger(__name__)

class OldModule(ModuleBase):
    def __init__(self, app_container=None):
        super().__init__(app_container)
        self._log = logging.getLogger(f"module.{self.name}")
```

### После (v24.1):
```python
from modules._module_call import ModuleBase, log, CoreException

class NewModule(ModuleBase):
    def on_init(self):
        self.log.info("Автоматический логгер работает!")
        # safe_execute доступен из коробки
        result = self.safe_execute(lambda: do_something(), default=None)
```

## Расширение в Будущем

Если потребуется добавить новые зависимости:

1. **Добавьте импорт в `_module_call.py`**:
```python
from core.new_feature import NewFeature
__all__.append('NewFeature')
```

2. **Все модули автоматически получат доступ**:
```python
from modules._module_call import NewFeature
# Готово!
```

## Заключение

Архитектура Module Call Wrapper обеспечивает:
- ✅ **Zero Configuration** - никаких настроек для новых модулей
- ✅ **Convention over Configuration** - следуйте шаблону, всё работает автоматически
- ✅ **Separation of Concerns** - ядро не знает о конкретных модулях
- ✅ **Easy Testing** - легкое тестирование через моки
- ✅ **Scalability** - неограниченное количество модулей

**Проект готов к масштабированию!** 🚀
