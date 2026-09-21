#!/usr/bin/env python3

"""Централизованный реестр пользовательских сообщений — по КОДУ, а не по
сырой строке в месте вызова (SAP T100-style: класс сообщения (группа) +
имя сообщения внутри класса -> канонический текст).

Использование::

    from utils.messages import Msg

    logger.warning(Msg.Employee.ADD_FAILED)
    messagebox.showerror(Msg.Title.ERROR, Msg.Lock.OPTIMISTIC_CONFLICT)

Каждая группа — вложенный класс (Msg.Employee, Msg.Role, Msg.Lock, ...) —
это и есть "класс сообщений" T100: у SAP код сообщения — это class+number
("ZMM001/001"), здесь то же самое через Python-неймспейс (Msg.Employee.ADDED
читается как "класс EMPLOYEE, сообщение ADDED"), без плоского списка из
полусотни EMPLOYEE_*/ROLE_*-констант с повторяющимся префиксом на каждой
строке. Msg.Title — отдельная, ничья группа: "Ошибка"/"Успех"/
"Предупреждение"/... — заголовки messagebox, переиспользуемые ВСЕМИ
группами одинаково, а не заголовок ошибки на каждый домен отдельно.

Один код — один канонический русский текст, объявленный ОДИН раз здесь;
вызывающий код больше не хардкодит f-string на месте — ни тело сообщения,
ни заголовок диалога. Обычные строки Python (``.format(**kwargs)`` из
stdlib) — специальный класс не нужен (см. AUDIT: попытка переиспользовать
i18n/ для этой цели отклонена — тот пакет решает другую задачу,
locale-fallback по .ini, а не code->template, и не подключён нигде в живом
приложении).

Область применения СЕЙЧАС — код, написанный в рамках фич блокировок
(managers/locking.py, database/sqlalchemy_database.py, gui/dialogs/
device_form.py) как исходный proof-of-concept, плюс employees/roles (RBAC,
см. TODO_RBAC_ROADMAP.md) и часть "Базис"-вкладки — расширяется по мере
того, как код в соответствующей области трогается заново, а не одномоментным
sweep всей кодовой базы (см. Task #38/T)."""

from __future__ import annotations


