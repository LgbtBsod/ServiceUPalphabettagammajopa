# Аудит кода ServiceUP v15.0 — v20

## Роль: Chief Core Auditor Engineer

Метод: параллельный код-ревью по 14 подсистемам (28 агентов: находка → скептическая верификация по реальному коду, часть находок подтверждена живым воспроизведением багов) + ручная проверка через `pytest`/`grep`. **145 подтверждённых находок, 0 отклонено верификатором.**

---

## 0. Главный вывод: в проекте два параллельных, несовместимых слоя доступа к данным

Предыдущие 3 смёрженных PR («SOLID architecture», «Factory Pattern + Service Layer», «SQLAlchemy multi-DB») добавили **вторую полную архитектуру** — `database/repositories/`, `database/factories.py`, `database/sqlalchemy_models.py`, `services/`, `events/`, `specifications/` — рядом со старой (`database/db_manager.py`, `database/client_db.py`).

Проверено фактами, а не предположением:

- `python -m pytest` **падает на этапе сбора тестов** (`database/tests/test_repositories.py`, `services/test_services.py`) — `ImportError: cannot import name 'SQLiteConnection'`. Класс переименован в `SQLAlchemyConnection` при миграции на SQLAlchemy, файл остался называться `sqlite_connection.py`, тесты не обновлены. Новая архитектура **не компилируется и никогда не запускалась после мержа**.
- `grep` по `gui/` и `pwa/` — **ноль** импортов из `database.repositories`, `services.service_layer`, `events`, `specifications`, `database.factories`. Реальное приложение как использовало, так и использует старый God Object `Database` (`database/db_manager.py`, 1289 строк, 60+ прямых вызовов `self.db.*` из `gui/main_window.py`).
- Внутри самого нового слоя — активные баги, а не просто мёртвый код: `DeviceRepository.create()` падает с `AttributeError` при вызове без `client_id` (воспроизведено), не передаёт `client_id` в модель вообще, `services/__init__.py` — рассинхронизированный дубликат-конкурент `services/service_layer.py` с несовместимым конструктором (`UnitOfWork()` без аргументов падает — воспроизведено), `SpecificationFactory.active_orders()` сравнивает статус с несуществующими строками и никогда не фильтрует.
- `.md`-документы (`ARCHITECTURE_IMPROVEMENTS_v18/19.md`) описывают эту архитектуру как реализованную и «совместимую с существующим кодом» — по факту она не подключена нигде и не работала ни разу после мержа.

**Это не техдолг одной функции — это архитектурное решение уровня «выяви и закрой», влияющее на большинство остальных находок ниже (VII, DIP-нарушения БД).** Решение по этому пункту нужно принять отдельно (см. вопросы в конце).

---

## 1. Сводка по важности

| Severity | Кол-во |
|---|---|
| High | 47 |
| Medium | 63 |
| Low | 35 |
| **Итого** | **145** |

## 2. Топ-10 критичных находок (помимо п.0)

