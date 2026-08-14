# Рефакторинг ServiceUP v16.0 - Архитектурное руководство

## Обзор изменений

Этот документ описывает масштабный рефакторинг приложения ServiceUP в соответствии с принципами:
- **SOLID** - принципы объектно-ориентированного проектирования
- **DRY** - Don't Repeat Yourself
- **SRP** - Single Responsibility Principle
- **SSOT** - Single Source of Truth
- **Clean Architecture** - чистая архитектура с разделением на слои

## Новая архитектура

### Структура модулей

```
/workspace/
├── core/                      # Ядро приложения
│   └── __init__.py
│
├── domain/                    # Доменный слой (бизнес-логика)
│   ├── __init__.py
│   ├── entities.py           # Бизнес-сущности (Device, Client, WorkItem, Photo)
│   ├── aggregates.py         # Агрегаты (OrderAggregate)
│   ├── events/               # Доменные события
│   │   ├── __init__.py
│   │   └── events.py
│   └── services/             # Доменные сервисы
│       ├── __init__.py
│       ├── order_service.py
│       ├── client_service.py
│       └── notification_service.py
│
├── infrastructure/           # Инфраструктурный слой
│   ├── __init__.py
│   ├── db/                   # Работа с БД
│   │   ├── __init__.py
│   │   └── repositories.py   # Репозитории (DeviceRepository, ClientRepository)
│   ├── licensing/            # Лицензирование
│   │   ├── __init__.py
│   │   ├── license_service.py
│   │   ├── license_repository.py
│   │   └── hardware_info.py
│   └── pwa/                  # PWA сервер
│
├── application/              # Слой приложений (use cases)
│   └── __init__.py
│
├── interfaces/               # Слои интерфейсов
│   ├── gui/                  # Desktop GUI (customtkinter)
│   └── api/                  # REST API (для PWA)
│
└── shared/                   # Общие утилиты и константы
    └── __init__.py
```

## Ключевые изменения

### 1. Domain-Driven Design (DDD)

#### Сущности (Entities)
- `Device` - устройство в ремонте
- `Client` - клиент сервисного центра
- `WorkItem` - элемент работы
- `Photo` - фотография
- `RepairHistory` - история ремонта
- `FinanceRecord` - финансовая запись

Все сущности используют Python `dataclasses` со следующими возможностями:
- `slots=True` - экономия памяти
- Типизация через type hints
- Методы сериализации `to_dict()` / `from_dict()`

#### Агрегаты (Aggregates)
- `OrderAggregate` - агрегат заказа, объединяющий Device, Client и историю

Агрегат обеспечивает:
- Целостность бизнес-транзакций
- Бизнес-валидацию
- Проверку переходов статусов

#### Доменные события (Domain Events)
- `OrderCreatedEvent`
- `OrderStatusChangedEvent`
- `OrderCompletedEvent`
- `ClientCreatedEvent`
- `WorkItemAddedEvent`
- `PhotoAddedEvent`

События реализуют Event-Driven Architecture для слабой связанности.

### 2. Repository Pattern

Репозитории абстрагируют работу с базой данных:

```python
class DeviceRepository:
    def get(self, order_id: int) -> Optional[Device]
    def get_by_order_number(self, order_number: str) -> Optional[Device]
    def get_all(self, filters: dict = None) -> List[Device]
    def save(self, device: Device) -> Device
    def delete(self, order_id: int) -> bool
    def search(self, query: str) -> List[Device]
```

Преимущества:
- Тестируемость (можно подменить mock-репозиторием)
- Независимость от конкретной БД
- Централизованная логика доступа к данным

### 3. Unit of Work

`UnitOfWork` гарантирует атомарность операций:

```python
with UnitOfWork(db_connection) as uow:
    device = uow.devices.get(order_id)
    client = uow.clients.get_by_phone(phone)
    # Все изменения сохранятся атомарно
```

### 4. Dependency Injection

Сервисы используют инъекцию зависимостей через Protocols:

```python
class OrderService:
    def __init__(
        self,
        repository: RepositoryProtocol,
        event_dispatcher: Optional[EventDispatcherProtocol] = None,
    ):
        self._repository = repository
        self._event_dispatcher = event_dispatcher
```

