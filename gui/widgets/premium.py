#!/usr/bin/env python3

"""Премиум виджеты для интерфейса (стиль macOS).

Теперь `Premium*` — тонкие алиасы поверх Modern* с эффектом подсветки
границы при наведении (как в macOS Settings).
"""

import contextlib

import customtkinter as ctk


class PremiumCard(ctk.CTkFrame):
    """Карточка с подсветкой границы при наведении (hover-glow эффект)"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        kwargs.pop("fg_color", None)
        super().__init__(
            master,
            fg_color=colors["bg_card"],
            corner_radius=10,
            border_width=1,
            border_color=colors.get("border_light", colors.get("border", "#e5e5ea")),
            **kwargs,
        )
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)

    def on_enter(self, e):
        with contextlib.suppress(Exception):
            self.configure(border_color=self.colors["accent"])

    def on_leave(self, e):
        with contextlib.suppress(Exception):
            self.configure(
                border_color=self.colors.get(
                    "border_light", self.colors.get("border", "#e5e5ea")
                )
            )


class PremiumButton(ctk.CTkButton):
    """Кнопка в стиле macOS"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        kwargs.pop("fg_color", None)
        kwargs.pop("hover_color", None)
        kwargs.pop("text_color", None)
        super().__init__(
            master,
            fg_color=colors["accent"],
            hover_color=colors["accent_hover"],
            text_color="white",
            corner_radius=8,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            **kwargs,
        )


class PremiumEntry(ctk.CTkEntry):
    """Поле ввода в стиле macOS"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        kwargs.pop("fg_color", None)
        kwargs.pop("text_color", None)
        kwargs.pop("border_color", None)
        super().__init__(
            master,
            fg_color=colors["bg_tertiary"],
            text_color=colors["text_primary"],
            border_color=colors["border"],
            border_width=1,
            corner_radius=8,
            height=34,
            font=ctk.CTkFont(size=13),
            **kwargs,
        )


class PremiumLabel(ctk.CTkLabel):
    """Метка в стиле macOS"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        kwargs.pop("text_color", None)
        font = kwargs.pop("font", ctk.CTkFont(size=13))
        super().__init__(master, font=font, text_color=colors["text_primary"], **kwargs)


class PremiumCombobox(ctk.CTkComboBox):
    """Выпадающий список в стиле macOS"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        kwargs.pop("fg_color", None)
        kwargs.pop("text_color", None)
        kwargs.pop("border_color", None)
        super().__init__(
            master,
            fg_color=colors["bg_tertiary"],
            text_color=colors["text_primary"],
            border_color=colors["border"],
            border_width=1,
            corner_radius=8,
            height=34,
            font=ctk.CTkFont(size=13),
            dropdown_fg_color=colors["bg_secondary"],
            dropdown_hover_color=colors["hover"],
            dropdown_text_color=colors["text_primary"],
            button_color=colors["accent"],
            button_hover_color=colors["accent_hover"],
            **kwargs,
        )