1. **`utils/license_manager.py:29` + `keygen.py:20`** — секретный HMAC-ключ лицензирования захардкожен в клиентском коде и побайтово продублирован в двух файлах. Любой пользователь, распаковав .exe, может сгенерировать валидный ключ активации под любой HWID — защита лицензии полностью обходится.
2. **`pwa/server.py:620`** — HTTP-сервер слушает `0.0.0.0:5000` без единой проверки авторизации на всех `/api/*` маршрутах (заказы + ПДн клиентов — имя, телефон, фото). Любое устройство в сети читает/меняет все данные без пароля.
3. **`database/client_db.py:406`** (`get_client_stats`) — в отличие от соседнего `get_client_history`, не имеет fallback на основную БД: для клиентов без legacy `.db`-файла молча возвращает нулевую статистику.
4. **`gui/dialogs/device_form.py:581-871`** — ~290 строк недостижимого мёртвого кода внутри `_do_save` (после `return` на обоих путях try/except), из-за чего `self.receipt_datetime_label` никогда не создаётся и `save()` всегда использует `datetime.now()` вместо реальной даты приёма.
5. **`database/sqlalchemy_models.py:62,113`** — `cascade='all, delete-orphan'` на уровне ORM конфликтует с `ondelete='SET NULL'` на уровне БД: удаление клиента реально каскадно удаляет устройства (воспроизведено), а не отвязывает их, как предполагает докстринг.
6. **`services/service_layer.py:383`** (и дубликат в `services/__init__.py`) — `ClientService.update_client_stats` под TODO безусловно пишет `total_spent = 0.0`, затирая накопленную статистику клиента при каждом вызове.
7. **`models/pydantic_models.py:58`** — `ClientStatus.PROBLEMATIC = "Еблан"` — нецензурное оскорбление как значение бизнес-enum, попадает в любую форму/экспорт/печатный документ, где отображается статус клиента.
8. **`gui/main_window.py:1015`** и **`pwa/server.py:525`** — единственные места в проекте, где к БД обращаются в обход фасада `Database`: открывают собственное `sqlite3`-соединение и делают сырой SQL прямо из GUI/HTTP-хендлера, потому что у `Database` нет метода `delete_device`/`update_device_photos`.
9. **`managers/reports.py`** — дублирует форматирование актов, уже реализованное в `reports/report_renderer.py`, и на каждый предпросмотр пишет мусорный `.txt` прямо в каталог **исходного кода** `reports/` (совпадает с `REPORTS_DIR`), без очистки.
10. **`database/db_manager.py:242`** (`create_tables`) — ошибка создания схемы БД перехватывается и просто печатается, не пробрасывается дальше — приложение продолжает работать с потенциально неполной схемой и падает позже в случайном месте с непонятной ошибкой.

## 3. Находки по подсистемам

### 3.1 Точка входа / конфиг (`main.py`, `bootstrap.py`, `config.py`, `keygen.py`, `_scan.py`) — 8 находок
| # | Файл:строка | Принцип | Sev | Суть |
|---|---|---|---|---|
|1| keygen.py:20 | DRY | High | SECRET_KEY и алгоритм генерации ключа дублированы с license_manager.py |
|2| utils/license_manager.py:29 | best-practice | High | Хардкод секрета лицензирования в клиентском коде |
|3| bootstrap.py:24 | DRY | Med | check_dependencies проверяет 2 из 12 пакетов requirements.txt (включая sqlalchemy) |
|4| main.py:15 | SRP | Med | main() смешивает зависимости/лицензию/GUI/обработку ошибок |
|5| main.py:45 | clean-code | Low | Статусы лицензии как строковые литералы, magic number 3 |
|6| main.py:33 | best-practice | Low | print()/traceback вместо logging в точке входа |
|7| _scan.py:1 | clean-code | Low | dev-скрипт с side-effect на уровне модуля без `__main__`-guard |
|8| config.py:16 | DRY | Med | Путь к БД задан двумя несвязанными способами (config.DB_PATH vs db_config.py) |

### 3.2 Легаси-слой БД (`database/db_manager.py`, `client_db.py`, `db_config.py`, `models.py`) — 12 находок
| # | Файл:строка | Принцип | Sev | Суть |
|---|---|---|---|---|
|1| db_manager.py:28 | SRP | High | Database — God Object, 8+ обязанностей в одном классе (~1262 строк) |
|2| client_db.py:126 | SRP | High | add_repair_to_client_history — метод на 217 строк, 5+ обязанностей |
|3| client_db.py:16 | DRY | High | Двойная схема хранения истории клиента (main_db + legacy .db), агрегаты считаются по-разному |
|4| client_db.py:406 | correctness | High | get_client_stats без fallback на main_db (см. п.2 сводки) |
|5| client_db.py:147 | DIP | Med | Прямой доступ к `self._main_db.conn.cursor()` в обход фасада |
|6| database/models.py:11 | DRY | Med | `_safe_price_to_float` дублирует `utils/formatters.parse_price_to_float` другим алгоритмом |
|7| db_manager.py:243 | clean-code | Med | print() вместо logging по всему файлу |
|8| db_manager.py:242 | correctness | Med | create_tables глотает sqlite3.Error, не пробрасывает |
|9| db_manager.py:518 | DRY | Med | Блок dual-write price-колонок продублирован в add_device/update_device |
|10| db_manager.py:94 | clean-code | Med | Статусы как строковые литералы в 10+ местах вместо констант |
|11| db_config.py:4 | reinventing-wheel | Med | Докстринг обещает multi-DB конфиг, легаси Database о нём не знает |
|12| db_manager.py:1153 | clean-code | Low | Повторные локальные import модулей, уже импортированных в шапке |

