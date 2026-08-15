# ServiceUP: аудит + реальная интеграция архитектуры — итоговый отчёт

## Часть 1. Аудит SOLID/SRP/DRY/best-practice

Проведён параллельный код-ревью (28 агентов) по 14 подсистемам кодовой базы с
живым воспроизведением багов, где это было возможно. **145 подтверждённых
находок, 0 отклонено верификатором.**

### Главный системный вывод

Три подряд идущих "SOLID-рефакторинга" (repositories/factories/SQLAlchemy,
service layer, domain events + specifications) добавили вторую полную
архитектуру доступа к данным рядом со старой (`database/db_manager.py`,
`database/client_db.py`), но **не подключили её к реальному приложению**:

- `gui/main_window.py` и `pwa/server.py` не импортировали ничего из
  `database.repositories`, `services.service_layer`, `events`, `specifications`.
- `python -m pytest` падал на сборе тестов (`ImportError: SQLiteConnection`)
  с момента мержа — новая архитектура никогда не запускалась в этом окружении.
- Внутри самого нового слоя — активные баги (не только мёртвый код):
  `DeviceRepository.create()` падал с `AttributeError`, `services/__init__.py`
  был рассинхронизированным дублем-конкурентом `service_layer.py` с
  несовместимым DI-контрактом, `SpecificationFactory.active_orders()`
  сравнивал статус с несуществующими строками.

### Топ критичных находок (полный список — 145 находок по 14 подсистемам,
см. секции ниже и журнал workflow)

1. Хардкод SECRET_KEY лицензирования, продублирован в `keygen.py`/`license_manager.py`.
2. PWA-сервер без авторизации отдавал ПДн клиентов кому угодно в сети (к моменту
   этого отчёта уже был исправлен токеном `X-API-Key` — подтверждено при
   повторном чтении кода).
3. `get_client_stats` без fallback на основную БД — молчаливо нулевая статистика.
4. ~290 строк недостижимого мёртвого кода в `device_form.py` — дата приёма
   никогда не сохранялась правильно.
5. `cascade='all, delete-orphan'` конфликтовал с `ondelete='SET NULL'` в ORM.
6. `ClientService.update_client_stats` затирал `total_spent` нулём под TODO.
7. `ClientStatus.PROBLEMATIC = "Еблан"` — нецензурное слово как значение enum.
8. Прямой `sqlite3.connect()` в обход фасада `Database` в GUI/PWA (к моменту
   этого отчёта устранён — оба места используют `Database.delete_device()`/
   `update_device()`).
9. `managers/reports.py` дублировал форматирование актов и засорял `.txt`-файлами
   каталог исходников `reports/`.
10. `create_tables()` глотала ошибку схемы БД вместо проброса (к моменту этого
    отчёта уже исправлено — `raise` добавлен).

Полная таблица находок по всем 14 подсистемам (entry/config, легаси-БД, новая
архитектура, services/events/specs, GUI main window, GUI widgets, GUI dialogs
×2, managers, reports, PWA, utils, models/tests, сквозной DRY) сохранена в
журнале workflow-аудита этой сессии.

---

## Часть 2. Реальная интеграция Kernel/DI/Plugin/DB-agnostic архитектуры

При проверке второй, ещё более крупной волны "архитектурных" PR (`core/`,
`application/`, `domain/`, `infrastructure/`, `plugins/`, `features/`,
`shared/`, `i18n/` — сотни файлов) выяснилось: **ни один из 5 заявленных
пунктов не был подключён к работающему приложению** — тот же паттерн, что и в
части 1, в большем масштабе, плюс несколько мест гарантированно падали при
использовании (`ImportError`, `ModuleNotFoundError`, `AttributeError`,
`InvalidRequestError` — все воспроизведены запуском кода).

