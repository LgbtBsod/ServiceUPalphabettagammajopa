# Улучшение архитектуры приложения v19: Domain Events и Specification Pattern

## Обзор изменений

Данное улучшение внедряет два важных паттерна проектирования:
1. **Domain Events** - для событийно-ориентированной архитектуры
2. **Specification Pattern** - для инкапсуляции сложных бизнес-правил

Оба паттерна соответствуют принципам SOLID, DRY и Clean Code.

## Реализованные принципы

### 1. SOLID

#### Single Responsibility Principle (SRP)
- Каждая спецификация отвечает за одно бизнес-правило
- Обработчики событий выполняют одну конкретную задачу
- EventBus управляет только публикацией/подпиской событий

#### Open/Closed Principle (OCP)
- Легко добавлять новые типы событий без изменения существующего кода
- Спецификации можно комбинировать без модификации
- Новые обработчики событий добавляются через наследование

#### Dependency Inversion Principle (DIP)
- Обработчики событий зависят от абстракции `DomainEvent`
- Спецификации работают с любыми объектами через generics

#### Interface Segregation Principle (ISP)
- Минимальные интерфейсы для обработчиков событий
- Спецификации имеют один метод `is_satisfied_by()`

### 2. DRY (Don't Repeat Yourself)
- Базовые классы спецификаций переиспользуются
- Фабрики централизуют создание объектов
- Общие операции комбинирования вынесены в базовый класс

### 3. Domain Events Pattern
- Слабая связанность между компонентами
- Асинхронная обработка событий
- Аудит и логирование через события
- Расширяемость без изменения ядра

### 4. Specification Pattern
- Инкапсуляция бизнес-правил
- Комбинируемость правил через логические операторы
- Переиспользование спецификаций
- Читаемый код фильтрации

## Новые файлы

### `/workspace/events/domain_events.py`

```python
class EventType(Enum):
    """Типы событий домена."""
    ORDER_CREATED = "order.created"
    ORDER_STATUS_CHANGED = "order.status_changed"
    CLIENT_CREATED = "client.created"
    # ... и другие

class DomainEvent:
    """Базовый класс события домена."""
    event_type: EventType
    aggregate_id: Optional[int]
    timestamp: datetime
    payload: Dict[str, Any]
    metadata: Dict[str, Any]

class EventHandler(ABC):
    """Абстрактный обработчик событий."""
    @abstractmethod
    def handle(event: DomainEvent) -> None: ...
    
    @property
    @abstractmethod
    def subscribed_events() -> List[EventType]: ...

class EventBus:
    """Шина событий (Singleton)."""
    def subscribe(handler: EventHandler) -> None
    def unsubscribe(handler: EventHandler) -> None
    def publish(event: DomainEvent) -> None
    def get_history(limit: int = 100) -> List[DomainEvent]

@event_handler([EventType.ORDER_CREATED])
class OrderNotificationHandler(EventHandler):
    """Пример обработчика."""
```

### `/workspace/specifications/order_specifications.py`

```python
class Specification(ABC, Generic[T]):
    """Базовый класс спецификации."""
    @abstractmethod
    def is_satisfied_by(candidate: T) -> bool: ...
    
    def and_(other: Specification) -> Specification
    def or_(other: Specification) -> Specification
    def not_() -> Specification

class SpecificationFactory:
    """Фабрика спецификаций заказов."""
    @staticmethod
    def by_status(status: str) -> Specification
    @staticmethod
    def overdue(days: int = 14) -> Specification
    @staticmethod
    def needs_attention() -> Specification
    @staticmethod
    def active_orders() -> Specification

# Пример использования:
spec = (
    SpecificationFactory.by_priority('Срочный')
    .and_(SpecificationFactory.overdue(5))
)
filtered = [o for o in orders if spec.is_satisfied_by(o)]
```

## Примеры использования

### Domain Events

```python
from events import event_bus, EventType, create_event

# Создание и публикация события
event = create_event(
    event_type=EventType.ORDER_CREATED,
    aggregate_id=order_id,
    payload={'order_number': '00001', 'total': 5000}
)
event_bus.publish(event)

# Подписка на события
@event_handler([EventType.ORDER_STATUS_CHANGED])
class MyStatusHandler(EventHandler):
    def handle(self, event: DomainEvent) -> None:
        print(f"Status changed: {event.payload}")

# Автоматическая подписка при создании экземпляра
handler = MyStatusHandler()
```

### Specification Pattern