### 3.3 «Новая» SOLID-архитектура (`repositories/`, `factories.py`, `sqlalchemy_models.py`) — 11 находок
| # | Файл:строка | Принцип | Sev | Суть |
|---|---|---|---|---|
|1| device_repository.py:61 | LSP | High | Конвертация ORM→legacy-dataclass теряет client_name/phone/status (не денормализовано) |
|2| device_repository.py:141 | clean-code | High | Обращение к несуществующему `DeviceModel.phone` — падает с AttributeError (воспроизведено) |
|3| sqlalchemy_models.py:62 | best-practice | High | cascade='all,delete-orphan' vs ondelete='SET NULL' — конфликт, реально каскадит (воспроизведено) |
|4| client_repository.py:29 | DIP | Med | Конструкторы типизированы на конкретный SQLAlchemyConnection, а не на абстракцию |
|5| repositories/base.py:119 | ISP | Med | Абстракция DatabaseConnection не описывает get_session(), которым реально пользуются репозитории |
|6| client_repository.py:60 | DRY | Med | Построение фильтров продублировано 4 раза (2 репозитория × get_all/count) |
|7| device_repository.py:61 | DRY | Med | Конвертация ORM→domain продублирована 6 раз в одном файле |
|8| sqlite_connection.py:71 | clean-code | Low | disconnect() глотает исключение без логирования |
|9| repositories/base.py:18 | LSP | Med | BaseRepository[T] возвращает разные типы результата у разных репозиториев |
|10| sqlalchemy_models.py:53 | DRY | Low | Дефолтные статусы задублированы в ORM-модели и в репозиториях |
|11| factories.py:111 | best-practice | Low | DI через мутируемый глобальный синглтон без потокобезопасности |
|12| database/tests/test_repositories.py:16 | best-practice | High | ImportError несуществующего SQLiteConnection, тесты не собираются вообще |

### 3.4 Services / Events / Specifications — 10 находок
| # | Файл:строка | Принцип | Sev | Суть |
|---|---|---|---|---|
|1| services/__init__.py:27 | DRY | High | Полный дубликат-конкурент service_layer.py с несовместимым, ломающимся DI-контрактом (воспроизведено: `TypeError`) |
|2| services/test_services.py:19 | best-practice | Med | Тесты бьют по неверному модулю + ImportError SQLiteConnection |
|3| order_specifications.py:226 | DRY | High | active_orders() сравнивает статус с несуществующими строками — фильтр никогда не срабатывает |
|4| order_specifications.py:135 | DRY | Med | Порог «просрочено 14 дней» задублирован в 4+ независимых местах |
|5| service_layer.py:228 | DRY | High | Собственный алгоритм нумерации заказов (COUNT+1), не совпадает с реальным персистентным счётчиком — коллизии номеров |
|6| service_layer.py:383 | clean-code | High | update_client_stats затирает total_spent нулём под TODO (см. п.6 сводки) |
|7| events/domain_events.py:127 | YAGNI | Med | EventBus/DomainEvent — ~340 строк без единого реального потребителя |
|8| events/domain_events.py:268 | clean-code | Med | Декоратор event_handler перетирает subscribed_events, явные property мертвы |
|9| events/domain_events.py:135 | reinventing-wheel | Low | Избыточный get_instance() поверх уже готового Singleton через __new__ |
|10| order_specifications.py:179 | YAGNI | Med | Весь Specification-слой не используется — фильтрация в GUI сделана вручную |
|11| order_specifications.py:300 | SRP | Low | Демо-скрипт с print() встроен в продовый модуль бизнес-правил |

