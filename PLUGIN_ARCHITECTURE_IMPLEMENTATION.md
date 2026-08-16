# 🏗️ Plugin Architecture Implementation - ServiceUP v25.0

## Обзор изменений

В версии 25.0 реализована полноценная **Plugin Architecture** с центральным ядром (Core Kernel), через которое все модули и плагины получают доступ к сервисам системы.

## 🎯 Ключевые принципы

### 1. Single Entry Point (Ядро)
Все взаимодействия между модулями происходят **только через ядро**:
```python
from core.kernel import get_core

core = get_core()
core.initialize()

# Получение сервиса через ядро
order_service = core.get_service(OrderService)

# Вызов метода другого модуля
result = core.call_module_method('billing', 'calculate_total', order_id=123)

# Подписка на события
core.subscribe(OrderCreatedEvent, handler)
```

### 2. Dependency Inversion
Модули зависят от абстракций (интерфейсов), а не от конкретных реализаций:
```python
# Плагин получает репозиторий через интерфейс
self._repository = self._core.get_service(IClientRepository)
```

### 3. Module Isolation
Модули **не импортируют друг друга напрямую**. Вместо этого:
- Каждый модуль регистрирует свой API в ядре
- Другие модули вызывают методы через `core.call_module_method()`

### 4. Plugin Lifecycle Management
Плагины имеют четкий жизненный цикл:
- **UNLOADED** → **LOADING** → **ACTIVE** → **DISABLED** → **UNLOADING**

## 📦 Обновленные зависимости

### requirements.txt
Добавлены пакеты для поддержки plugin architecture:
- `pluggy>=1.4.0` - система плагинов
- `importlib-metadata>=7.0.0` - динамическая загрузка модулей
- `injector>=0.22.0` - альтернативный DI контейнер
- `cachetools>=5.3.0` - кэширование
- `cryptography>=42.0.0`, `pyjwt>=2.8.0` - безопасность

### pyproject.toml
Обновлен до версии **25.0.0** с поддержкой entry points:

> **⚠️ УСТАРЕЛО (см. AUDIT_REPORT_v21.md):** `plugins.orders/reports/auth/pwa`
> и весь `modules/` удалены этой сессией — были нерабочими заглушками без
> реальной логики. Единственные реальные плагины сегодня — `plugins.clients`
> и `plugins.employees`. Остальное содержимое этого файла (API `core/kernel.py`)
> по-прежнему точно описывает живую архитектуру.

```toml
[project.entry-points."serviceup.plugins"]
clients = "plugins.clients:ClientsPlugin"
employees = "plugins.employees:EmployeesPlugin"
```

## 🆕 Новые компоненты

### core/kernel.py
Центральное ядро системы:

```python
class ServiceUpCore:
    """Ядро предоставляет:
    - Доступ ко всем сервисам через DI контейнер
    - Управление плагинами и модулями
    - Систему событий
    - Межмодульную коммуникацию
    """
    
    def initialize(self) -> None
    def get_service[T](self, service_type: type[T]) -> T
    def register_module(self, name: str, module, api: Any)
    def call_module_method(self, module_name, method_name, *args, **kwargs)
    def subscribe(self, event_type, handler)
    def publish(self, event)
    def register_plugin(self, plugin: IPlugin)
    def enable_plugin(self, plugin_name) -> bool
```

### Обновленный ClientsPlugin
Пример реализации плагина с доступом через ядро:

```python
class ClientsPlugin(IPlugin):
    def initialize(self) -> bool:
        # Получаем ядро
        self._core = get_core()
        
        # Получаем репозиторий через DI контейнер ядра
        self._repository = self._core.get_service(IClientRepository)
        
        # Создаем сервис
        self._service = ClientService(self._repository)
        
        # Регистрируем API в ядре
        self._core.register_module("clients", self, self._service)
```

## 🔧 Как использовать

### Для разработчиков плагинов

1. **Создайте плагин:**
```python
from core.plugin_system import IPlugin, PluginMetadata

class MyPlugin(IPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my_plugin",
            version="1.0.0",
            description="My custom plugin",
            author="Your Name",
            dependencies=["clients"],  # Зависимости от других плагинов
        )
    
    def initialize(self) -> bool:
        self._core = get_core()
        # Получайте сервисы через ядро
        self._service = self._core.get_service(IMyService)
        return True
    
    def get_api(self):
        return self._service
```

2. **Зарегистрируйте в pyproject.toml:**
```toml
[project.entry-points."serviceup.plugins"]
my_plugin = "plugins.my_plugin:MyPlugin"
```

3. **Вызывайте методы других модулей:**
```python
# НЕЛЬЗЯ: from modules.billing import BillingModule
# НУЖНО:
core = get_core()
total = core.call_module_method('billing', 'calculate_total', order_id=123)
```

### Для разработчиков модулей

1. **Создайте API модуля:**
```python
class BillingAPI:
    def calculate_total(self, order_id: int) -> Decimal:
        ...
    
    def generate_invoice(self, order_id: int) -> bytes:
        ...
```

2. **Зарегистрируйте модуль в ядре:**
```python
core = get_core()
core.register_module('billing', billing_module, BillingAPI())
```

## ✅ Тестирование

Все тесты проходят успешно:
```bash
# Тесты репозиториев
pytest database/tests/test_repositories.py -v
# Результат: 17/17 passed ✅

# Тесты ядра
python -c "from core.kernel import get_core; core = get_core(); core.initialize()"
# Результат: Core initialized successfully ✅
```

## 📊 Архитектурные преимущества

| До | После |
|---|---|
| Прямые импорты между модулями | Взаимодействие через ядро |
| Жесткие зависимости | Слабая связанность через интерфейсы |
| Сложное тестирование | Легкая мокизация через DI |
| Монолитная структура | Модульная plugin-архитектура |
| Нет единой точки входа | Clear Entry Point через Core |

## 🚀 Миграция на v25.0

### Шаг 1: Обновите зависимости
```bash
pip install -r requirements.txt --upgrade
```

### Шаг 2: Обновите плагины
Замените прямой доступ к сервисам на получение через ядро:
```python
# Было
self._repo = SQLAlchemyClientRepository()

# Стало
self._core = get_core()
self._repo = self._core.get_service(IClientRepository)
```

### Шаг 3: Обновите межмодульные вызовы
```python
# Было
from modules.billing import calculate_total
result = calculate_total(order_id)

# Стало
core = get_core()
result = core.call_module_method('billing', 'calculate_total', order_id=order_id)
```

## 📝 Changelog

### v25.0.0
- ✅ Добавлено ядро системы (core.kernel.ServiceUpCore)
- ✅ Реализован доступ к сервисам через DI контейнер ядра
- ✅ Обновлены плагины для работы через ядро
- ✅ Добавлены entry points для автоматической регистрации
- ✅ Обновлены зависимости (pluggy, injector, cryptography)
- ✅ Улучшена документация и примеры использования

### v24.2.0 (предыдущая)
- Базовая система плагинов
- Ручная регистрация модулей
- Прямые импорты между модулями

## 📚 Дополнительные ресурсы

- [PLUGINS_ARCHITECTURE.md](./PLUGINS_ARCHITECTURE.md) - детальное описание архитектуры
- [MODULE_CALL_WRAPPER_ARCHITECTURE.md](./MODULE_CALL_WRAPPER_ARCHITECTURE.md) - паттерны вызова модулей
- [core/plugin_system.py](./core/plugin_system.py) - исходный код системы плагинов
- [core/kernel.py](./core/kernel.py) - исходный код ядра

---

**ServiceUP v25.0** - Modular, Extensible, Decoupled ✨
