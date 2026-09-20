#!/usr/bin/env python3

"""Централизованный реестр пользовательских сообщений — по КОДУ, а не по
сырой строке в месте вызова (SAP T100-style: класс/номер сообщения ->
канонический текст).

Использование::

    from utils.messages import Msg

    logger.warning(Msg.LOGIN_TAKEN.format(login=command.login))
    messagebox.showerror("Ошибка", Msg.OPTIMISTIC_CONFLICT.format())

Один код — один канонический русский текст, объявленный ОДИН раз здесь;
вызывающий код больше не хардкодит f-string на месте. Обычные строки Python
(``.format(**kwargs)`` из stdlib) — специальный класс не нужен (см.
AUDIT: попытка переиспользовать i18n/ для этой цели отклонена — тот пакет
решает другую задачу, locale-fallback по .ini, а не code->template, и не
подключён нигде в живом приложении).

Область применения СЕЙЧАС — только код, написанный в рамках фич
блокировок (managers/locking.py, database/sqlalchemy_database.py,
gui/dialogs/device_form.py) как proof-of-concept паттерна. Перенос
остальных ~сотен разбросанных по коду сообщений — отдельная, отдельно
согласованная задача (см. Task #38/T во избежание одномоментного
sweep всей кодовой базы)."""

from __future__ import annotations


