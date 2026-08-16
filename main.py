#!/usr/bin/env python3

"""Сервисный центр - Учет ремонта техники

Версия приложения — единственный источник истины: config.APP_VERSION
(config/settings.py). Не хардкодить номер версии здесь — раньше он был
захардкожен ('15.0') и расходился с реальной версией (см. AUDIT_REPORT_v21.md).
"""

import sys
import warnings

# Точечно (не все категории целиком — раньше это маскировало и полезные
# предупреждения, например о неверном использовании API сторонних
# библиотек, см. AUDIT_REPORT_v21.md): DeprecationWarning от зависимостей
# не actionable для конечного пользователя десктоп-приложения.
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Баннер и сообщения ниже используют emoji/рамки (║╔═╗, ❌, 🔐, 📅...) —
# только UTF-8 их кодирует. start.bat делает chcp 65001 перед запуском, но
# python main.py напрямую (IDE, редиректнутый/пайпнутый stdout, cp1251/cp866
# консоль по умолчанию) наследует locale-кодировку Windows и падает
# UnicodeEncodeError на первом же print() — а except-обработчик ниже сам
# пытался напечатать "❌ ..." и падал ТЕМ ЖЕ образом, эскалируя в необработанное
# исключение вместо задуманного дружелюбного сообщения (см. AUDIT_REPORT_v25.md,
# найдено живым прогоном `python main.py`). reconfigure(..., errors="replace")
# — единственная точка фикса: дальше по модулю можно печатать что угодно,
# несовместимые символы станут "?", а не уронят процесс.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    """Точка входа в приложение"""
    # ==================== ПРОВЕРКА ЗАВИСИМОСТЕЙ ====================
    from bootstrap import check_dependencies, ensure_directories, initialize_kernel

    if not check_dependencies():
        sys.exit(1)

    ensure_directories()

    # Импортируем customtkinter после проверки зависимостей
    import customtkinter as ctk

    # Импортируем основное приложение
    # ВАЖНО: gui импортируется раньше initialize_kernel() — managers/reports
    # содержат predexisting circular import (managers -> reports ->
    # gui.widgets.modern -> gui -> gui.dialogs -> gui.dialogs.device_form ->
    # managers), который триггерится, если managers импортируется до того,
    # как пакет gui полностью инициализирован. См. AUDIT_REPORT_v20.md.
    from gui import ServiceCenterApp
    from utils.license_manager import LicenseManager

    # Kernel — единая точка сборки зависимостей (Database, менеджеры) для
    # gui/main_window.py и pwa/server.py.
    initialize_kernel()

    from config import APP_VERSION

    try:
        title = f"ServiceUP v{APP_VERSION}"
        subtitle = "УЧЁТ РЕМОНТА ТЕХНИКИ"
        width = 50
        print("╔" + "═" * width + "╗")
        print("║" + title.center(width) + "║")
        print("╠" + "═" * width + "╣")
        print("║" + subtitle.center(width) + "║")
        print("╚" + "═" * width + "╝")
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
