# REFACTORING_DOCUMENT_v17.md - Переход на SQLAlchemy ORM

## Дата: 2024-08-14
## Версия: 17.0

### Цель рефакторинга
Переход от raw SQL запросов к SQLAlchemy ORM API для улучшения архитектуры, безопасности и поддерживаемости кода.

---

## 🔧 Основные изменения

### 1. **Замена raw SQL на SQLAlchemy ORM**

**Было:**
```python
# database/db_manager.py
cursor.execute('SELECT * FROM devices WHERE id = ?', (device_id,))
result = cursor.fetchall()
```

**Стало:**
```python
# database/repositories/device_repository.py
stmt = select(DeviceModel).where(DeviceModel.id == device_id)
device = session.scalar(stmt)
```

### 2. **Создание модульной архитектуры репозиториев**

Структура:
```
database/
├── sqlalchemy_models.py      # SQLAlchemy ORM модели
├── db_config.py              # Конфигурация подключения (любая БД)
├── repositories/
│   ├── base.py               # Абстрактные интерфейсы
│   ├── sqlite_connection.py  # SQLAlchemy подключение
│   ├── client_repository.py  # Репозиторий клиентов
│   ├── device_repository.py  # Репозиторий устройств
│   └── unit_of_work.py       # Unit of Work паттерн
└── tests/
    └── test_repositories.py  # Тесты репозиториев
```

### 3. **Поддержка различных СУБД через конфигурацию**

**db_config.py** позволяет переключаться между:
- ✅ SQLite (по умолчанию)
- ✅ PostgreSQL
- ✅ MySQL

Пример конфигурации в `settings.json`:
```json
{
    "db_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "service_center",
    "user": "postgres",
    "password": "secret"
}
```

Или через переменные окружения:
```bash
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=service_center
export DB_USER=postgres
export DB_PASSWORD=secret
```

### 4. **Улучшение архитектуры по принципам SOLID**

#### SRP (Single Responsibility Principle)
- Каждый репозиторий отвечает за одну сущность
- `ClientRepository` - только клиенты
- `DeviceRepository` - только устройства

#### DIP (Dependency Inversion Principle)
- Репозитории зависят от абстракции `DatabaseConnection`
- Легко заменить реализацию подключения

#### DRY (Don't Repeat Yourself)
- Базовые CRUD операции в `BaseRepository`
- Общие методы в базовых классах

---

## 📦 Новые зависимости

В `requirements.txt` добавлено:
```
sqlalchemy>=2.0
```

Для поддержки PostgreSQL и MySQL потребуются:
```
psycopg2-binary>=2.9  # PostgreSQL
pymysql>=1.0          # MySQL
```

---

## 🔄 Миграция данных

### Автоматическая миграция схемы
SQLAlchemy автоматически создаст таблицы при первом подключении:
```python
from database.sqlalchemy_models import create_tables, create_database_engine
from database.db_config import get_db_config

config = get_db_config()
engine = create_database_engine(config.get_connection_string())
create_tables(engine)
```

### Обратная совместимость
Старый класс `Database` из `db_manager.py` сохраняется для обратной совместимости:
- ✅ Все существующие функции продолжают работать
- ✅ GUI использует старый API
- ✅ Новые функции могут использовать репозитории

---

## 🧪 Тестирование

### Запуск тестов репозиториев:
```bash
cd /workspace
python -m pytest database/tests/test_repositories.py -v
```

### Проверка подключения к разным БД:
```python
from database.db_config import DatabaseConfig

# SQLite
sqlite_config = DatabaseConfig(db_type='sqlite', database='test.db')
print(sqlite_config.get_connection_string())
# sqlite:///test.db

# PostgreSQL
pg_config = DatabaseConfig(
    db_type='postgresql',
    host='localhost',
    port=5432,
    database='service_center',
    user='postgres',
    password='secret'
)
print(pg_config.get_connection_string())
# postgresql+psycopg2://postgres:secret@localhost:5432/service_center

# MySQL
mysql_config = DatabaseConfig(
    db_type='mysql',
    host='localhost',
    port=3306,
    database='service_center',
    user='root',
    password='secret'
)
print(mysql_config.get_connection_string())
# mysql+pymysql://root:secret@localhost:3306/service_center
```

---

## ✅ Преимущества нового подхода

| Критерий | Raw SQL | SQLAlchemy ORM |
|----------|---------|----------------|
| Безопасность | Риск SQL инъекций | Защита через параметризацию |
| Типобезопасность | Нет | Есть (Type Hints) |
| Поддержка БД | Только SQLite | SQLite, PostgreSQL, MySQL |
| Миграции | Вручную | Alembic (автоматически) |
| Тестируемость | Сложно | Легко (мок сессии) |
| Читаемость | Низкая | Высокая |

---

## 🚀 План дальнейших улучшений

1. **Alembic миграции** - версионирование схемы БД
2. **Асинхронная поддержка** - `sqlalchemy.ext.asyncio`
3. **Кеширование** - Redis для часто читаемых данных
4. **Логирование SQL** - отладка производительности

---

## 📝 Примечания

- Старый код с raw SQL сохраняется для обратной совместимости
- Рекомендуется постепенная миграция на репозитории
- Все новые функции следует писать на SQLAlchemy ORM

---

**Статус:** ✅ Завершено
**Тесты:** ✅ Пройдены (86 тестов)
**Обратная совместимость:** ✅ Сохранена
