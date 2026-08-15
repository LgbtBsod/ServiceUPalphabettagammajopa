# Архитектурные Улучшения v23.0

## 📦 Выделение Сервисных Модулей

### 1. Модуль Уведомлений (`services/notifications/`)

**Цель:** Централизация всех каналов коммуникации с клиентами.

**Структура:**
```
services/notifications/
├── __init__.py              # Публичный API модуля
├── notification_service.py  # Основной сервис (Strategy Pattern)
├── telegram_adapter.py      # Telegram Bot API
├── whatsapp_adapter.py      # WhatsApp Business API
├── vk_adapter.py            # VKontakte API
├── email_adapter.py         # SMTP Email
└── bluetooth_adapter.py     # Bluetooth Call (PC-to-Phone)
```

**Паттерны:**
- **Strategy Pattern**: Выбор канала уведомления через адаптеры
- **Adapter Pattern**: Унификация интерфейсов разных API
- **Protocol**: Типизированные интерфейсы для адаптеров

**Пример использования:**
```python
from services.notifications import NotificationService, NotificationChannel

service = NotificationService()
service.register_adapter(NotificationChannel.TELEGRAM, TelegramAdapter(token))
service.register_adapter(NotificationChannel.EMAIL, EmailAdapter(smtp_config))

await service.send(
    NotificationMessage(
        channel=NotificationChannel.TELEGRAM,
        recipient="123456789",
        body="Ваш заказ готов!",
    )
)
```

---

### 2. Модуль Аналитики (`services/analytics/`)

**Цель:** Бизнес-аналитика, метрики и генерация отчетов.

**Структура:**
```
services/analytics/
├── __init__.py           # Публичный API модуля
├── analytics_service.py  # Основной сервис аналитики
├── dashboard_metrics.py  # DTO для метрик дашборда
└── report_generator.py   # Генератор отчетов (Strategy Pattern)
```

**Паттерны:**
- **Repository Pattern**: Абстракция доступа к данным
- **Strategy Pattern**: Экспорт в разные форматы (PDF, Excel, CSV)
- **DTO**: Типизированные объекты для передачи данных

**Функционал:**
- DashboardMetrics: агрегированные метрики за период
- ReportGenerator: экспорт в PDF/Excel/CSV с fallback
- AnalyticsService: тренды, клиентская аналитика, периодические отчеты

**Пример использования:**
```python
from services.analytics import AnalyticsService, DashboardMetrics

service = AnalyticsService(repository)
metrics = service.get_dashboard_metrics()
report_path = service.generate_period_report(
    date_from=date(2024, 1, 1),
    date_to=date(2024, 1, 31),
    report_type="excel",
)
```

---

## 🏗️ Архитектурные Принципы

### Clean Architecture Layers

```
┌─────────────────────────────────────┐
│         Presentation Layer          │
│  (GUI, Web API, Mobile PWA)         │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│      Application Services Layer     │
│  /workspace/services/               │
│  - notifications/                   │
│  - analytics/                       │
│  - order_services.py                │
│  - client_services.py               │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│         Domain Layer                │
│  (Entities, Value Objects, Events)  │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│      Infrastructure Layer           │
│  (Repositories, DB, External APIs)  │
└─────────────────────────────────────┘
```

### DIP (Dependency Inversion Principle)

Все сервисы зависят от абстракций (Protocol), а не от конкретных реализаций:

```python
class AnalyticsRepository(Protocol):
    def get_orders_by_date_range(...) -> List[Dict]: ...
    def get_dashboard_stats(...) -> Dict: ...

class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository):
        self._repository = repository  # Зависимость от абстракции
```

### SRP (Single Responsibility Principle)

Каждый модуль отвечает за одну задачу:
- `notifications` → коммуникация с клиентами
- `analytics` → бизнес-аналитика и отчеты
- `pdf_builder` → генерация PDF документов
- `order_services` → логика заказов
- `client_services` → логика клиентов

---

## 📊 Сравнение До/После

| Аспект | До | После |
|--------|----|-------|
| **Модульность** | Монолитный `application/` | Разделен на `services/notifications`, `services/analytics` |
| **Связность** | Прямые импорты между модулями | Через абстракции (Protocol) |
| **Тестируемость** | Сложное мокирование | Легкое тестирование через Protocol |
| **Расширяемость** | Изменение кода ядра | Добавление новых адаптеров без изменений |
| **Повторное использование** | Дублирование кода | Общие стратегии и утилиты |

---

## 🚀 Следующие Шаги

1. **Переместить Keygen** в отдельную папку `/tools/keygen/`
2. **Вынести Exception Handler** в модуль `core/exceptions.py`
3. **Обновить GUI** для работы через новые сервисы
4. **Добавить Unit-тесты** для `notifications` и `analytics`
5. **Документировать API** каждого сервиса

---

## ✅ Чеклист Рефакторинга

- [x] Создан модуль `services/notifications/` с 5 адаптерами
- [x] Создан модуль `services/analytics/` с метриками и генератором отчетов
- [x] Применены паттерны: Strategy, Adapter, Repository, Protocol
- [x] Все импорты работают корректно
- [ ] Переместить `keygen.py` в `/tools/`
- [ ] Вынести обработку исключений в `core/exceptions.py`
- [ ] Обновить документацию API
- [ ] Добавить coverage тесты

