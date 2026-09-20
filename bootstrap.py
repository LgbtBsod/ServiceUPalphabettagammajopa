#!/usr/bin/env python3

"""Модуль инициализации приложения.
Отвечает за проверку зависимостей и создание необходимых директорий.
Вынесен из main.py для соблюдения SRP.
"""


def check_dependencies(ui_mode: str | None = None) -> bool:
    """Проверка наличия необходимых пакетов через requirements.txt.

    Args:
        ui_mode: "classic"/"flet", если оболочка задана явно через --ui=,
            иначе None (интерактивный выбор — доступны обе оболочки, значит
            нужны пакеты для обеих). customtkinter/PIL нужны ВСЕГДА, даже
            при --ui=flet — main.py использует ctk.CTk() для диалогов
            лицензии/обновления независимо от выбранной оболочки заказов.
            flet нужен, только если пользователь может попасть в Flet-режим
            (--ui=flet или сам выбор ещё не сделан).

    Returns:
        bool: True если все зависимости установлены, иначе False

    Регрессия (живой отчёт с чужой машины, свежий git-checkout без venv):
    main.py --ui=flet падал сырым traceback'ом ModuleNotFoundError: No
    module named 'flet' вместо понятного "Отсутствуют обязательные пакеты"
    — эта проверка знала только про customtkinter/PIL (нужны классической
    оболочке), про flet не знала вообще, хотя main.py поддерживает выбор
    Flet-оболочки (--ui=flet или диалог выбора). Заодно добавлены pydantic/
    sqlalchemy — та же болезнь: main.py импортирует их до любого выбора
    оболочки (ensure_directories()/initialize_kernel()), а эта проверка
    их не знала вообще.
    """
    missing_packages = []

    # Проверяем обязательные пакеты — customtkinter/PIL/pydantic/sqlalchemy
    # нужны ВСЕГДА независимо от ui_mode: config/settings.py (pydantic) и
    # database/ (sqlalchemy) импортируются в main.py до любого выбора
    # оболочки (ensure_directories()/initialize_kernel()), а
    # customtkinter/PIL — диалогами лицензии/обновления даже при --ui=flet.
    required_packages = {
        "customtkinter": "customtkinter",
        "PIL": "Pillow",
        "pydantic": "pydantic",
        "sqlalchemy": "sqlalchemy",
    }
    if ui_mode != "classic":
        required_packages["flet"] = "flet[web]"

    for module_name, package_name in required_packages.items():
        try:
            __import__(module_name)
        except ImportError:
            missing_packages.append(package_name)

    # requests не обязателен, но рекомендуется (информируем пользователя)
    try:
        __import__("requests")
    except ImportError:
        print("⚠️  requests не установлен (опционально, для интеграций)")

    if missing_packages:
        print(f"❌ Отсутствуют обязательные пакеты: {', '.join(missing_packages)}")
        print("Установите их командой:")
        print(f"pip install {' '.join(missing_packages)}")
        print("\nИли используйте requirements.txt:")
        print("pip install -r requirements.txt")
        return False

    return True


def ensure_directories() -> None:
    """Создание необходимых директорий.

    Делегирует функцию ensure_directories из config.py
    для централизованного управления путями.
    """
    from config import ensure_directories as _create_dirs

    _create_dirs()