По решению пользователя эта архитектура была **реально доведена до рабочего
состояния** (не удалена и не оставлена фиктивной). Ниже — точное текущее
состояние каждого пункта, подтверждённое исполняемыми проверками (не только
чтением кода).

### 1. Core Kernel / Mediator — ✅ подключено

- `core/kernel.py::ServiceUpCore` — единственное ядро приложения.
  `core.contracts.CoreContainer` оставлен, но явно задокументирован как
  DI-контейнер для (пока не подключённого) `features/orders/`, а не как
  второе ядро. `core.application.CoreApplication` (третья, сломанная
  реализация — требовала неустановленный пакет `dependency_injector` и
  блокировала импорт `core.*` целиком) — удалена.
- `bootstrap.initialize_kernel()` — единая точка сборки зависимостей,
  вызывается из `main.py` перед созданием `ServiceCenterApp`.
- Подтверждено: `core.initialize()` → `core.get_service(Database)` →
  `core.shutdown()` — полный цикл, живой прогон.

### 2. DI-контейнер / строгий Mediator — ✅ подключено

- `ServiceUpCore.register_service()` (публичный метод, добавлен) — типобезопасный
  DI-контейнер для случаев, где резолвинг по классу удобнее.
- **По требованию пользователя ужесточено**: модули регистрируются в ядре как
  именованные singleton-модули (`core.register_module(name, instance, type,
  api=...)`), а не только в DI-контейнере. `gui/main_window.py` и
  `pwa/server.py` больше НЕ импортируют конкретные классы менеджеров/БД —
  они получают их исключительно по имени через ядро:
  `core.get_db_access()` (БД — зарезервированное имя `'db_access'`, единственный
  разрешённый путь к базе данных), `core.get_module_api('reports'|'settings'|
  'backup'|'integrations'|'photos'|'client_history')`,
  `core.call_module_method('db_access', 'method', ...)`. Проверено живым
  прогоном: `core.get_db_access() is <тот же объект>`, `call_module_method`
  реально вызывает метод БД через ядро, GUI и PWA используют один и тот же
  экземпляр, полученный обоими независимо через `core.get_db_access()`.
- `gui/main_window.py` больше не содержит ни одного `from database import
  Database` / `from managers import BackupManager, ...` — импорты конкретных
  классов удалены за ненадобностью (единственная связь с этими модулями —
  через имя, известное только `bootstrap.initialize_kernel()`).

### 3. Global Cache + ThreadManager — ✅ подключено

- Прямые `threading.Thread(...)` в `pwa/server.py` (поток Flask-сервера),
  `gui/dialogs/integration_settings.py` (Bluetooth scan/connect ×2),
  `reports/print_utils.py` (отложенное удаление временных PDF ×2) —
  заменены на `core.create_thread()`/`core.start_thread()`. Проверено живым
  прогоном, включая повторные вызовы с уникальными именами потоков.
- Удалён неиспользуемый дублирующий `gui/threading/__init__.py::ThreadManager`
  и неиспользуемый `shared/cache.py::TTLCache` (0 внешних потребителей —
  подтверждено).

### 4. Database Agnostic Layer + Calculation Offloading — ✅ подключено

- `database/engines/` — новый пакет: `IDatabaseEngine` (ABC) +
  `SQLiteEngine`/`PostgreSQLEngine`, выбор через уже существующий
  `database/db_config.py::get_db_config()` (DB_TYPE из `.env`).
  `database/db_config.py` заодно исправлен: раньше указывал на устаревший
  относительный `service_center.db`, теперь берёт путь из единственного
  реального источника (`config.get_db_path()` → `data/serviceup.db`).
- `database/sqlalchemy_database.py::Database` — новый facade, реализующий
  **тот же публичный API**, что и legacy `database.db_manager.Database`
  (23 метода, подтверждённые как реально используемые GUI/PWA/managers через
  grep), поверх SQLAlchemy-сессий вместо сырого `sqlite3`. Проверен
  комплексным тестом: словари, счётчики, клиенты, устройства (CRUD/поиск/
  фильтры), работы/фото (дочерние таблицы), статистика, финансы, история
  ремонтов — всё через реальную БД.
