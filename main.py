#!/usr/bin/env python3

"""Сервисный центр - Учет ремонта техники
Версия 15.0
Структурированная версия
"""

import sys
import warnings

warnings.filterwarnings("ignore")


def main():
    """Точка входа в приложение"""
    # ==================== ПРОВЕРКА ЗАВИСИМОСТЕЙ ====================
    from bootstrap import check_dependencies, ensure_directories

    if not check_dependencies():
        sys.exit(1)

    ensure_directories()

    # Импортируем customtkinter после проверки зависимостей
    import customtkinter as ctk

    # Импортируем основное приложение
    from gui import ServiceCenterApp
    from utils.license_manager import LicenseManager

    try:
        print("╔" + "═" * 50 + "╗")
        print("║" + " " * 14 + "ServiceUP v15.0" + " " * 14 + "║")
        print("╠" + "═" * 50 + "╣")
        print("║" + " " * 12 + "УЧЁТ РЕМОНТА ТЕХНИКИ" + " " * 12 + "║")
        print("╚" + "═" * 50 + "╝")
        print()

        # --- Проверка лицензии перед запуском ---
        lic = LicenseManager()
        status = lic.check_license()
        print(f"🔐 Статус лицензии: {status}")

        if status in ("trial_expired", "corrupted") or (
            status == "trial_active" and lic.get_trial_days_left() <= 3
        ):
            # Показываем окно активации (трийал почти истёк или истёк)
            from gui.dialogs.activation_dialog import ActivationDialog

            root = ctk.CTk()
            root.withdraw()
            dialog = ActivationDialog(root, lic)
            root.wait_window(dialog)

            if not lic.is_activated() and status in ("trial_expired", "corrupted"):
                print("❌ Программа не активирована. Завершение.")
                sys.exit(0)
            root.destroy()

        elif status == "trial_active":
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
