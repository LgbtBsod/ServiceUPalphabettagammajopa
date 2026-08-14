# API Документация проекта

## Версия: 20.0.0

---

## 📐 Архитектура

Проект построен по принципу **Clean Architecture** с четким разделением на слои:

```
┌─────────────────────────────────────────┐
│         Presentation (GUI)              │
│    gui/main_window.py                   │
│    gui/dialogs/                         │
│    reports/report_editor.py             │
└─────────────────┬───────────────────────┘
                  │ (через Core Application)
┌─────────────────▼───────────────────────┐
│      Application Services               │
│    application/order_service.py         │
│    application/client_services.py       │
│    application/pdf_builder/             │
└─────────────────┬───────────────────────┘
                  │ (Domain Models)
┌─────────────────▼───────────────────────┐
│           Domain Layer                  │
│    domain/models/                       │
│    domain/constants.py                  │
│    domain/events.py                     │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│        Infrastructure                   │
│    infrastructure/db/                   │
│    infrastructure/repositories/         │
│    infrastructure/external_api/         │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│            Core                         │
│    core/application.py (DI Container)   │
│    core/config.py                       │
│    core/events.py (EventBus)            │
└─────────────────────────────────────────┘
```

---

## 🔧 Core Module

### `core.application.CoreApplication`

Центральный класс приложения, реализующий DI контейнер.

#### Методы:

```python
def get_service(service_class: Type[T]) -> T:
    """Получение сервиса через DI контейнер."""
    
def register_service(service_class: Type[T], instance: T) -> None:
    """Регистрация сервиса в контейнере."""
    
def get_event_bus() -> EventBus:
    """Получение шины событий для слабой связанности."""
```

#### Пример использования:

```python
from core.application import get_app

app = get_app()
order_service = app.get_service(OrderService)
client_service = app.get_service(ClientAppService)
```

---

## 📊 Application Services

### `application.order_service.OrderService`

Сервис управления заказами.

#### Методы:

```python
def create_order(client_id: int, items: List[Dict]) -> Order:
    """Создание нового заказа."""
    
def get_order(order_id: int) -> Optional[Order]:
    """Получение заказа по ID."""
    
def update_order_status(order_id: int, status: str) -> bool:
    """Обновление статуса заказа."""
    
def delete_order(order_id: int) -> bool:
    """Удаление заказа."""
```

### `application.client_services.ClientAppService`

Сервис управления клиентами.

#### Методы:

```python
def create_client(name: str, phone: str, email: Optional[str] = None) -> Client:
    """Создание нового клиента."""
    
def get_client(client_id: int) -> Optional[Client]:
    """Получение клиента по ID."""
    
def search_clients(query: str) -> List[Client]:
    """Поиск клиентов по названию/телефону."""
    
def update_client(client_id: int, **kwargs) -> bool:
    """Обновление данных клиента."""
```

### `application.pdf_builder.pdf_builder.PDFBuilder`

Конструктор PDF отчетов с поддержкой Drag-and-Drop.

#### Методы:

```python
def set_template(template_data: Dict) -> PDFBuilder:
    """Установка шаблона отчета."""
    
def reorder_fields(section_index: int, field_order: List[int]) -> PDFBuilder:
    """Переупорядочивание полей (после DnD)."""
    
def add_field(section_index: int, field: Dict) -> PDFBuilder:
    """Добавление поля в секцию."""
    
def remove_field(section_index: int, field_index: int) -> PDFBuilder:
    """Удаление поля из секции."""
    
def set_format(format: str) -> PDFBuilder:
    """Установка формата документа (A4/A5)."""
    
def build() -> bytes:
    """Генерация PDF и возврат байтов."""
    
def save(filepath: str) -> None:
    """Сохранение PDF в файл."""
```

#### Пример использования:

```python
from application.pdf_builder import PDFBuilder

builder = PDFBuilder()
pdf_bytes = (builder
    .set_template(template_data)
    .reorder_fields(0, [2, 0, 1, 3])  # Порядок после DnD
    .set_format("A4")
    .build())
```

---

## 🎨 GUI Module

### `gui.main_window.MainWindow`

Главное окно приложения.

#### Получение данных через ядро:

```python
from core.application import get_app
from application.order_service import OrderService

class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.app = get_app()
        self.order_service = self.app.get_service(OrderService)
        
    def load_orders(self):
        orders = self.order_service.get_all_orders()
        # Отображение в UI
```

### `reports.report_editor.ReportEditor`

Редактор актов с Drag-and-Drop поддержкой.

#### Методы DnD:

```python
def _create_field_item(field: Dict, index: int) -> tk.Frame:
    """Создание элемента списка полей."""
    
def _on_drag_start(event: tk.Event) -> None:
    """Начало перетаскивания."""
    
def _on_drag_motion(event: tk.Event) -> None:
    """Движение элемента с авто-заменой позиций."""
    
def _on_drag_drop(event: tk.Event) -> None:
    """Завершение перетаскивания."""
    
def _get_field_order() -> List[Dict]:
    """Получение текущего порядка полей из UI."""
    
def sync_template_from_ui() -> Dict:
    """Синхронизация данных шаблона с UI."""
```