### 5. Multi-threading Support

Для многопоточности используются:
- `concurrent.futures.ThreadPoolExecutor` - для параллельных задач
- `threading.Lock` - для синхронизации доступа к общим ресурсам
- `queue.Queue` - для потокобезопасной передачи данных

Пример использования в PWA сервере:
```python
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)
future = executor.submit(long_running_task, arg1, arg2)
result = future.result()
```

### 6. License Service

Новый сервис лицензирования с поддержкой:
- Trial периода (14 дней)
- Активации по ключу (HMAC-SHA256)
- Защиты от отката даты
- HWID-привязки

```python
from infrastructure.licensing import LicenseService

license_service = LicenseService()
status = license_service.check_license()
if status == 'trial_expired':
    # Показать диалог активации
    pass
```

## Миграция legacy кода

### Старая структура → Новая структура

| Старый модуль | Новый модуль | Примечание |
|--------------|--------------|------------|
| `database/db_manager.py` | `infrastructure/db/repositories.py` | Repository pattern |
| `utils/license_manager.py` | `infrastructure/licensing/license_service.py` | Facade pattern |
| `managers/settings.py` | `application/services/settings_service.py` | SRP |
| `services/service_layer.py` | `domain/services/` | Domain services |
| `events/domain_events.py` | `domain/events/events.py` | Domain events |

### Обратная совместимость

Legacy модули сохраняются для постепенной миграции:
- `utils/` - утилиты (постепенно переносятся в `shared/`)
- `managers/` - менеджеры (постепенно переносятся в `application/`)
- `database/` - БД (постепенно заменяется на репозитории)

## Best Practices Python 3.14

### 1. Type Hints
Все функции и методы имеют полную типизацию:
```python
from typing import List, Optional, Dict, Any, Protocol

def get_devices(filters: Optional[Dict[str, Any]] = None) -> List[Device]:
    ...
```

### 2. Dataclasses
Используются для всех сущностей:
```python
@dataclass(slots=True, frozen=False)
class Device:
    id: Optional[int] = None
    order_number: Optional[str] = None
    ...
```

### 3. Context Managers
Для управления ресурсами:
```python
@contextmanager
def get_session(self) -> Session:
    session = self._session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

### 4. Protocol (Structural Subtyping)
Для определения интерфейсов:
```python
class RepositoryProtocol(Protocol):
    def get(self, order_id: int) -> Optional[Device]: ...
    def save(self, device: Device) -> Device: ...
```

### 5. Logging вместо print
```python
logger = logging.getLogger(__name__)

logger.info(f"Создан заказ {order_number}")
logger.error(f"Ошибка создания заказа: {e}", exc_info=True)
```

## Тестирование

Новая архитектура позволяет легко писать тесты:

```python
import unittest
from unittest.mock import Mock

class TestOrderService(unittest.TestCase):
    def test_create_order(self):
        mock_repo = Mock(spec=DeviceRepository)
        mock_repo.get_next_order_number.return_value = 1
        
        service = OrderService(mock_repo)
        success, order, message = service.create_order(...)
        
        self.assertTrue(success)
        self.assertEqual(order.device.order_number, "000001")
```

## Производительность

Оптимизации в новой архитектуре:
1. **SQLite WAL mode** - параллельные чтение/запись
2. **Индексы** - на часто используемых полях
3. **Кеширование** - словарей и конфигурации
4. **Lazy loading** - ленивая загрузка тяжелых компонентов
5. **Connection pooling** - пул соединений с БД

## Дальнейшие шаги

1. ✅ Создать domain слой (entities, aggregates, events)
2. ✅ Создать infrastructure слой (repositories, licensing)
3. ⏳ Перенести GUI в interfaces/gui
4. ⏳ Создать REST API в interfaces/api
5. ⏳ Добавить полноценное тестирование
6. ⏳ Документировать все публичные API

## Заключение

Рефакторинг обеспечивает:
- **Масштабируемость** - легко добавлять новый функционал
- **Тестируемость** - изолированные компоненты
- **Поддерживаемость** - четкое разделение ответственности
- **Гибкость** - замена реализаций без изменения бизнес-логики

Версия: 16.0
Дата: 2024