class Msg:
    """Пространство имён для вложенных "классов сообщений" (см. докстринг
    модуля). Сам класс Msg не содержит сообщений напрямую — только группы."""

    class Title:
        """Общие заголовки messagebox — переиспользуются всеми группами
        ниже одинаково, поэтому вынесены отдельно, а не дублируются на
        каждый домен ("EMPLOYEE_TITLE_ERROR", "ROLE_TITLE_ERROR", ...)."""

        ERROR = "Ошибка"
        SUCCESS = "Успех"
        WARNING = "Предупреждение"
        CONFIRM = "Подтверждение"
        DELETE = "Удаление"
        BASIS = "Базис"

    class Lock:
        """Пессимистичная блокировка (managers/locking.py,
        gui/dialogs/device_form_parts/locking_mixin.py)."""

        HELD_BY_OTHER = "🔒 Заказ редактирует «{holder}» — с {time}. Можно смотреть, но не сохранить."
        REACQUIRED = "🔓 Блокировка снята — можно редактировать."
        STILL_HELD = "Всё ещё занято пользователем «{holder}»."
        CHECK_FAILED = "не удалось проверить блокировку"
        DEVICE_NOT_FOUND = "❌ Заказ больше не существует (возможно, удалён)."
        OPTIMISTIC_CONFLICT = (
            "❌ Заказ изменил другой пользователь, пока форма была открыта. "
            "Закройте окно и откройте заказ заново, чтобы применить правки поверх актуальной версии."
        )

    class Pwa:
        """Оптимистичная блокировка на стороне PWA (pwa/server.py)."""

        ORDER_VERSION_CONFLICT = "Заказ изменён другим пользователем. Обновите данные и повторите."
        PHOTO_VERSION_CONFLICT = "Заказ изменён другим пользователем, повторите загрузку фото."
        LOG_WORK_ITEMS_TOTAL_RECALC_FAILED = (
            "Не удалось пересчитать total_price из work_items ({context})"
        )

    class Settings:
        """Подписи настроек блокировок (gui/dialogs/settings.py,
        Базис-вкладка)."""

        PESSIMISTIC_LOCK_LABEL = (
            "Блокировать заказ на редактирование для других "
            "(доп. к всегда включённой базовой защите)"
        )
        LOCK_TTL_LABEL = "Снимать блокировку через (сек, мин. 120):"

    class Basis:
        """Вкладка "🔧 Базис" (gui/main_window_parts/basis_cockpit_mixin.py)."""

        QUERY_CACHE_LABEL = "Кэш запросов (справочники, TTL ~1 час)"
        QUERY_CACHE_HINT = (
            "Справочники (статусы/бренды/типы устройств) кэшируются на час и "
            "переиспользуются всеми — и обычным окном, и мобильной версией. "
            "При записи через это приложение кэш обновляется сам; кнопка ниже — "
            "на случай, если данные поменяли в обход него."
        )
        REFRESH_CACHE_BUTTON = "🔄 Обновить кэш"
        CACHE_REFRESHED = "Кэш очищен: {count} записей. Следующие запросы прочитают БД заново."
        LOCKING_SAVED = "Настройки блокировок сохранены"
        PERMISSIONS_HINT = (
            "Роли и полномочия можно создавать и назначать сотрудникам "
            "(кнопка ниже), но реального ограничения доступа ещё нет — "
            "пока нет входа по паролю, любой может назначить себе любую "
            "роль тем же диалогом. См. TODO_RBAC_ROADMAP.md."
        )
        MANAGE_ROLES_BUTTON = "🔑 Управление ролями"

    class Loading:
        """Skeleton-loading / busy-индикатор (gui/widgets/skeleton.py,
        gui/main_window_parts/devices_table_mixin.py, finance_mixin.py)."""

        GENERIC = "Загрузка..."
        ORDERS = "Загрузка заказов..."
        SEARCH = "Поиск..."
        FINANCE = "Загрузка финансов..."
        ORDERS_FAILED = "Не удалось загрузить список заказов: {error}"
        FINANCE_FAILED = "Не удалось загрузить финансы: {error}"

    class Employee:
        """Сотрудники (plugins/employees, gui/dialogs/employees.py,
        gui_flet/views_employees.py) — общий текст для обеих оболочек,
        чтобы не расходиться незаметно (workflow-найденное расхождение: см.
        Role ниже, "Удалить роль?" отличался между classic/Flet одним
        словом, пока не свели к одному коду)."""

        NAME_REQUIRED_FOR_LOGIN = "Сначала введите ФИО"
        LOGIN_GENERATION_FAILED = "Не удалось сгенерировать логин: {error}"
        FIELDS_REQUIRED = "Заполните ФИО и логин"
        ADDED = "✅ Сотрудник добавлен"
        ADD_FAILED = "❌ Не удалось добавить (логин уже занят?)"
        SELECT_FIRST = "Сначала выберите сотрудника"
        UPDATED = "✅ Сотрудник обновлён"
        UPDATE_FAILED = "❌ Не удалось обновить (логин уже занят?)"
        ROLES_NOT_SAVED = (
            "⚠️ Данные сотрудника сохранены, но роли — нет: не удалось прочитать "
            "текущие роли при открытии формы, сохранение изменило бы их вслепую. "
            "Откройте сотрудника заново и попробуйте ещё раз."
        )
        SELECT_TO_DELETE = "Выберите сотрудника для удаления"
        DELETE_CONFIRM = "Удалить сотрудника? Записи, созданные им, сохранятся без привязки."
        DELETED = "✅ Сотрудник удалён"
        DELETE_FAILED = "❌ Не удалось удалить сотрудника"
        MODULE_UNAVAILABLE = "Модуль сотрудников недоступен"
        # Лог (не показывается пользователю) — тоже через Msg, SSOT
        # одинаково применяется к тексту логов и диалогов.
        LOG_ROLES_LIST_LOAD_FAILED = "Не удалось загрузить список ролей"
        LOG_ROLES_LOAD_FAILED = "Не удалось загрузить роли сотрудника {employee_id}"

    class Role:
        """Роли/полномочия, RBAC (plugins/employees/roles.py,
        gui/dialogs/roles_manager.py, gui_flet/views_employees.py)."""

        NAME_REQUIRED = "Введите название роли"
        ADDED = "✅ Роль добавлена"
        ADD_FAILED = "❌ Не удалось добавить (название уже занято?)"
        SELECT_FIRST = "Сначала выберите роль"
        UPDATED = "✅ Роль обновлена"
        UPDATE_FAILED = "❌ Не удалось обновить (название уже занято?)"
        SELECT_TO_DELETE = "Выберите роль для удаления"
        DELETE_CONFIRM = "Удалить роль? Она будет снята со всех сотрудников, которым назначена."
        DELETED = "✅ Роль удалена"
        DELETE_FAILED = "❌ Не удалось удалить роль"
        PERMISSIONS_NOT_SAVED = (
            "⚠️ Название/описание роли сохранены, но полномочия — нет: не "
            "удалось прочитать их список при открытии окна, сохранение "
            "изменило бы их вслепую. Закройте окно и откройте заново."
        )
        MODULE_UNAVAILABLE = "Модуль ролей недоступен"
        LOG_PERMISSIONS_LIST_LOAD_FAILED = "Не удалось загрузить список полномочий"

    class Activation:
        """Активация лицензии (gui/main_window_parts/dialogs_mixin.py)."""

        OPEN_FAILED = "Не удалось открыть активацию: {error}"
        LOG_OPEN_FAILED = "Не удалось открыть окно активации лицензии"

    class Report:
        """Редактор актов (gui/main_window_parts/dialogs_mixin.py)."""

        EDITOR_LOAD_FAILED = (
            "Не удалось загрузить редактор: {error}\n\nУстановите reportlab: pip install reportlab"
        )

    class Finance:
        """Редактирование расхода по заказу (gui/main_window_parts/finance_mixin.py)."""

        EXPENSE_UPDATED = "Расход обновлён"
        EXPENSE_UPDATE_FAILED = "Не удалось обновить расход"
        INVALID_NUMBER = "Введите корректное число"

    class Order:
        """Валидация и сохранение заказа
        (gui/dialogs/device_form_parts/save_mixin.py) — save()
        (интерактивное сохранение) и _do_save() (тихое сохранение для
        "печать акта до явного Save") намеренно используют одни и те же
        коды там, где раньше несли независимо продублированный и слегка
        разошедшийся текст (workflow-найденное расхождение: формат ошибки
        телефона отличался между двумя путями одним примером в конце)."""

        DEVICE_TYPE_REQUIRED = "Выберите тип устройства!"
        MODEL_REQUIRED = "Заполните модель устройства!"
        DEFECT_REQUIRED = "Опишите неисправность!"
        CLIENT_NAME_REQUIRED = "Заполните ФИО клиента!"
        PHONE_REQUIRED = "Заполните номер телефона!"
        SILENT_FIELDS_REQUIRED = "Заполните тип устройства, модель, неисправность, имя и телефон!"
        PHONE_FORMAT_INVALID = "Неверный формат телефона!\nПример: +7 (123) 456-78-90"
        PRICE_FORMAT_INVALID = "Неверный формат цены!"
        PREPAYMENT_FORMAT_INVALID = "Неверный формат предоплаты!"
        EXPENSE_FORMAT_INVALID = "Неверный формат затрат!"
        CREATED = "Заказ №{order_number} создан!"
        CREATED_WITH_ICON = "✅ Заказ #{order_number} создан!"
        CREATE_FAILED = "❌ Не удалось создать заказ"
        UPDATED = "✅ Заказ обновлен!"
        SAVED = "Заказ №{order_number} сохранён"
        UPDATE_FAILED = "❌ Не удалось обновить заказ"
        SAVE_FAILED = "❌ Ошибка сохранения: {error}"
        VERSION_CONFLICT_TITLE = "Конфликт версий"
        VERSION_CONFLICT_REFRESH_PROMPT = "Обновить данные из базы сейчас?"
        LOG_SAVE_FAILED = "Ошибка сохранения: {error}"
        LOG_CLIENT_NAME_LOOKUP_FAILED = "Не удалось выполнить автопоиск клиента по имени"

    class Legacy:
        """database/db_manager.py — легаси SQLite-слой, живой только как
        источник для migrate_client_dbs() (одноразовая миграция старых
        per-client БД в SQLAlchemy-схему), не основной путь записи."""

        LOG_PRICE_DUAL_WRITE_FAILED = (
            "Не удалось обновить числовые колонки цен для устройства {device_id}"
        )
