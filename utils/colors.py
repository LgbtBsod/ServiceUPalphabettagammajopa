#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Единая цветовая схема в стиле macOS.

Поддерживает светлую и тёмную темы с полупрозрачными фонами (vibrancy),
которые работают вместе с utils/window_effects.py (Acrylic/Mica на Windows,
нативная прозрачность на macOS).
"""


# Полупрозрачные фоны для эффекта vibrancy (прозрачность окна).
# Эти значения используются как fg_color контейнеров поверх прозрачного окна.
def _light_palette(accent_color):
    return {
        # Основные цвета — macOS light
        'bg_primary': '#f5f5f7',       # серый фон как в macOS
        'bg_secondary': '#ffffff',     # карточки
        'bg_tertiary': '#ececef',      # поля ввода / tertiary
        'bg_card': '#ffffff',          # карточки
        'bg_hover': '#e5e5ea',
        'hover': '#e5e5ea',

        # Полупрозрачные версии для vibrancy (когда окно прозрачное)
        # alpha в hex (#RRGGBBAA) — customtkinter/Tk поддерживает через tkhtml,
        # но безопаснее использовать как есть; окно само даёт размытый фон.
        'bg_primary_translucent': '#f5f5f7',
        'bg_secondary_translucent': '#fbfbfd',
        'bg_card_translucent': '#fcfcfe',

        # Акцентные цвета (как системные акценты macOS)
        'accent': accent_color,
        'accent_light': '#e8f0fe',
        'accent_hover': '#0a84ff',     # macOS blue pressed
        'accent_muted': '#d4e6f1',

        # Текст
        'text_primary': '#1d1d1f',     # macOS primary label
        'text_secondary': '#6e6e73',   # secondary label
        'text_tertiary': '#8e8e93',    # tertiary label
        'text_muted': '#aeaeb2',

        # Границы / сепараторы (macOS separator)
        'border': '#d2d2d7',
        'border_light': '#e5e5ea',
        'separator': '#e5e5ea',

        # Цвета статусов (приглушённые, в духе macOS)
        'success': '#34c759',          # macOS green
        'success_light': '#e8f9ee',
        'success_dark': '#248a3d',

        'warning': '#ff9f0a',          # macOS orange
        'warning_light': '#fff4e0',
        'warning_dark': '#c93400',

        'error': '#ff3b30',            # macOS red
        'error_light': '#ffecec',
        'error_dark': '#d70015',

        'info': '#007aff',             # macOS blue
        'info_light': '#e6f2ff',
        'info_dark': '#004cb3',

        # Специальные
        'urgent': '#ff453a',
        'urgent_light': '#ffefed',
        'normal_light': '#eafaf0',
    }


def _dark_palette(accent_color):
    return {
        # Основные цвета — macOS dark
        'bg_primary': '#1c1c1e',       # фон окна
        'bg_secondary': '#2c2c2e',     # карточки
        'bg_tertiary': '#3a3a3c',      # tertiary / inputs
        'bg_card': '#2c2c2e',
        'bg_hover': '#48484a',
        'hover': '#48484a',

        'bg_primary_translucent': '#1c1c1e',
        'bg_secondary_translucent': '#2c2c2eff',
        'bg_card_translucent': '#2c2c2eff',

        # Акцентные
        'accent': accent_color,
        'accent_light': '#0a3d62',
        'accent_hover': '#0a84ff',
        'accent_muted': '#1c3a5a',

        # Текст
        'text_primary': '#ffffff',
        'text_secondary': '#ebebf5',   # 60% opacity white на macOS
        'text_tertiary': '#9a9aa0',
        'text_muted': '#636366',

        # Границы
        'border': '#38383a',
        'border_light': '#48484a',
        'separator': '#38383a',

        # Статусы
        'success': '#30d158',
        'success_light': '#1e3a24',
        'success_dark': '#248a3d',

        'warning': '#ff9f0a',
        'warning_light': '#3a2e16',
        'warning_dark': '#c93400',

        'error': '#ff453a',
        'error_light': '#3a1e1e',
        'error_dark': '#d70015',

        'info': '#0a84ff',
        'info_light': '#1a2a3a',
        'info_dark': '#004cb3',

        # Специальные
        'urgent': '#ff453a',
        'urgent_light': '#3a1e1e',
        'normal_light': '#1e3a24',
    }


def get_colors(theme="light", accent_color="#007aff"):
    """Получение цветовой схемы в стиле macOS"""
    if theme == "dark":
        return _dark_palette(accent_color)
    return _light_palette(accent_color)
