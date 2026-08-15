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
