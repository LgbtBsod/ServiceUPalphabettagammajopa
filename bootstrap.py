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
        BackupManager,
        IntegrationManager,
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

    # Те же экземпляры — в DI-контейнере, для типобезопасного get_service(Type)
    # там, где резолвинг по имени модуля неудобен (например, в самих менеджерах).
    core.register_service(Database, db)
    core.register_service(SettingsManager, settings)
    core.register_service(BackupManager, backup_mgr)
    core.register_service(IntegrationManager, integration_mgr)
    core.register_service(PhotoManager, photo_mgr)
    core.register_service(ReportGenerator, report_gen)
    core.register_service(ClientDatabaseManager, client_db)

    # Плагины: регистрируем зависимости, которые им нужны, затем находим
    # и загружаем все модули plugins/*, реализующие register_plugin().
    from plugins.clients import IClientRepository
    from plugins.clients.repository import SqlAlchemyClientRepository

    core.register_service(IClientRepository, SqlAlchemyClientRepository(db.engine))
    loaded = core.services.plugin_manager.discover("plugins", context=core)
    if loaded:
        core.logger.info(f"Плагины загружены: {', '.join(loaded)}")

    return core
