#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Сервисный центр - Учет ремонта техники
Версия 14.3
Структурированная версия
"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

# ==================== ПРОВЕРКА ЗАВИСИМОСТЕЙ ====================

def check_dependencies():
    """Проверка наличия необходимых пакетов"""
    missing_packages = []
    
    try:
        import customtkinter
    except ImportError:
        missing_packages.append("customtkinter")
    
    try:
        import PIL
    except ImportError:
        missing_packages.append("Pillow")
    
    # requests не обязателен, но рекомендуется
    try:
        import requests
    except ImportError:
        print("⚠️ requests не установлен (опционально, для интеграций)")
    
    if missing_packages:
        print(f"❌ Отсутствуют обязательные пакеты: {', '.join(missing_packages)}")
        print("Установите их командой:")
        print(f"pip install {' '.join(missing_packages)}")
        input("Нажмите Enter для выхода...")
        sys.exit(1)
    
    return True

# ==================== ПРОВЕРКА ДИРЕКТОРИЙ ====================

def check_directories():
    """Проверка и создание необходимых директорий"""
    from config import BASE_DIR, BACKUP_DIR, EXPORT_DIR, PHOTOS_DIR, THUMBNAILS_DIR, CLIENTS_DB_DIR, REPORTS_DIR
    
    # Создаём папку для шаблонов отчётов
    templates_dir = os.path.join(REPORTS_DIR, "templates")
    os.makedirs(templates_dir, exist_ok=True)
    
    # Создаём остальные директории
    for directory in [BACKUP_DIR, EXPORT_DIR, PHOTOS_DIR, THUMBNAILS_DIR, CLIENTS_DB_DIR, REPORTS_DIR, templates_dir]:
        os.makedirs(directory, exist_ok=True)
    
    return True

check_dependencies()
check_directories()

# Импортируем customtkinter
import customtkinter as ctk

# Импортируем основное приложение
from gui import ServiceCenterApp


def main():
    """Точка входа в приложение"""
    try:
        print("╔" + "═" * 50 + "╗")
        print("║" + " " * 14 + "ServiceUP v15.0" + " " * 14 + "║")
        print("╠" + "═" * 50 + "╣")
        print("║" + " " * 12 + "УЧЁТ РЕМОНТА ТЕХНИКИ" + " " * 12 + "║")
        print("╚" + "═" * 50 + "╝")
        print()

        # --- Проверка лицензии перед запуском ---
        from utils.license_manager import LicenseManager
        lic = LicenseManager()
        status = lic.check_license()
        print(f"🔐 Статус лицензии: {status}")

        if status in ('trial_expired', 'corrupted') or \
           (status == 'trial_active' and lic.get_trial_days_left() <= 3):
            # Показываем окно активации (трийал почти истёк или истёк)
            from gui.dialogs.activation_dialog import ActivationDialog
            root = ctk.CTk()
            root.withdraw()
            dialog = ActivationDialog(root, lic)
            root.wait_window(dialog)

            if not lic.is_activated() and status in ('trial_expired', 'corrupted'):
                print("❌ Программа не активирована. Завершение.")
                sys.exit(0)
            root.destroy()

        elif status == 'trial_active':
            days_left = lic.get_trial_days_left()
            print(f"📅 Пробный период: осталось {days_left} дн.")

        # --- Запуск приложения (только если лицензия пройдена) ---
        app = ServiceCenterApp()
        app.run()
        
    except KeyboardInterrupt:
        print("\n👋 Программа завершена")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        input("\nНажмите Enter для выхода...")
        sys.exit(1)


if __name__ == "__main__":
    main()
