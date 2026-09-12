"""Flet-оболочка ServiceUP — второй, браузерный фронт поверх того же ядра
(core.kernel), что и классический customtkinter-интерфейс (gui/).

Выбор оболочки — gui/dialogs/ui_chooser.py, вызывается из main.py."""

from gui_flet.app import run_app

__all__ = ["run_app"]