class Msg:
    """Коды сообщений, сгруппированные по области. Значение — канонический
    русский текст с {placeholder}-плейсхолдерами (обычный str.format —
    отсутствующий плейсхолдер бросает KeyError, и это осознанно: опечатка в
    коде должна падать громко, а не молча деградировать до сырого ключа,
    как это делает i18n/service.py)."""

    # --- Пессимистичная блокировка (managers/locking.py, device_form.py) ---
    LOCK_HELD_BY_OTHER = "🔒 Заказ редактирует «{holder}» — с {time}. Можно смотреть, но не сохранить."
    LOCK_REACQUIRED = "🔓 Блокировка снята — можно редактировать."
    LOCK_STILL_HELD = "Всё ещё занято пользователем «{holder}»."

    # --- Оптимистичная блокировка (Database.update_device) ---
    OPTIMISTIC_CONFLICT = (
        "❌ Заказ изменил другой пользователь, пока форма была открыта. "
        "Закройте окно и откройте заказ заново, чтобы применить правки поверх актуальной версии."
    )

    # --- Оптимистичная блокировка на стороне PWA (pwa/server.py) ---
    PWA_ORDER_VERSION_CONFLICT = "Заказ изменён другим пользователем. Обновите данные и повторите."
    PWA_PHOTO_VERSION_CONFLICT = "Заказ изменён другим пользователем, повторите загрузку фото."

    # --- Диагностика блокировок (managers/locking.py) ---
    LOCK_CHECK_FAILED = "не удалось проверить блокировку"

    # --- Настройки блокировок (gui/dialogs/settings.py) ---
    SETTINGS_PESSIMISTIC_LOCK_LABEL = (
        "Блокировать заказ на редактирование для других "
        "(доп. к всегда включённой базовой защите)"
    )
    SETTINGS_LOCK_TTL_LABEL = "Снимать блокировку через (сек, мин. 120):"

    # --- Кэш запросов к БД (database/db_core.py, Task W) ---
    BASIS_QUERY_CACHE_LABEL = "Кэш запросов (справочники, TTL ~1 час)"
    BASIS_QUERY_CACHE_HINT = (
        "Справочники (статусы/бренды/типы устройств) кэшируются на час и "
        "переиспользуются всеми — и обычным окном, и мобильной версией. "
        "При записи через это приложение кэш обновляется сам; кнопка ниже — "
        "на случай, если данные поменяли в обход него."
    )
    BASIS_REFRESH_CACHE_BUTTON = "🔄 Обновить кэш"
    BASIS_CACHE_REFRESHED = "Кэш очищен: {count} записей. Следующие запросы прочитают БД заново."

    # --- Skeleton-loading / busy-индикатор (gui/widgets/skeleton.py, Task O) ---
    LOADING_GENERIC = "Загрузка..."
    LOADING_ORDERS = "Загрузка заказов..."
    LOADING_SEARCH = "Поиск..."
    LOADING_FINANCE = "Загрузка финансов..."
    LOAD_ORDERS_FAILED = "Не удалось загрузить список заказов: {error}"
    LOAD_FINANCE_FAILED = "Не удалось загрузить финансы: {error}"

    # --- Сотрудники (plugins/employees, gui/dialogs/employees.py,
    # gui_flet/views_employees.py) — общий текст для обеих оболочек, чтобы
    # не расходиться незаметно (workflow-найденное расхождение: см. ROLE_*
    # ниже, "Удалить роль?" отличался между classic/Flet одним словом) ---
    EMPLOYEE_NAME_REQUIRED_FOR_LOGIN = "Сначала введите ФИО"
    EMPLOYEE_LOGIN_GENERATION_FAILED = "Не удалось сгенерировать логин: {error}"
    EMPLOYEE_FIELDS_REQUIRED = "Заполните ФИО и логин"
    EMPLOYEE_ADDED = "✅ Сотрудник добавлен"
    EMPLOYEE_ADD_FAILED = "❌ Не удалось добавить (логин уже занят?)"
    EMPLOYEE_SELECT_FIRST = "Сначала выберите сотрудника"
    EMPLOYEE_UPDATED = "✅ Сотрудник обновлён"
    EMPLOYEE_UPDATE_FAILED = "❌ Не удалось обновить (логин уже занят?)"
    EMPLOYEE_SELECT_TO_DELETE = "Выберите сотрудника для удаления"
    EMPLOYEE_DELETE_CONFIRM = "Удалить сотрудника? Записи, созданные им, сохранятся без привязки."
    EMPLOYEE_DELETED = "✅ Сотрудник удалён"
    EMPLOYEE_DELETE_FAILED = "❌ Не удалось удалить сотрудника"
    EMPLOYEES_MODULE_UNAVAILABLE = "Модуль сотрудников недоступен"

    # --- Роли/полномочия, RBAC (plugins/employees/roles.py,
    # gui/dialogs/roles_manager.py, gui_flet/views_employees.py) ---
    ROLE_NAME_REQUIRED = "Введите название роли"
    ROLE_ADDED = "✅ Роль добавлена"
    ROLE_ADD_FAILED = "❌ Не удалось добавить (название уже занято?)"
    ROLE_SELECT_FIRST = "Сначала выберите роль"
    ROLE_UPDATED = "✅ Роль обновлена"
    ROLE_UPDATE_FAILED = "❌ Не удалось обновить (название уже занято?)"
    ROLE_SELECT_TO_DELETE = "Выберите роль для удаления"
    ROLE_DELETE_CONFIRM = "Удалить роль? Она будет снята со всех сотрудников, которым назначена."
    ROLE_DELETED = "✅ Роль удалена"
    ROLE_DELETE_FAILED = "❌ Не удалось удалить роль"
    ROLES_MODULE_UNAVAILABLE = "Модуль ролей недоступен"

    # --- Полномочия в "Базис" (gui/main_window_parts/basis_cockpit_mixin.py)
    # — тот же паттерн, что BASIS_QUERY_CACHE_HINT/BASIS_REFRESH_CACHE_BUTTON
    # выше, для соседней секции того же экрана ---
    BASIS_PERMISSIONS_HINT = (
        "Роли и полномочия можно создавать и назначать сотрудникам "
        "(кнопка ниже), но реального ограничения доступа ещё нет — "
        "пока нет входа по паролю, любой может назначить себе любую "
        "роль тем же диалогом. См. TODO_RBAC_ROADMAP.md."
    )
    BASIS_MANAGE_ROLES_BUTTON = "🔑 Управление ролями"