### 3.5 GUI Main Window (`gui/main_window.py`) — 13 находок
| # | Строка | Принцип | Sev | Суть |
|---|---|---|---|---|
|1| 42 | SRP | High | ServiceCenterApp — God Object, 1564 строки, окно+БД+отчёты+бэкапы+интеграции+фото+PWA+бизнес-логика |
|2| 1015 | DIP | High | _quick_delete_selected — единственное место с сырым sqlite3 в обход фасада (у Database нет delete_device) |
|3| 1195 | DRY | Med | Цепочка «взять выбранную строку → получить устройство» скопирована 4-5 раз |
|4| 915 | clean-code | Low | Статусы как строковые литералы вместо констант |
|5| 279 | clean-code | Med | 39 блоков except Exception, часть — silent pass, 16 print() вместо logging |
|6| 735 | SRP | Med | Жизненный цикл встроенного PWA-сервера в GUI-классе, ленивая инициализация продублирована 3 раза |
|7| 1238 | SRP | Med | Файловый I/O чтения шаблона акта прямо в GUI-классе вместо ReportGenerator |
|8| 65 | clean-code | Low | 4 неиспользуемых атрибута экземпляра |
|9| 62 | YAGNI | Low | integration_manager не используется нигде; work_manager дублируется локальными инстансами |
|10| 857 | clean-code | Low | 2 неиспользуемых приватных метода (один — no-op) |
|11| 1394 | YAGNI | Med | print_dual_acts — мёртвая фича «печать двух актов», нигде не вызывается из UI |
|12| 688 | DRY | Low | Контекстное меню и панель действий на 90% дублируют список пунктов |
|13| 619 | SRP | Low | 2 диалога построены inline вместо gui/dialogs/, нарушая паттерн проекта |
|14| 197 | KISS | Low | refresh_ui пересоздаёт всё дерево виджетов ради смены темы |

### 3.6 GUI Widgets — 10 находок
God Object дашборд с прямым доступом к БД и дублированием бизнес-правила (14 дней), `premium.py` — лживый докстринг + полный дубль `modern.py`, дублирование логики миниатюр, самодельный polling-скроллбар с 4 параллельными механизмами проверки, неполный публичный API пакета. Полный список — в журнале аудита (agent `review:gui_widgets`).

### 3.7 GUI Dialogs (крупные: device_form, act_preview, client_history, work_item_dialog) — 12 находок
Ключевое: **`device_form.py` содержит ~290 строк недостижимого мёртвого кода** (см. п.4 сводки) и является God Object на 1428 строк; `_do_save`/`save()` независимо собирают device_data с разошедшейся валидацией; прямой SQL к `counters` в обход `Database.get_next_order_number`; hardcoded карта тип-устройства→бренды не согласована с БД-справочником; 7 мест silent `except: pass`.

### 3.8 GUI Dialogs (мелкие: settings, dictionaries, activation, work_template_picker, photo_viewer, pwa_qr) — 9 находок
Копипаст жизненного цикла окна (geometry/transient/grab_set) в 10 диалогах без общего базового класса; диалоги обращаются к `self.db` напрямую в обход сервисного слоя; дублирование логики миниатюр; рассинхронизированная резервная цветовая палитра; dead import; неполный экспорт пакета `gui/dialogs/__init__.py`.

### 3.9 Managers — 6 находок
`managers/reports.py` дублирует `report_renderer.py` и засоряет каталог исходников `.txt`-файлами (см. п.9 сводки); **весь модуль SMS/Email-уведомлений в `integrations.py` физически недостижим** (ключи настроек нигде не объявлены в UI/DEFAULT_SETTINGS, `merge_settings` их отбрасывает) — заглушки с `print()+return True`; письмо «заказ готов» отправляется на собственный email сервиса, а не клиента (в БД нет поля email клиента); дублирование санитизации имён файлов; `SettingsManager.set()` — 22 полных перезаписи JSON на одно сохранение настроек.

### 3.10 Reports — 9 находок
`FIELD_LABELS` продублирован и **разошёлся** между редактором и рендерером; `ActPanel` — 655-строчный God Object; `print_pdf()` заново реализует то, что уже есть в `print_utils.print_act_pdf` (без очистки temp-файла); неиспользуемый класс `PDFRenderer`; sys.path-хак в `__init__.py`; шрифты жёстко под Windows без platform-ветвления (в отличие от print_utils.py); дублирование пересчёта mm→pt.