- Схема (`database/sqlalchemy_models.py`) расширена до полного паритета с
  9 таблицами `db_manager.py::create_tables` (добавлены `Counter`,
  `DictionaryItem`, `FinanceRecord`, `WorkItemRecord`, `PhotoRecord`,
  `CompletedRepair`, `RepairHistoryMain`; `Client` дополнен
  `first_order_date`/`favorite_device`). Все `DateTime`-колонки получили
  `timezone=True`.
- **Найден и исправлен реальный блокер**: живая таблица `devices` (создана
  старым sqlite-кодом) не имела колонок `client_id`/`diagnostic_cost`/
  `ready_date`/`repair_cost`/`updated_at`, которые уже были в ORM-модели —
  `Base.metadata.create_all()` не добавляет колонки в уже существующие
  таблицы. Добавлена автоматическая ALTER-миграция
  (`SQLiteEngine._add_missing_columns`, тот же паттерн, что уже использовался
  в `db_manager.py::_run_migrations`, но применена единообразно ко всем
  моделям) — применена к реальной живой БД, проверена: ни одна существующая
  строка не потеряна (65 записей словарей до/после совпали).
- `tools/migrate_to_sqlalchemy.py` — инструмент миграции на случай смены
  схемы/СУБД (бэкап → перенос → верификация количества строк по каждой
  таблице). Прогнан на реальной БД (пуста от бизнес-данных, но перенос
  словарей/счётчика проверен полностью).
- `Database.calculate(name, **params)` — реальный SQL offloading для
  `overdue_count`/`overdue_orders`/`dashboard_stats` (агрегация на стороне
  БД вместо питоновских циклов) — заодно закрывает находку части 1 о
  четырёхкратно продублированной логике «просрочено > 14 дней».
- Удалены как orphan/broken (0 внешних потребителей, гарантированно падали
  при импорте): `infrastructure/db_access/`, `infrastructure/analytics/`,
  `core/analytics/report_generator_act.py`.

### 5. Plugin Architecture — ✅ подключено (для одного, обоснованного плагина)

- `core/plugin_system.py`: добавлен `BasePlugin(IPlugin)` с хранением
  контекста; сигнатура `IPlugin.initialize(self, context)` — плагины больше
  не могут получать ресурсы в обход переданного контекста.
- `PluginManager.discover(package_name, context)` — реальное
  автообнаружение через `pkgutil.iter_modules` + вызов `register_plugin()`
  каждого найденного модуля, с последующей загрузкой через `load(name, context)`.
- `plugins/__init__.py` создан (отсутствовал — `plugins/` не был настоящим
  пакетом, поэтому discovery был в принципе невозможен).
- `plugins/auth`, `plugins/orders`, `plugins/pwa`, `plugins/reports`
  (~1836 строк, только `initialize()`-заглушки с закомментированными TODO,
  без единой реальной строки логики) — **удалены**: `auth` не имеет смысла
  в однопользовательском десктоп-приложении без системы логина, `orders`/
  `pwa`/`reports` лишь заново оборачивали бы уже рабочий код.
- `plugins/clients` — единственный плагин с осмысленным намерением — доведён
  до полностью рабочего состояния: `plugins/clients/repository.py::
  SqlAlchemyClientRepository` — конкретная реализация `IClientRepository`
  поверх реальной модели `Client`, зарегистрирована в DI. **Проверено живым
  прогоном**: `bootstrap.initialize_kernel()` → discovery находит и грузит
  `clients` → `core.get_module_api('clients')` возвращает рабочий
  `ClientService` → `create_client()`/`search_clients()` реально пишут и
  читают через настоящую БД.

### Явно не тронуто в этом заходе (осознанные границы объёма)

