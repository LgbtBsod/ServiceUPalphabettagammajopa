#!/usr/bin/env python3

"""Премиум виджеты для интерфейса (стиль macOS).

`Premium*` — РЕАЛЬНО тонкие подклассы `Modern*` (gui/widgets/modern.py),
как и было заявлено в докстринге, но раньше не было правдой: каждый класс
независимо копировал вёрстку Modern*, из-за чего они начали расходиться
(button_color/button_hover_color у PremiumCombobox, отсутствие variant у
PremiumButton — см. AUDIT_REPORT_v21.md). Единственное реальное отличие
Premium* от Modern* — hover-glow эффект у PremiumCard.
"""

import contextlib

from gui.widgets.modern import (
    ModernButton,
    ModernCard,
    ModernCombobox,
    ModernEntry,
    ModernLabel,
)


class PremiumCard(ModernCard):
    """Карточка с подсветкой границы при наведении (hover-glow эффект) —
    единственное реальное отличие от ModernCard."""

    def __init__(self, master, colors, **kwargs):
        super().__init__(master, colors, **kwargs)
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


class PremiumButton(ModernButton):
    """Кнопка в стиле macOS — тонкий алиас ModernButton (по умолчанию
    variant='primary', т.е. акцентная заливка, как было у старой PremiumButton)."""

    def __init__(self, master, colors, **kwargs):
        kwargs.setdefault("variant", "primary")
        super().__init__(master, colors, **kwargs)


class PremiumEntry(ModernEntry):
    """Поле ввода в стиле macOS — тонкий алиас ModernEntry."""


class PremiumLabel(ModernLabel):
    """Метка в стиле macOS — тонкий алиас ModernLabel."""


class PremiumCombobox(ModernCombobox):
    """Выпадающий список в стиле macOS — тонкий алиас ModernCombobox с
    акцентной (не серой) кнопкой раскрытия, как было у старой PremiumCombobox."""

    def __init__(self, master, colors, **kwargs):
        kwargs.setdefault("button_color", colors["accent"])
        kwargs.setdefault("button_hover_color", colors["accent_hover"])
        super().__init__(master, colors, **kwargs)
