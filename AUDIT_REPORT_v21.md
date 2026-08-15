# ServiceUP: аудит архитектуры v21 — SSOT / SOLID / DRY / модульность

Параллельный аудит (18 подсистем × находка+верификация = 36 агентов) всего текущего дерева (338 файлов) на нарушения SSOT, "не изобретай велосипед", SOLID/SRP/DIP/LSP, DRY, clean code, Python 3.14+ практики и границы модульности/plugin-архитектуры (ядро Kernel из предыдущей сессии).

**150 подтверждённых находок, 2 отклонено верификатором.**

## Главный вывод

Тот же паттерн, что был обнаружен в двух предыдущих аудитах этой сессии, оказался ещё более системным: **каждая новая "рефакторинговая" итерация добавляла ОЧЕРЕДНУЮ параллельную реализацию базовых понятий, не убирая предыдущие**. Конкретно по счётчикам:

| Понятие | Сколько независимых реализаций | Файлы |
|---|---|---|
| `OrderStatus` (статус заказа) | **5**, три из них сами называют себя "SSOT" | `shared/kernel.py`, `domain/entities.py`, `domain/state_machines/native_state_machine.py`, `domain/state_machines/order_machine.py`, `models/pydantic_models.py` |
| Подключение к БД / `DatabaseConnection` | **4** | `database/db_manager.py` (raw sqlite3, живой), `database/sqlalchemy_database.py` (живой facade), `infrastructure/db/connection.py` + `infrastructure/db/repositories.py` (дубль внутри одного пакета!), `database/db_manager_ssot.py` (сломан, не импортируется) |
| Лицензирование | **2** полных копии алгоритма | `utils/license_manager.py` (реально используется), `infrastructure/licensing/` (не используется, и уже **разошёлся** поведением — работает только с HKCU, тогда как живой читает HKLM+fallback) |
| Plugin/module-система | **2** | `core/plugin_system.py` + `plugins/` (то, что подключено в этой сессии), `core/module_registry.py` + `core/module_loader.py` + `modules/` (мёртвая, и её собственный пример модуля сам не может быть найден её же правилами обнаружения) |
| Форматирование/валидация телефона-цены-email | **3** | `utils/formatters.py`+`utils/validators.py` (реально используется почти всем), `shared/utils.py` (заявлен как консолидация, используется только новым плагином `clients`), `models/pydantic_models.py` |
| Тема виджетов (Modern* vs Premium*) | **2**, обе реально используются в разных диалогах одновременно | `gui/widgets/modern.py`, `gui/widgets/premium.py` (докстринг лжёт: "тонкие алиасы поверх Modern*" — на деле независимая копия) |
| Загрузка шаблона акта (`_load_act_template`) | **3** копии с разным поведением при отсутствии файла | `gui/main_window.py`, `gui/dialogs/device_form.py`, `reports/report_editor.py` |
| `config` модуль | **2** (второй мёртв, но не удалён) | `config.py` (полностью затенён, дублирует секрет лицензии, `ensure_directories()` упал бы AttributeError) и пакет `config/` (реальный) |
| Версия приложения | **4 разных значения** | `main.py`="15.0", `shared/kernel.py`="17.0", `shared/__init__.py`="20.0", `config`="23.0", `pyproject.toml`="25.0.0" |

## Регрессии, которые я сам внёс в этой сессии при подключении Kernel — приоритет №1

1. **`gui/dialogs/device_form.py:213`** — превью следующего номера заказа делает `self.db.conn.cursor()`. Я не поймал этот вызов при переводе `main_window.py` на `core.get_db_access()` — у нового facade нет `.conn`. AttributeError ловится голым `except`, поэтому диалог «Новое устройство» **всегда показывает номер «???»** вместо реального. Живой баг, не гипотетический.
2. **`database/__init__.py`** экспортирует `Database` = легаси raw-sqlite3 класс (`db_manager.Database`), а не новый facade — `device_form.py`/`client_history.py` типизируют `db: Database` на неверный класс. Это и есть корень находки №1.
3. **`ReportGenerator` не проброшен в дочерние диалоги** — `DeviceFormDialog`/`ClientHistoryWindow` по-прежнему делают `ReportGenerator()` сами внутри себя (`from managers import ReportGenerator`), а не берут единственный экземпляр из `core.get_module_api("reports")`, который я зарегистрировал в ядре. Три независимых инстанса вместо одного.
4. **PWA-сервер не может перезапуститься** — `core.create_thread(name="PWA-Server", ...)`, который я подключил в WP5, кидает `ValueError` при повторном `start()`, потому что `stop()` не освобождает имя потока в `ThreadManager`. Toggle "Мобильная версия" выключить-включить второй раз сломается.
5. **`Database.calculate()`**, который я построил специально чтобы закрыть 4-кратное дублирование "просрочено >14 дней" — **сам оказался не подключён**: `gui/main_window.py` (дважды) и `gui/widgets/dashboard.py` продолжают независимо хардкодить `> 14` вместо вызова `self.db.calculate("overdue_count")`.