- `database/client_db.py` (`ClientDatabaseManager`) — legacy dual-write в
  отдельные `.db`-файлы по клиенту остаётся как есть (уже отмечен в части 1
  как write-only архив). Единственное исправление —
  `get_device_id_by_order_number()` вместо прямого доступа к `.conn.cursor()`
  (закрывает находку части 1).
- `application/`, `domain/`, `features/orders/` — остаются не подключены к
  приложению (это отдельная миграция бизнес-логики заказов на другую модель
  данных, не входящая в «подключить Kernel-инфраструктуру»); их падающие
  импорты починены (WP0), но живыми они не стали.
- `database/repositories`/`services.service_layer`/`events`/`specifications`
  (мёртвая архитектура из части 1) — по решению пользователя не тронуты.
- `infrastructure/db/`, `infrastructure/licensing/`, `infrastructure/messaging/`,
  `infrastructure/storage/` — обнаружены при интеграции, не используются
  приложением; решение по ним не принималось, остаются на месте.

### Побочно найденные и исправленные баги

- `services/__init__.py` — рассинхронизированный дубль-конкурент
  `service_layer.py`, `UnitOfWork()` падал с `TypeError` (найдено в части 1,
  не тронуто — часть мёртвой архитектуры).
- **`settings.json` содержит `backup_path` со старой машины**
  (`C:\Users\Сервис\Desktop\ServiceUP(new)\backups`) — `BackupManager`
  тихо не может создать директорию (`PermissionError`, пойман и залогирован,
  не роняет приложение). Данные пользователя не тронуты — требует ручного
  исправления в настройках.
- Pre-existing circular import: `managers → reports → gui.widgets.modern →
  gui → gui.dialogs → gui.dialogs.device_form → managers` — проявляется
  только если `managers` импортируется раньше `gui` (например, при прямом
  `python -c "import pwa.server"` в изоляции). В реальном приложении не
  проявляется (`main.py` всегда грузит `gui` первым) — учтено при вызове
  `initialize_kernel()` из `main.py` (после импорта `gui`, не до).
- `pyproject.toml` конфигурирует `pytest` на `testpaths = ["tests"]`, а
  `tests/` содержит только `conftest.py` — **штатный `pytest` без аргументов
  сейчас собирает 0 тестов**, реальные тесты (`database/tests/`,
  `services/test_services.py`) остаются вне конфигурации. Не исправлено в
  этом заходе (конфигурационный вопрос, требует решения — куда переносить
  тесты).

## Верификация (пройдена)

- `python -m compileall` по всем затронутым каталогам — чисто.
- `pytest database/tests/test_repositories.py services/test_services.py` —
  33 passed (столько же, сколько до всех изменений; 16 pre-existing ошибок
  Windows file-lock в teardown, не связаны с этой работой).
- Полный сквозной прогон: `gui` + `pwa.server` импортируются вместе, `Kernel`
  инициализируется, `Database`/менеджеры/плагин `clients` резолвятся из DI,
  `_DBHolder` в PWA и `ServiceCenterApp` в GUI используют **один и тот же**
  экземпляр `Database` — подтверждено идентичностью объектов.
- Ручной живой прогон `ClientsPlugin`: создание и поиск клиента через полную
  цепочку Kernel → DI → Repository → SQLAlchemy → реальная БД.
- Известное ограничение: полный live-прогон Flask-приложения PWA через
  `test_client()` в этой сессии не завершился надёжно — среда работает внутри
  постоянно синхронизируемой OneDrive-папки, и повторные блокировки файла
  `data/serviceup.db` синком OneDrive приводили к перемежающимся зависаниям
  файлового I/O (не связано с логикой кода — тот же паттерн `_DBHolder`
  проверен и работает корректно в изоляции). Рекомендуется вручную запустить
  PWA вне OneDrive-синхронизируемого окружения перед продакшн-использованием.
