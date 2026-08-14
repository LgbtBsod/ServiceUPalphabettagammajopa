#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Современные виджеты в едином стиле macOS.

Особенности:
- Большие скругления (corner_radius) как у контролов macOS.
- Полупрозрачные/матовые фоны для vibrancy.
- Аккуратные отступы и типографика (San Francisco-подобные шрифты).
"""

import customtkinter as ctk


# Базовый размер скругления контролов macOS
_CORNER = 10
_CORNER_INPUT = 8


class ModernCard(ctk.CTkFrame):
    """Карточка с закругленными углами (стиль macOS «grouped» карточки)"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        corner_radius = kwargs.pop('corner_radius', _CORNER)
        kwargs.pop('fg_color', None)
        super().__init__(
            master,
            fg_color=colors['bg_card'],
            corner_radius=corner_radius,
            border_width=1,
            border_color=colors.get('border_light', colors.get('border', '#e5e5ea')),
            **kwargs
        )


class ModernButton(ctk.CTkButton):
    """Кнопка в стиле macOS (аппл-подобная)"""

    def __init__(self, master, colors, variant="primary", **kwargs):
        self.colors = colors

        height = kwargs.pop('height', 34)
        width = kwargs.pop('width', None)
        text = kwargs.pop('text', "")
        command = kwargs.pop('command', None)

        # customtkinter падает при width=None (TypeError в scaling),
        # поэтому собираем kwargs явно и передаём width только если он задан.
        button_kwargs = dict(
            text=text,
            command=command,
            height=height,
        )
        if width is not None:
            button_kwargs['width'] = width

        if variant == "primary":
            button_kwargs.update(fg_color=colors['accent'], hover_color=colors['accent_hover'],
                                 text_color="white", border_width=0, border_color=None)
        elif variant == "secondary":
            button_kwargs.update(fg_color=colors['bg_tertiary'], hover_color=colors['bg_hover'],
                                 text_color=colors['text_primary'], border_width=0, border_color=None)
        elif variant == "success":
            button_kwargs.update(fg_color=colors['success'], hover_color=colors['success_dark'],
                                 text_color="white", border_width=0, border_color=None)
        elif variant == "danger":
            button_kwargs.update(fg_color=colors['error'], hover_color=colors['error_dark'],
                                 text_color="white", border_width=0, border_color=None)
        else:  # outline
            button_kwargs.update(fg_color="transparent", hover_color=colors['bg_hover'],
                                 text_color=colors['text_primary'], border_width=1,
                                 border_color=colors.get('border', '#d2d2d7'))

        button_kwargs.update(
            corner_radius=_CORNER_INPUT,
            font=ctk.CTkFont(size=13),
        )
        super().__init__(master, **button_kwargs, **kwargs)


class ModernEntry(ctk.CTkEntry):
    """Поле ввода в стиле macOS (матовый серый фон)"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        height = kwargs.pop('height', 34)
        super().__init__(
            master,
            fg_color=colors['bg_tertiary'],
            text_color=colors['text_primary'],
            border_color=colors['border'],
            border_width=1,
            corner_radius=_CORNER_INPUT,
            height=height,
            font=ctk.CTkFont(size=13),
            **kwargs
        )


class ModernLabel(ctk.CTkLabel):
    """Метка в стиле macOS"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        text_color = kwargs.pop('text_color', colors['text_primary'])
        font = kwargs.pop('font', ctk.CTkFont(size=13))
        super().__init__(master, text_color=text_color, font=font, **kwargs)


class ModernCombobox(ctk.CTkComboBox):
    """Выпадающий список в стиле macOS"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        height = kwargs.pop('height', 34)
        width = kwargs.pop('width', None)
        values = kwargs.pop('values', [])

        super().__init__(
            master,
            values=values,
            fg_color=colors['bg_tertiary'],
            text_color=colors['text_primary'],
            border_color=colors['border'],
            border_width=1,
            corner_radius=_CORNER_INPUT,
            height=height,
            width=width,
            font=ctk.CTkFont(size=13),
            dropdown_fg_color=colors['bg_secondary'],
            dropdown_hover_color=colors['bg_hover'],
            dropdown_text_color=colors['text_primary'],
            button_color=colors['bg_tertiary'],
            button_hover_color=colors['bg_hover'],
            state="readonly",
            **kwargs
        )


class ModernTextbox(ctk.CTkTextbox):
    """Текстовое поле в стиле macOS"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        height = kwargs.pop('height', 100)
        super().__init__(
            master,
            fg_color=colors['bg_tertiary'],
            text_color=colors['text_primary'],
            border_color=colors['border'],
            border_width=1,
            corner_radius=_CORNER_INPUT,
            height=height,
            font=ctk.CTkFont(size=13),
            **kwargs
        )


class ModernCheckbox(ctk.CTkCheckBox):
    """Чекбокс в стиле macOS"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        super().__init__(
            master,
            fg_color=colors['accent'],
            hover_color=colors['accent_hover'],
            border_color=colors['border'],
            text_color=colors['text_primary'],
            font=ctk.CTkFont(size=13),
            corner_radius=6,
            **kwargs
        )


class ModernSwitch(ctk.CTkSwitch):
    """Переключатель в стиле macOS (тоггл)"""

    def __init__(self, master, colors, **kwargs):
        self.colors = colors
        super().__init__(
            master,
            fg_color=colors['bg_hover'],
            progress_color=colors['accent'],
            button_color="white",
            button_hover_color=colors['bg_hover'],
            text_color=colors['text_primary'],
            font=ctk.CTkFont(size=13),
            corner_radius=15,
            **kwargs
        )
