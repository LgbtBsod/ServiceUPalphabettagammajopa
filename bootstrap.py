#!/usr/bin/env python3

"""Модуль инициализации приложения.
Отвечает за проверку зависимостей и создание необходимых директорий.
Вынесен из main.py для соблюдения SRP.
"""


def check_dependencies() -> bool:
    """Проверка наличия необходимых пакетов через requirements.txt.

    Returns:
        bool: True если все зависимости установлены, иначе False
    """
    missing_packages = []

    # Проверяем обязательные пакеты
    required_packages = {
        "customtkinter": "customtkinter",
        "PIL": "Pillow",
    }

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

    core.register_service(IClientRepository, SqlAlchemyClientRepository(db.engine))
    core.register_service(IEmployeeRepository, SqlAlchemyEmployeeRepository(db.engine))
    loaded = core.services.plugin_manager.discover("plugins", context=core)
    if loaded:
        core.logger.info(f"Плагины загружены: {', '.join(loaded)}")

    return core
