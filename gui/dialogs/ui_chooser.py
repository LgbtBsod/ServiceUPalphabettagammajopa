"""Диалог выбора интерфейса при старте приложения.

ServiceUP теперь умеет запускаться в двух оболочках: классической
(customtkinter, gui/) и Flet-браузере (gui_flet/) — второй вариант работает
как локальный веб-сервер и открывается во вкладке браузера, сохраняя тот же
Kernel/Database. Выбор запоминается в service_center.config (ключ ui_mode),
если пользователь отметил чекбокс — иначе диалог показывается на каждом
запуске (main.py читает settings.get("ui_mode") до вызова этого диалога).
"""

from __future__ import annotations

import customtkinter as ctk


class UIChooserDialog(ctk.CTkToplevel):
    """Модальный выбор оболочки. Результат — в self.choice ("classic"/"flet"/None)."""

    def __init__(self, parent, colors: dict[str, str] | None = None):
        super().__init__(parent)
        from utils.colors import get_colors

        self.colors = colors or get_colors("light")
        self.choice: str | None = None
        self.remember = False

        self.title("Выбор интерфейса")
        self.geometry("460x320")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_classic)  # закрытие крестиком = классика

        self.update_idletasks()
        x = (self.winfo_screenwidth() - 460) // 2
        y = (self.winfo_screenheight() - 320) // 2
        self.geometry(f"460x320+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self) -> None:
        c = self.colors
        main = ctk.CTkFrame(self, fg_color=c.get("bg_primary", "#f5f5f7"))
        main.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            main, text="Какой интерфейс открыть?",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(4, 4))
        ctk.CTkLabel(
            main,
            text="Оба работают с одной и той же базой данных.",
            font=ctk.CTkFont(size=12), text_color=c.get("text_secondary", "gray"),
        ).pack(pady=(0, 16))

        ctk.CTkButton(
            main, text="🖥️  Классический интерфейс",
            font=ctk.CTkFont(size=14, weight="bold"), height=48,
            command=self._on_classic,
        ).pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            main, text="Обычное окно приложения (то, что было раньше).",
            font=ctk.CTkFont(size=11), text_color=c.get("text_secondary", "gray"),
        ).pack(pady=(0, 14))

        ctk.CTkButton(
            main, text="🌐  Flet (в браузере)",
            font=ctk.CTkFont(size=14, weight="bold"), height=48,
            fg_color=c.get("success", "#34c759"), hover_color=c.get("success_dark", "#248a3d"),
            command=self._on_flet,
        ).pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            main,
            text="Открывает вкладку браузера с тем же функционалом.",
            font=ctk.CTkFont(size=11), text_color=c.get("text_secondary", "gray"),
        ).pack(pady=(0, 14))

        self.remember_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            main, text="Запомнить выбор и больше не спрашивать",
            variable=self.remember_var,
            font=ctk.CTkFont(size=12),
        ).pack(pady=(4, 0))

    def _on_classic(self) -> None:
        self.choice = "classic"
        self.remember = bool(self.remember_var.get()) if hasattr(self, "remember_var") else False
        self.destroy()

    def _on_flet(self) -> None:
        self.choice = "flet"
        self.remember = bool(self.remember_var.get())
        self.destroy()


def choose_ui_mode(parent, settings, colors: dict[str, str] | None = None) -> str:
    """Возвращает "classic" или "flet". Если settings уже хранит выбор
    (ui_mode != ""), диалог не показывается вообще."""
    remembered = (settings.get("ui_mode") or "").strip()
    if remembered in ("classic", "flet"):
        return remembered

    dialog = UIChooserDialog(parent, colors)
    parent.wait_window(dialog)
    choice = dialog.choice or "classic"
    if dialog.remember:
        settings.set("ui_mode", choice)  # SettingsManager.set() уже сохраняет файл
    return choice


__all__ = ["UIChooserDialog", "choose_ui_mode"]