---

## 📁 Infrastructure Module

### `infrastructure.db.db_connection.DatabaseConnection`

Класс подключения к базе данных.

#### Методы:

```python
def get_connection() -> sqlite3.Connection:
    """Получение соединения с БД."""
    
def execute_query(query: str, params: Tuple = ()) -> List[Dict]:
    """Выполнение SELECT запроса."""
    
def execute_command(query: str, params: Tuple = ()) -> int:
    """Выполнение INSERT/UPDATE/DELETE."""
```

### `infrastructure.repositories.order_repository.OrderRepository`

Репозиторий для работы с заказами.

#### Методы:

```python
def get_by_id(order_id: int) -> Optional[Order]:
    """Получение заказа по ID."""
    
def get_all() -> List[Order]:
    """Получение всех заказов."""
    
def save(order: Order) -> int:
    """Сохранение заказа, возврат ID."""
    
def delete(order_id: int) -> bool:
    """Удаление заказа."""
```

---

## 📋 Reports Module

### `reports.act_pdf_generator.ActPDFGenerator`

Генератор PDF актов.

#### Методы:

```python
def generate_act(template_data: Dict, output_path: str) -> str:
    """Генерация акта и сохранение в файл."""
    
def preview_act(template_data: Dict) -> Image.Image:
    """Предпросмотр акта как изображение."""
    
def add_logo(image_path: str, position: Tuple[int, int]) -> ActPDFGenerator:
    """Добавление логотипа."""
    
def add_qr_code(data: str, position: Tuple[int, int]) -> ActPDFGenerator:
    """Добавление QR-кода."""
```

---

## 🔌 Events System

### `core.events.EventBus`

Шина событий для слабой связанности компонентов.

#### Методы:

```python
def subscribe(event_type: str, handler: Callable) -> None:
    """Подписка на событие."""
    
def unsubscribe(event_type: str, handler: Callable) -> None:
    """Отписка от события."""
    
def publish(event_type: str, data: Any = None) -> None:
    """Публикация события."""
```

#### Пример использования:

```python
from core.application import get_app

event_bus = get_app().get_event_bus()

# Подписка
event_bus.subscribe("order.created", on_order_created)
event_bus.subscribe("order.updated", on_order_updated)

# Публикация
event_bus.publish("order.created", {"order_id": 123})
```

---

## 🧪 Testing

### Запуск тестов:

```bash
# Все тесты
python -m unittest discover tests/ -v

# Конкретный модуль
python -m unittest tests.test_drag_drop -v
python -m unittest tests.test_pdf_builder -v
python -m unittest tests.test_pathlib_utils -v
```

### Структура тестов:

- `test_pathlib_utils.py` — тесты методов pathlib
- `test_drag_drop.py` — тесты логики Drag-and-Drop
- `test_pdf_builder.py` — тесты PDF конструктора
- `test_advanced.py` — расширенные интеграционные тесты
- `test_basic.py` — базовые unit-тесты
- `test_pydantic_models.py` — тесты Pydantic моделей

---

## 📦 Зависимости

Основные библиотеки:

| Библиотека | Версия | Назначение |
|------------|--------|------------|
| customtkinter | >=5.2.0 | GUI фреймворк |
| dependency-injector | >=4.41.0 | DI контейнер |
| pydantic | >=2.0.0 | Валидация данных |
| pydantic-settings | >=2.0.0 | Управление настройками |
| qrcode | >=7.4.0 | Генерация QR-кодов |
| pypdfium2 | >=4.30.0 | Рендеринг PDF |
| reportlab | >=4.0.0 | Генерация PDF |
| Pillow | >=10.0.0 | Работа с изображениями |

---

## 🚀 Быстрый старт

```python
from core.application import get_app
from application.order_service import OrderService
from application.client_services import ClientAppService

# Инициализация приложения
app = get_app()

# Получение сервисов
order_service = app.get_service(OrderService)
client_service = app.get_service(ClientAppService)

# Создание клиента
client = client_service.create_client(
    name="ООО Ромашка",
    phone="+79991234567",
    email="info@romashka.ru"
)

# Создание заказа
order = order_service.create_order(
    client_id=client.id,
    items=[
        {"name": "Услуга 1", "price": 1000, "quantity": 2},
        {"name": "Услуга 2", "price": 500, "quantity": 1}
    ]
)

print(f"Заказ #{order.id} создан!")
```

---

## 📝 Changelog

### v20.0.0
- ✅ Полная миграция на pathlib
- ✅ Выделение GUI в отдельный модуль
- ✅ Drag-and-Drop редактор актов
- ✅ Unit-тесты для всех новых функций
- ✅ Оптимизация PDF рендеринга (800мс → 80мс)
- ✅ Централизованная обработка исключений
- ✅ Обновленная документация API

### v19.0.0
- Интеграция pydantic-settings
- Улучшенная валидация данных

### v18.0.0
- Добавлен PDF Builder с кэшированием
- WebSocket для мобильного подключения

---

## 📞 Поддержка

Вопросы и предложения направляйте в репозиторий проекта.
