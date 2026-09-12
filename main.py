#!/usr/bin/env python3

"""Сервисный центр - Учет ремонта техники

Версия приложения — единственный источник истины: config.APP_VERSION
(config/settings.py). Не хардкодить номер версии здесь — раньше он был
захардкожен ('15.0') и расходился с реальной версией (см. AUDIT_REPORT_v21.md).
"""

import contextlib
import sys
import time
import warnings
from pathlib import Path

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
        with contextlib.suppress(Exception):
            _stream.reconfigure(encoding="utf-8", errors="replace")


_HELP = """ServiceUP — учёт ремонта техники

  --version        показать версию и выйти
  --help, -h       эта справка
  --no-update      (frozen) не проверять обновления на этом запуске
  --ui=classic     запустить классический интерфейс (customtkinter), без диалога выбора
  --ui=flet        запустить Flet-интерфейс (браузер), без диалога выбора
"""


def _finish_pending_update() -> bool:
    """Frozen only: файл ``<exe>.updated`` рядом с нами означает, что
    self-update скачал новый бинарник, но подмена могла не завершиться (крэш
    между скачиванием и swap, антивирус придержал файл и т.п.). Если
    staged-файл существует — отдаём его свежему AutoUpdater на до-установку и
    выходим; иначе чистим мусор. Возвращает True, если процесс должен выйти
    (перезапуск уже запущен)."""
    if not getattr(sys, "frozen", False):
        return False
    exe = Path(sys.executable).resolve()
    staged = exe.with_name(exe.name + ".updated")
    if not staged.is_file():
        return False
    try:
        from utils.update_manager import AutoUpdater

        AutoUpdater()._relaunch_after_update()
        return True
    except Exception as e:
        print(f"⚠️ Не удалось завершить отложенное обновление: {e}")
        with contextlib.suppress(OSError):
            staged.unlink()
        return False


def _cleanup_update_leftovers() -> None:
    """Frozen only: удаляет ``<exe>.old``, оставленный предыдущей подменой
    бинарника (utils/update_manager.AutoUpdater._swap_windows_binary)."""
    if not getattr(sys, "frozen", False):
        return
    exe = Path(sys.executable).resolve()
    old = exe.with_name(exe.name + ".old")
    for attempt in range(3):
        try:
            if old.exists():
                old.unlink()
            break
        except OSError:
            time.sleep(0.3 * (attempt + 1))


def main():
    """Точка входа в приложение"""
    args = sys.argv[1:]
    if "--version" in args:
        from config import APP_VERSION

        print(APP_VERSION)
        return
    if "--help" in args or "-h" in args:
        print(_HELP)
        return

    # ==================== ПРОВЕРКА ЗАВИСИМОСТЕЙ ====================
    from bootstrap import check_dependencies, ensure_directories, initialize_kernel

    if not check_dependencies():
        sys.exit(1)

    ensure_directories()

    if _finish_pending_update():
        print("⏳ Отложенное обновление передано свежему процессу — выходим.")
        return
    _cleanup_update_leftovers()

    # Импортируем customtkinter после проверки зависимостей
    import customtkinter as ctk

    # ==================== ПРОВЕРКА ОБНОВЛЕНИЙ ====================
    # Проверяем обновления перед инициализацией ядра и запуском GUI.
    # --no-update: после self-update relaunch (см. AutoUpdater._relaunch_*)
    # свежий процесс не должен сразу же снова себя обновлять.
    update_result = None
    if "--no-update" not in args:
        try:
            from utils.update_manager import check_updates_at_startup
            update_result = check_updates_at_startup()
        except Exception as e:
            print(f"⚠️ Не удалось проверить обновления: {e}")
    # ============================================================

    # Импортируем основное приложение
    # ВАЖНО: gui импортируется раньше initialize_kernel() — managers/reports
    # содержат predexisting circular import (managers -> reports ->
    # gui.widgets.modern -> gui -> gui.dialogs -> gui.dialogs.device_form ->
    # managers), который триггерится, если managers импортируется до того,
    # как пакет gui полностью инициализирован. См. AUDIT_REPORT_v20.md.
    from gui import ServiceCenterApp
    from utils.license_manager import LicenseManager

    # Kernel — единая точка сборки зависимостей (Database, менеджеры) для
    # gui/main_window.py, gui_flet/app.py и pwa/server.py.
    core = initialize_kernel()

    ui_override = next((a.split("=", 1)[1] for a in args if a.startswith("--ui=")), None)

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

        # --- Показываем диалог обновления если есть новая версия ---
        if update_result and update_result.get("has_update"):
            try:
                from gui.dialogs.update_dialog import show_update_dialog

                # Создаем временное окно для диалога обновлений
                temp_root = ctk.CTk()
                temp_root.withdraw()
                show_update_dialog(temp_root, update_result)
                temp_root.destroy()
            except Exception as e:
                print(f"⚠️ Не удалось показать диалог обновления: {e}")

        # --- Выбор оболочки (классический интерфейс / Flet-браузер) ---
        ui_mode = ui_override
        if ui_mode not in ("classic", "flet"):
            settings_api = core.get_module_api("settings")
            from gui.dialogs.ui_chooser import choose_ui_mode
            from utils.colors import get_colors

            chooser_root = ctk.CTk()
            chooser_root.withdraw()
            ui_mode = choose_ui_mode(
                chooser_root, settings_api,
                get_colors(settings_api.get("theme", "light")),
            )
            chooser_root.destroy()

        if ui_mode == "flet":
            print("🌐 Запуск Flet-интерфейса (браузер)...")
            from gui_flet import run_app as run_flet_app

            run_flet_app(core)
        else:
            # --- Запуск классического интерфейса ---
            app = ServiceCenterApp()
            app.run()

    except KeyboardInterrupt:
        print("\n👋 Программа завершена")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
        # sys.stdin.isatty(): в frozen --windowed сборке консоли нет вообще
        # (stdin — не просто "не терминал", а зачастую None/недоступен) —
        # input() там сразу падал EOFError/TypeError, ЗАМЕНЯЯ настоящую
        # трассировку выше на невнятную вторую ошибку вместо паузы для чтения.
        if sys.stdin is not None and sys.stdin.isatty():
            with contextlib.suppress(EOFError, OSError):
                input("\nНажмите Enter для выхода...")
        sys.exit(1)


if __name__ == "__main__":
    main()