def initialize_kernel():
    """Инициализирует Kernel (core.kernel.ServiceUpCore) и регистрирует в его
    реестре синглетонов модулей реальные сервисы приложения — Database
    (SQLAlchemy-facade, под именем 'db_access'), ClientDatabaseManager и
    менеджеры. Модули НЕ импортируют друг друга напрямую — только через ядро:

        core.get_db_access().get_all_devices()          # доступ к БД
        core.get_module_api('reports').generate(...)     # доступ к менеджеру
        core.call_module_method('db_access', 'add_device', data)

    Каждый сервис также зарегистрирован в DI-контейнере (core.get_service)
    для типобезопасного разрешения там, где это удобнее модуля по имени —
    оба пути ведут к ОДНОМУ и тому же экземпляру.

    Возвращает инициализированный ServiceUpCore.
    """
    from core.kernel import get_core
    from database import ClientDatabaseManager
    from database.sqlalchemy_database import Database
    from managers import (
        AnalyticsService,
        BackupManager,
        IntegrationManager,
        LockManager,
        PhotoManager,
        ReportGenerator,
        SettingsManager,
    )

    core = get_core()
    core.initialize()

    # ServiceUpCore.initialize() запускает WorkerPool (не-daemon executor-потоки
    # concurrent.futures) — ни main.py, ни gui/main_window.py.on_closing() нигде
    # не звали core.shutdown(), поэтому при выходе из mainloop интерпретатор
    # вешался навсегда на join() этих потоков (worker-loop не видит флага
    # остановки executor'а, только свой self._shutdown, который выставляет
    # только core.shutdown()). atexit — самая надёжная точка: срабатывает и на
    # нормальном выходе, и на необработанном исключении, её нельзя случайно
    # пропустить ранним return из on_closing(). core.shutdown() идемпотентен.
    import atexit

    atexit.register(core.shutdown)

    db = Database()
    settings = SettingsManager()
    backup_mgr = BackupManager(settings)
    integration_mgr = IntegrationManager(settings)
    photo_mgr = PhotoManager(settings)
    report_gen = ReportGenerator()
    client_db = ClientDatabaseManager(main_db=db)
    # Analytics не владеет своей таблицей (агрегирует devices/finances чужих
    # модулей) — получает ядро, а не движок БД напрямую: любой запрос к БД
    # идёт через core.call_module_method('db_access', ...), см. managers/analytics.py.
    analytics_svc = AnalyticsService(core)
    # Как Analytics — не владеет своей таблицей записей-заказов, только
    # record_locks, но бизнес-логика (TTL, идентичность держателя) зависит
    # от employees/settings, поэтому получает ядро, а не движок БД напрямую.
    lock_mgr = LockManager(core)

    # 'db_access' — зарезервированное имя (core.module_manager.ModuleRegistry):
    # единственный способ добраться до БД — через core.get_db_access(), без
    # исключений. Ни один модуль не хранит db.conn / raw sqlite3 напрямую.
    core.register_module("db_access", db, Database, api=db)
    core.register_module("settings", settings, SettingsManager, api=settings)
    core.register_module("backup", backup_mgr, BackupManager, api=backup_mgr)
    core.register_module(
        "integrations", integration_mgr, IntegrationManager, api=integration_mgr
    )
    core.register_module("photos", photo_mgr, PhotoManager, api=photo_mgr)
    core.register_module("reports", report_gen, ReportGenerator, api=report_gen)
    core.register_module(
        "client_history", client_db, ClientDatabaseManager, api=client_db
    )
    core.register_module("analytics", analytics_svc, AnalyticsService, api=analytics_svc)
    core.register_module("locking", lock_mgr, LockManager, api=lock_mgr)

    # Раньше AnalyticsService._REPORTS сверялся с
    # Database.list_calculations() ТОЛЬКО в test suite
    # (tests/test_analytics.py::TestReportsWhitelistConsistency) — реально
    # работающее приложение никогда не проверяло, что whitelist не разошёлся
    # с CalculateMixin.calculate() (см. AUDIT_REPORT_v25.md, Task P
    # verify-пасс). Не бросаем — расхождение одного отчёта не должно ронять
    # весь запуск приложения, но обязано быть видно в логе сразу, а не
    # только когда пользователь случайно откроет именно этот отчёт.
    _broken_reports = analytics_svc.verify_calculations_available(db.list_calculations())
    if _broken_reports:
        core.logger.error(
            f"AnalyticsService._REPORTS расходится с Database.list_calculations(): "
            f"отчёты {_broken_reports} упадут ValueError при первом обращении"
        )

    # Первый реальный потребитель core/events/event_bus.py в приложении —
    # раньше EventBus был полностью построен и зарегистрирован в DI, но ни
    # один код нигде не publish()/subscribe(), см. AUDIT_REPORT_v25.md.
    # database/sqlalchemy_database.py публикует DeviceStatusChangedEvent
    # при смене статуса (оба пути — полная форма и быстрая кнопка/PWA),
    # IntegrationManager реагирует на переход в "Готов к выдаче".
    from domain.events import DeviceStatusChangedEvent

    core.subscribe(DeviceStatusChangedEvent, integration_mgr.on_device_status_changed)

    # Раньше эти же 7 экземпляров ДОПОЛНИТЕЛЬНО регистрировались в DI-контейнере
    # через core.register_service(Type, instance) — но ни один живой вызов
    # core.get_service(Database/SettingsManager/BackupManager/...) не читает
    # их обратно; весь реальный межмодульный доступ идёт через именной путь
    # (core.get_module_api/get_db_access выше). DI-контейнер оставлен только
    # для его единственного реального применения — резолвинга интерфейсов
    # для конструирования плагинов (IClientRepository ниже), см.
    # AUDIT_REPORT_v21.md.

    # Плагины: регистрируем зависимости, которые им нужны, затем находим
    # и загружаем все модули plugins/*, реализующие register_plugin().
    from plugins.clients import IClientRepository
    from plugins.clients.repository import SqlAlchemyClientRepository
    from plugins.employees import IEmployeeRepository
    from plugins.employees.repository import SqlAlchemyEmployeeRepository
    from plugins.orders import IOrderRepository
    from plugins.orders.repository import SqlAlchemyOrderRepository

    core.register_service(IClientRepository, SqlAlchemyClientRepository(db.engine))
    core.register_service(IEmployeeRepository, SqlAlchemyEmployeeRepository(db.engine))
    # orders — в отличие от clients/employees, репозиторий оборачивает уже
    # готовый Database facade (db), а не голый db.engine — см.
    # plugins/orders/repository.py за причиной.
    core.register_service(IOrderRepository, SqlAlchemyOrderRepository(db))
    loaded = core.services.plugin_manager.discover("plugins", context=core)
    if loaded:
        core.logger.info(f"Плагины загружены: {', '.join(loaded)}")

    _initialize_rbac(core)

    return core


