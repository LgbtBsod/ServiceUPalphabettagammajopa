"""Update Dialog Module

GUI диалог для показа доступных обновлений пользователю с автоскачиванием.
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk

from config.settings import get_version
from utils.colors import HexColor
from utils.update_manager import download_and_prepare_update, start_update_process


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
            update_info: Информация об обновлении от UpdateManager
            **kwargs: Дополнительные аргументы для CTkToplevel
        """
        super().__init__(parent, **kwargs)
        
        self.update_info = update_info or {}
        self.current_version = self.update_info.get("current_version", get_version())
        self.latest_version = self.update_info.get("latest_version", "0.0")
        self.release_notes = self.update_info.get("release_notes", "")
        self.download_url = self.update_info.get("download_url", "")
        
        # Для автоскачивания - создаем структуру данных для update_manager
        self._update_data = {
            "version": self.latest_version,
            "url": self.download_url,
            "notes": self.release_notes
        }
        
        # Для автоскачивания
        self.temp_path = None
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
            text=f"Текущая версия:",
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
            text=f"Новая версия:",
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
    
    def _progress_callback(self, message: str, percent: int):
        """Обновление прогресса скачивания"""
        self.progress_label.configure(text=message)
        self.progress_bar.set(percent / 100)
        self.update_idletasks()
    
    def _download_thread(self):
        """Поток для скачивания и установки"""
        try:
            # Скачиваем и подготавливаем файлы
            self.temp_path = download_and_prepare_update(
                self._update_data,
                self._progress_callback
            )
            
            if self.temp_path:
                # Запускаем процесс обновления
                self.after(0, lambda: self._start_installation())
            else:
                self.after(0, lambda: self._show_error("Не удалось скачать обновление"))
        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))
    
    def _start_installation(self):
        """Запуск установки после скачивания"""
        self.progress_label.configure(text="Запуск установки...")
        start_update_process(self.temp_path)
        self.destroy()
    
    def _show_error(self, message: str):
        """Показ ошибки"""
        error_label = ctk.CTkLabel(
            self,
            text=f"❌ Ошибка: {message}",
            text_color="#F44336",
            font=ctk.CTkFont(size=12),
        )
        error_label.pack(pady=(0, 10))
        self.download_btn.configure(state="normal")
    
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
