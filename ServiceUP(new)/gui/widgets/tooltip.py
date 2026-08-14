#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Простые tooltips (всплывающие подсказки) для виджетов Tkinter/customtkinter."""


class ToolTip:
    """Всплывающая подсказка при наведении на виджет."""

    def __init__(self, widget, text: str, delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay  # мс до показа
        self._tip_window = None
        self._after_id = None

        self.widget.bind("<Enter>", self._schedule, add="+")
        self.widget.bind("<Leave>", self._hide, add="+")

    def _schedule(self, event=None):
        self._hide()
        self._after_id = self.widget.after(self.delay, self._show)

    def _show(self, event=None):
        if self._tip_window or not self.text:
            return
        try:
            import tkinter as tk
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

            self._tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")

            label = tk.Label(tw, text=self.text, justify="left",
                             background="#1c1c1e", foreground="#ffffff",
                             relief="solid", borderwidth=0,
                             font=("Segoe UI", 10), padx=8, pady=4)
            label.pack()
        except Exception:
            pass

    def _hide(self, event=None):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._tip_window:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None


def create_tooltip(widget, text: str, delay: int = 500) -> ToolTip:
    """Создаёт tooltip для виджета. Возвращает объект ToolTip."""
    return ToolTip(widget, text, delay)
