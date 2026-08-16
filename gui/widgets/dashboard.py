#!/usr/bin/env python3

"""Компактный дашборд с аналитикой.

Полоса из 4 показателей: Всего / В ремонте / Готовы / Просрочены.
Клик по «Просрочены» фильтрует таблицу (callback on_overdue_click).
"""

import logging

import customtkinter as ctk

from gui.widgets.premium import PremiumCard

logger = logging.getLogger(__name__)


class PremiumDashboard(PremiumCard):
    """Компактный дашборд с аналитикой"""

    def __init__(self, master, db, colors, settings=None, on_overdue_click=None, **kwargs):
        self.db = db
        self.colors = colors
        self.settings = settings
        self.on_overdue_click = on_overdue_click  # callback клика по «Просрочены»
        super().__init__(master, colors, **kwargs)
        self.stats_cards = {}
        self.create_widgets()

    def create_widgets(self):
        """Создание виджетов дашборда — компактная полоса."""
        # Заголовок убран для компактности, показатели идут напрямую

        self.stats_container = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_container.pack(fill="x", padx=8, pady=4)

        # 4 компактных показателя в одну строку
        stats_items = [
            ("total", "Всего", "📦", self.colors["accent"], False),
            ("in_repair", "В ремонте", "🔧", self.colors["warning"], False),
            ("ready", "Готовы", "✅", self.colors["success"], False),
            ("overdue", "Просроч.", "⏰", self.colors.get("error", "#ff3b30"), True),
        ]

        for i, (key, label, icon, color, is_clickable) in enumerate(stats_items):
            card = ctk.CTkFrame(
                self.stats_container,
                fg_color=self.colors["bg_tertiary"],
                corner_radius=8,
                height=44,
            )
            card.grid(row=0, column=i, padx=3, pady=2, sticky="nsew")
            card.pack_propagate(False)

            # Иконка + значение в одну строку (компактно)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(expand=True)

            icon_lbl = ctk.CTkLabel(
                inner, text=icon, font=ctk.CTkFont(size=16), text_color=color
            )
            icon_lbl.pack(side="left", padx=(8, 4))

            value_lbl = ctk.CTkLabel(
                inner,
                text="0",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=color,
            )
            value_lbl.pack(side="left", padx=(0, 4))

            name_lbl = ctk.CTkLabel(
                inner,
                text=label,
                font=ctk.CTkFont(size=10),
                text_color=self.colors["text_secondary"],
            )
            name_lbl.pack(side="left", padx=(0, 8))

            self.stats_cards[key] = value_lbl

            # Кликабельная карточка «Просрочены»
            if is_clickable:
                card.configure(cursor="hand2")
                card.bind("<Button-1>", lambda e: self._on_card_click())
                for child in card.winfo_children():
                    child.bind("<Button-1>", lambda e: self._on_card_click())
                    for sub in child.winfo_children():
                        sub.bind("<Button-1>", lambda e: self._on_card_click())

        for i in range(4):
            self.stats_container.grid_columnconfigure(i, weight=1)

    def _on_card_click(self):
        """Обработчик клика по карточке «Просрочены»."""
        if self.on_overdue_click:
            self.on_overdue_click()

    def update_stats(self):
        """Обновление статистики, включая просроченные заказы.

        НЕ кэшируется — сознательное решение, не недосмотр. Измерено на 3000
        устройств: полный пересчёт (get_statistics()+calculate('overdue_count'))
        занимает ~2.8ms, а проверка "не изменились ли данные" (был реализован
        вариант через COUNT+MAX(updated_at), см. database.sqlalchemy_database.
        Database.get_table_generation()) — ~1ms. Экономия при валидном кэше
        человеком не ощущается (<2ms), а update_stats() зовётся сразу ПОСЛЕ
        CRUD-операции (main_window.py, 7+ мест) — то есть кэш почти всегда
        невалиден в момент вызова, и тогда проверка добавляет накладные
        расходы вместо экономии. Преждевременная оптимизация несуществующей
        на этом масштабе проблемы — убрано после измерения, см. историю сессии."""
        threshold = self.settings.get("overdue_days", 14) if self.settings else 14
        stats = self.db.get_statistics()
        try:
            overdue = self.db.calculate("overdue_count", threshold_days=threshold)
        except Exception as e:
            logger.error(f"Ошибка подсчёта просроченных заказов: {e}", exc_info=True)
            overdue = 0

        for key in ("total", "in_repair", "ready"):
            if key in self.stats_cards:
                self.stats_cards[key].configure(text=str(stats.get(key, 0)))
        if "overdue" in self.stats_cards:
            self.stats_cards["overdue"].configure(text=str(overdue))