def _initialize_rbac(core) -> None:
    """Подключает ролевую модель (roles/permissions, см.
    TODO_RBAC_ROADMAP.md) ПОСЛЕ дискавери плагинов — EmployeeService уже
    существует (создан EmployeesPlugin.on_initialize()), но реальная
    проверка has_permission() до этого момента была заглушкой (всегда True).

    Вызывается ОДИН раз при каждом старте приложения — сид/миграция внутри
    (RoleService.seed_default_rbac) идемпотентны, повторный вызов ничего не
    ломает и не дублирует.
    """
    from plugins.employees.roles import IRoleRepository, RoleService
    from plugins.employees.roles_repository import SqlAlchemyRoleRepository

    db = core.get_db_access()
    role_repo = SqlAlchemyRoleRepository(db.engine)
    core.register_service(IRoleRepository, role_repo)
    role_service = RoleService(role_repo)
    core.register_module("roles", role_service, RoleService, api=role_service)

    employees_api = core.get_module_api("employees")
    if employees_api is None:
        core.logger.warning("RBAC: модуль 'employees' не загружен, RoleService не подключён")
        return
    employees_api.attach_role_service(role_service)

    # Явный список модулей, чьи сервисы уже объявили permission_object (см.
    # core.base.PermissionObject) — расширять по мере того, как новые
    # сервисы объявляют свой объект полномочий (см. TODO_RBAC_ROADMAP.md).
    declared_permission_objects = []
    for module_name in ("clients", "employees", "analytics"):
        api = core.get_module_api(module_name)
        po = getattr(type(api), "permission_object", None) if api is not None else None
        if po is not None:
            declared_permission_objects.append(po)

    from plugins.employees import ListEmployeesQuery

    all_employee_ids = [e.id for e in employees_api.list_employees(ListEmployeesQuery(active_only=False))]
    role_service.seed_default_rbac(declared_permission_objects, all_employee_ids)
