"""Update Dialog Module

GUI диалог для показа доступных обновлений пользователю с автоскачиванием.

Раньше скачивание шло через download_and_prepare_update() + отдельный
процесс apply_update.py (start_update_process) — два независимых шага без
проверки контрольной суммы и без бэкапа. Теперь AutoUpdater.download_update()
сам делает всё: бэкап -> скачивание с прогрессом -> проверка SHA256 ->
установка (frozen: подмена .exe + перезапуск нового процесса; из исходников:
copytree поверх + version.txt) -> откат при ошибке.
"""

from __future__ import annotations

import sys
import threading
from typing import Any

import customtkinter as ctk

from config.settings import get_version
from utils.update_manager import AutoUpdater, DownloadProgress


class UpdateDialog(ctk.CTkToplevel):
    """Диалог обновления приложения

    Показывает информацию о новой версии и предлагает скачать обновление.
    Поддерживает тихое скачивание и автоматическую установку.
    """

    def __init__(
        self,
        parent: ctk.CTkBaseClass | None = None,
        update_info: dict[str, Any] | None = None,
        **kwargs
    ):
        """Инициализация диалога обновления

        Args:
            parent: Родительское окно
            update_info: Информация об обновлении (см. utils.update_manager.check_updates_at_startup)
            **kwargs: Дополнительные аргументы для CTkToplevel
        """
        super().__init__(parent, **kwargs)

        self.update_info = update_info or {}
        self.current_version = self.update_info.get("current_version", get_version())
        self.latest_version = self.update_info.get("latest_version", "0.0")
        self.release_notes = self.update_info.get("release_notes", "")
        self.download_url = self.update_info.get("download_url", "")

        self.is_downloading = False

        # Настройка окна
        self.title("Доступно обновление")
        self.geometry("500x450")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()  # Модальное окно

        # Центрирование окна
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 450) // 2
        self.geometry(f"500x450+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self) -> None:
        """Создание виджетов диалога"""
        # Основной фрейм с отступами
        main_frame = ctk.CTkFrame(self, corner_radius=0)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Заголовок
        title_label = ctk.CTkLabel(
            main_frame,
            text="✨ Доступна новая версия!",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_label.pack(pady=(0, 10))

        # Информация о версиях
        version_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        version_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            version_frame,
            text="Текущая версия:",
            font=ctk.CTkFont(size=14),
        ).pack(anchor="w")

        ctk.CTkLabel(
            version_frame,
            text=f"  {self.current_version}",
            font=ctk.CTkFont(size=14, slant="italic"),
            text_color="gray",
        ).pack(anchor="w", padx=20)

        ctk.CTkLabel(
            version_frame,
            text="Новая версия:",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", pady=(10, 0))

        ctk.CTkLabel(
            version_frame,
            text=f"  {self.latest_version}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#4CAF50",  # Зеленый цвет
        ).pack(anchor="w", padx=20)

        # Заметки о релизе
        if self.release_notes:
            notes_label = ctk.CTkLabel(
                main_frame,
                text="📋 Что нового:",
                font=ctk.CTkFont(size=14, weight="bold"),
            )
            notes_label.pack(anchor="w", pady=(15, 5))

            # Текст заметок с прокруткой если длинный
            notes_text = ctk.CTkTextbox(
                main_frame,
                height=100,
                wrap="word",
                state="disabled",
            )
            notes_text.pack(fill="x", pady=5)
            notes_text.insert("0.0", self.release_notes[:500])  # Ограничиваем длину
            notes_text.configure(state="disabled")

        # Прогресс бар (скрыт по умолчанию)
        self.progress_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.progress_bar = ctk.CTkProgressBar(main_frame, mode="determinate")
        self.progress_bar.set(0)
        self.progress_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#2196F3",
        )

        # Кнопки
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(20, 0))

        # Кнопка "Скачать и установить"
        self.download_btn = ctk.CTkButton(
            button_frame,
            text="⬇️ Скачать и установить",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            command=self._on_download,
        )
        self.download_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Кнопка "Позже"
        later_btn = ctk.CTkButton(
            button_frame,
            text="⏭️ Позже",
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color="transparent",
            border_width=2,
            command=self._on_later,
        )
        later_btn.pack(side="left", fill="x", expand=True, padx=(10, 0))

    def _progress_callback(self, progress: DownloadProgress) -> None:
        """Колбэк AutoUpdater — вызывается из ФОНОВОГО потока загрузки.

        Раньше здесь напрямую трогались виджеты (configure/set/update_idletasks)
        из не-Tk потока — customtkinter/Tk не потокобезопасны, это гонка,
        которая на практике то тормозит, то роняет интерфейс необъяснимо
        редким образом. self.after(0, ...) передаёт обновление в Tk-поток."""
        text = f"{progress.percent:.0f}%   {progress.formatted_speed}" if progress.total_bytes else (
            f"{progress.bytes_downloaded // 1024} КБ"
        )
        value = progress.percent / 100 if progress.total_bytes else 0
        self.after(0, lambda: self._apply_progress(text, value))

    def _apply_progress(self, text: str, value: float) -> None:
        self.progress_label.configure(text=text)
        self.progress_bar.set(value)

    def _download_thread(self) -> None:
        """Поток для скачивания и установки."""
        updater = AutoUpdater(current_version=self.current_version)
        updater.progress_callback = self._progress_callback
        try:
            ok = updater.download_update(self.download_url, self.latest_version)
        except Exception as e:
            self.after(0, lambda err=e: self._show_error(str(err)))
            return
        if ok:
            self.after(0, lambda: self._on_installed(updater.is_frozen))
        else:
            self.after(0, lambda: self._show_error("Не удалось установить обновление"))

    def _on_installed(self, was_frozen: bool) -> None:
        """Обновление установлено — сообщаем и завершаем процесс.

        Frozen: AutoUpdater уже подменил .exe и запустил НОВЫЙ процесс
        (см. _relaunch_after_update) — этому, старому, остаётся только выйти,
        иначе оба будут держать файлы/порт PWA одновременно. Из исходников:
        файлы скопированы на месте, но текущий процесс их уже импортировал —
        нужен ручной перезапуск, поэтому просто просим пользователя."""
        if was_frozen:
            self.progress_label.configure(text="Установлено — перезапуск...")
            self.update_idletasks()
            self.after(800, os_exit_now)
        else:
            self.progress_label.configure(text="Установлено. Перезапустите приложение вручную.")
            self.download_btn.configure(state="disabled", text="Готово")

    def _show_error(self, message: str):
        """Показ ошибки"""
        error_label = ctk.CTkLabel(
            self,
            text=f"❌ Ошибка: {message}",
            text_color="#F44336",
            font=ctk.CTkFont(size=12),
        )
        error_label.pack(pady=(0, 10))
        self.download_btn.configure(state="normal", text="⬇️ Скачать и установить")
        self.is_downloading = False

    def _on_download(self) -> None:
        """Обработчик кнопки скачивания"""
        if self.is_downloading:
            return

        self.is_downloading = True
        self.download_btn.configure(state="disabled", text="⏳ Загрузка...")

        # Показываем прогресс
        self.progress_frame.pack(fill="x", pady=(10, 0))
        self.progress_bar.pack(fill="x", pady=5)
        self.progress_label.pack(pady=(0, 10))

        # Запускаем в отдельном потоке
        thread = threading.Thread(target=self._download_thread, daemon=True)
        thread.start()

    def _on_later(self) -> None:
        """Обработчик кнопки 'Позже'"""
        self.destroy()


def os_exit_now() -> None:
    """Немедленный выход без cleanup — новый процесс (после подмены .exe)
    уже запущен отдельно, старому здесь больше нечего делать корректно
    закрывать (GUI-обработчики закрытия окна тут неприменимы)."""
    sys.stdout.flush()
    sys.stderr.flush()
    import os

    os._exit(0)


def show_update_dialog(
    parent: ctk.CTkBaseClass | None,
    update_info: dict[str, Any],
) -> bool:
    """Показать диалог обновления

    Args:
        parent: Родительское окно
        update_info: Информация об обновлении

    Returns:
        bool: True если пользователь нажал "Скачать", False если "Позже"
    """
    if not update_info.get("has_update"):
        return False

    dialog = UpdateDialog(parent, update_info)
    dialog.wait_window()  # Ждем закрытия диалога

    return True


# Export public API
__all__ = ["UpdateDialog", "show_update_dialog"]