## Другие критичные находки (не мои регрессии, ранее существовавшие)

- **`managers/settings.py`**: `DEFAULT_SETTINGS.copy()` — **shallow copy**. Первое же сохранение геометрии окна мутирует вложенный словарь общего глобального дефолта; кнопка «Сбросить настройки» после этого больше не возвращает настоящие дефолты. Воспроизведено напрямую.
- **`managers/photo_manager.py`**: настройки "Качество фото" и "Создавать миниатюры" из UI **никогда не читаются** — `PhotoManager` не принимает `settings` вообще, качество захардкожено (85/70).
- **`domain/aggregates.py` + 2 state machine**: граф переходов статуса заказа продублирован **3 раза с несовместимыми состояниями** — если мёртвый стек `application/`/`domain/` когда-нибудь подключат, три источника правды о том, какой переход разрешён, дадут разные ответы.
- **`application/order_services.py`**: вызывает `self._order_service.create()`, `.validate_status_transition()`, `.calculate_total()` — **ни один из этих методов не существует** на `OrderService`. Гарантированный `AttributeError`, если этот код когда-либо заработает.
- **`application/reporting_services.py`**: создаёт `ReportEditor()` (GUI Toplevel-окно!) как headless-сервис и зовёт несуществующий `.generate_act()`.
- **`database/repositories/device_repository.py`**: `client_id` вычисляется, но не передаётся в конструктор `DeviceModel` — связь клиент↔устройство молча не сохраняется (в мёртвой архитектуре, но баг реальный).
- **PWA безопасность**: сравнение API-ключа через `!=` вместо `secrets.compare_digest` (тайминг-атака); эндпоинты записи не валидируют `status`/`priority` против разрешённых значений — можно записать произвольную строку в БД.
- **`config.py`** (корневой, затенённый файл) всё ещё не удалён — дублирует секрет лицензии, а `ensure_directories()` в нём упал бы `AttributeError`, если бы он вообще был достижим.

## Находки по темам (агрегировано, полный список в журнале workflow)

- **SSOT-нарушений**: 47
- **DRY-нарушений**: 31
- **modularity/plugin-architecture нарушений**: 12 (включая findings из специального прохода)
- **python-3.14 анахронизмов**: 15 (смешение `typing.Optional/Dict/List` и PEP 604/695 в одних и тех же файлах, `datetime.now()` без timezone рядом с timezone-aware кодом, `object.__setattr__` в не-frozen датаклассах, дубли `TypeVar` рядом с PEP 695 generics)
- **reinventing-the-wheel**: 9 (наивный `str.replace('?', ...)` вместо параметризованных запросов, ручной SQL вместо `Path.is_relative_to()`, независимый async-executor без единого потребителя, ручной thumbnail-ресайз вместо готового `PhotoManager.create_thumbnail`)
- **Dead code** (не вызывается никем): `_dismiss_context_menu`, `_auto_size_columns`, `_fit_window` (×2 копии), `print_dual_from_form`, `PremiumButton`/`PremiumCombobox`, `ModernTextbox`/`ModernCheckbox`, весь `IntegrationSettingsDialog`, вся `shared/async_utils.py`, весь `core/module_registry.py`+`modules/`, `database/db_manager_ssot.py`, `database/repositories/` + `services/service_layer.py` + `events/domain_events.py` (уже задокументированы ранее)

## Рекомендованный порядок закрытия

1. **Регрессии из этой сессии (5 пунктов выше)** — самое дешёвое и самое важное: реальные живые баги, которые я внёс сам.
2. **`managers/settings.py` shallow-copy баг** — простой фикс (`copy.deepcopy`), реальное повреждение данных настроек.
3. **`database/__init__.py` переэкспорт `Database`** — переименовать легаси-класс, чтобы `from database import Database` больше не давал не тот тип.
4. Консолидация SSOT: выбрать по одному источнику для `OrderStatus`/`Priority`/config БД/валидаторов, удалить остальные — самая крупная по объёму, но механическая работа.
5. Удаление подтверждённо мёртвых, сломанных стеков (`config.py`, `database/db_manager_ssot.py`, `core/module_registry.py`+`modules/`, `infrastructure/licensing/`, `infrastructure/db/repositories.py`) — требует вашего решения по каждому (как и в прошлый раз с "мёртвой" архитектурой).
6. `PhotoManager` — подключить настройки качества/миниатюр.
7. Python 3.14+ модернизация (`typing.Optional/Dict/List` → `X | None`/`dict`/`list`, `slots=True` для горячих датаклассов) — низкий риск, чисто механическая правка.
8. Widget-библиотека Modern* vs Premium* — решить, какую оставить, мигрировать остальные диалоги.