### 3.11 PWA сервер (`pwa/server.py`) — 11 находок
`create_flask_app()` — God function на 467 строк с 13 маршрутами-замыканиями; **бизнес-логика заказов заново реализована в обход `OrderService`**, включая отсутствие защиты «нельзя менять статус отказанного заказа»; сырой sqlite3 в обход `Database` при загрузке фото; дублирование расчёта total_price в 2 роутах; **отсутствие авторизации на всех `/api/*`** (см. п.2 сводки); утечка деталей исключения в JSON-ответ 500; несогласованная очистка thread-local ресурсов; хардкод списка гарантий вместо константы.

### 3.12 Utils — 9 находок
Хардкод SECRET_KEY (см. п.1 сводки); `LicenseManager` — God Class (реестр Windows + файлы + HMAC + бизнес-правила триала в одном классе); **два расходящихся источника статусов клиента** (`CLIENT_STATUSES` без VIP vs `DICTIONARY_TYPES` с VIP — два комбобокса в одной форме показывают разные списки); тройное дублирование парсинга цены с разным поведением на некорректном вводе; мёртвое условие `'sizeof' in dir()` (всегда False); `_apply_mac_vibrancy` не делает заявленного (ctypes не используется, alpha выставляется дважды).

### 3.13 Models / корневые тесты — 9 находок
`Device.defects: Optional[str] = Field(..., min_length=1)` — ограничение «обязательно и не пусто» тихо не работает (воспроизведено: `Device(..., defects=None)` проходит); **`ClientStatus.PROBLEMATIC = "Еблан"`** (см. п.7 сводки); phone/email/price валидируются независимо в 4 разных модулях с разным поведением; `Order.calculate_total` — бизнес-правило спрятано в Pydantic-валидатор; **параллельно существуют два несовместимых класса `Device`/`WorkItem`** (dataclass в `database/models.py` и Pydantic в `models/pydantic_models.py`), используемые разными частями проекта; `test_basic.py`/`test_advanced.py` — дублирующие друг друга наборы тестов с одинаковыми именами классов.

### 3.14 Сквозное дублирование по всему репозиторию — 9 находок
Помимо п.0 (архитектурный дубль) и уже перечисленного выше: парсинг даты `YYYY-MM-DD[ HH:MM:SS]` продублирован вручную в 3 GUI-модулях вместо `utils.formatters`; каждый менеджер заново создаёт свою рабочую директорию, хотя `config.ensure_directories()` уже делает это при старте; текст условий ремонта/гарантии продублирован в 3 независимых местах и может разойтись; список статусов захардкожен в фильтре истории клиента; **паттерн `except Exception as e: print(f"❌ ...: {e}")` встречается 105 раз в 25 файлах** — logging используется только в неиспользуемой параллельной архитектуре.

---

## 4. Итоговые рекомендации (по приоритету)

1. **Определить судьбу параллельной архитектуры** (п.0) — она либо мешает (вводит в заблуждение, ломает `pytest`), либо должна быть реально подключена. Без этого решения любой дальнейший рефакторинг БД-слоя рискует чинить код, который никто не запускает.
2. Закрыть три находки с прямым риском для пользователей/данных до всего остального: **хардкод SECRET_KEY** (п.1), **PWA без авторизации** (п.2), **тихая порча статистики клиента** (`total_spent = 0.0`, п.6).
3. Убрать нецензурное значение enum (п.7) — тривиально, но не должно попадать в отчёты клиентам.
4. Устранить 290 строк мёртвого кода в `device_form.py`, чинящего дату приёма (п.4).
5. Ввести единый `logging` и заменить ~105+16+7+... вхождений `print()` в обработчиках ошибок — самая частая находка во всём аудите, механическая и низкорисковая.
6. Точечно устранить дублирование (DRY) там, где оно уже разошлось по поведению (парсинг цены/даты, FIELD_LABELS, статусы клиента, дубли service_layer/__init__.py) — это не только чистота кода, а источники реальных расхождений в данных.
7. Постепенная SRP-декомпозиция God Object'ов (`main_window.py`, `db_manager.py`, `device_form.py`, `report_editor.py`, `pwa/server.py`) техникой Extract Class/Method с сохранением публичного API, под прогон существующих тестов после каждого шага — рискованно делать одним большим шагом без GUI-тестовой обвязки.