```python
from specifications import SpecificationFactory, filter_orders

# Простая спецификация
overdue_spec = SpecificationFactory.overdue(14)
overdue_orders = filter_orders(orders, overdue_spec)

# Комбинированная спецификация
attention_spec = (
    SpecificationFactory.by_priority('Срочный')
    .and_(SpecificationFactory.overdue(3))
    .or_(SpecificationFactory.ready_for_pickup())
)
needs_attention = filter_orders(orders, attention_spec)

# Кастомная спецификация
custom_spec = SpecificationFactory.custom(
    lambda o: o.total_cost > 10000 and o.status != 'Выдан'
)
```

## Преимущества новой архитектуры

### Domain Events
1. **Слабая связанность**: Компоненты не знают друг о друге
2. **Расширяемость**: Новые обработчики добавляются без изменения ядра
3. **Аудит**: История всех событий сохраняется
4. **Гибкость**: Возможность асинхронной обработки

### Specification Pattern
1. **Читаемость**: Бизнес-правила выражены явно
2. **Тестируемость**: Каждую спецификацию можно тестировать отдельно
3. **Переиспользование**: Спецификации комбинируются и переиспользуются
4. **Поддерживаемость**: Изменение правил локализовано

## Интеграция с существующим кодом

### Интеграция Domain Events в Service Layer

```python
# services/service_layer.py
from events import event_bus, EventType, create_event

class OrderService(BaseService[Order]):
    def create_order(self, order_data: Dict[str, Any]) -> Order:
        with self._get_uow() as uow:
            # ... создание заказа ...
            
            # Публикация события
            event = create_event(
                event_type=EventType.ORDER_CREATED,
                aggregate_id=order.id,
                payload=order.model_dump()
            )
            event_bus.publish(event)
            
            return order
    
    def update_order_status(self, order_id: int, status: OrderStatus) -> Optional[Order]:
        with self._get_uow() as uow:
            # ... обновление статуса ...
            
            # Публикация события
            event = create_event(
                event_type=EventType.ORDER_STATUS_CHANGED,
                aggregate_id=order_id,
                payload={'old_status': old_status, 'new_status': status.value}
            )
            event_bus.publish(event)
```

### Интеграция Specification в Repository

```python
# database/repositories/device_repository.py
from specifications import Specification, OrderCandidate

class DeviceRepository(BaseRepository[Device]):
    def find_by_specification(self, spec: Specification) -> List[Device]:
        """Поиск устройств по спецификации."""
        all_devices = self.get_all()
        
        # Конвертация в кандидаты для проверки
        candidates = [self._to_candidate(d) for d in all_devices]
        filtered = [c for c in candidates if spec.is_satisfied_by(c)]
        
        return [self._from_candidate(c) for c in filtered]
    
    def _to_candidate(self, device: Device) -> OrderCandidate:
        """Конвертация устройства в кандидата."""
        return OrderCandidate(
            id=device.id,
            status=device.status,
            priority=device.priority,
            receipt_date=device.receipt_date,
            ready_date=device.ready_date,
            total_cost=device.total_cost,
            days_in_service=get_days_since_receipt(device.receipt_date)
        )
```

## Тестирование

```bash
# Проверка модуля событий
python -c "from events import event_bus, EventType; print('✅ OK')"

# Проверка модуля спецификаций
python -c "from specifications import SpecificationFactory; print('✅ OK')"

# Запуск демонстрации спецификаций
python specifications/order_specifications.py
```

## Рекомендации по дальнейшему развитию

1. **CQRS + Event Sourcing**: Использовать события для восстановления состояния
2. **Saga Pattern**: Координация распределенных транзакций через события
3. **Outbox Pattern**: Гарантированная доставка событий
4. **GraphQL Integration**: Использование спецификаций для фильтрации GraphQL запросов
5. **Policy Pattern**: Развитие спецификаций в полноценную систему правил

## Обратная совместимость

Все изменения обратно совместимы:
- Существующий код продолжает работать без изменений
- Новые паттерны используются опционально
- API сервисов и репозиториев сохранены

## Миграция

Для постепенного внедрения:

1. Начать с добавления событий для ключевых операций
2. Постепенно заменять сложные условия на спецификации
3. Добавить обработчики для логирования и аудита
4. Расширять набор событий и спецификаций по мере необходимости

## Заключение

Внедрение Domain Events и Specification Pattern значительно улучшает архитектуру приложения:
- Повышает гибкость и расширяемость
- Упрощает тестирование и поддержку
- Делает код более читаемым и понятным
- Соответствует лучшим практикам разработки
