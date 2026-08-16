#!/usr/bin/env python3
"""FinanceMixin — вкладка "Финансы" главного окна: сводка, таблица
завершённых заказов, редактирование расхода. См. AUDIT_REPORT_v25.md,
Task T (перенесено из main_window.py без изменения поведения).

update_finance_display() идёт через AsyncLoadMixin (Task O) — запрос к БД
выполняется в фоновом потоке, таблицу на время загрузки закрывает
LoadingOverlay вместо замирания GUI."""

from __future__ import annotations

import logging
from tkinter import messagebox, ttk

import customtkinter as ctk

from gui.widgets import ModernCard
from gui.widgets.skeleton import LoadingOverlay
from utils.formatters import format_date, format_order_number_for_db, format_order_number_for_display, format_price
from utils.messages import Msg

logger = logging.getLogger(__name__)


class FinanceMixin:
    """Требует от финального класса ServiceCenterApp: self.db, self.colors,
    self.root, self._core (для фоновой загрузки, AsyncLoadMixin)."""

    def create_finance_tab(self, parent):
        """Создание вкладки финансов"""
        # Карточка со сводкой
        summary_card = ModernCard(parent, self.colors)
        summary_card.pack(fill="x", pady=(0, 10))

        summary_frame = ctk.CTkFrame(summary_card, fg_color="transparent")
        summary_frame.pack(fill="x", padx=15, pady=10)

        # Кнопки периодов
        period_frame = ctk.CTkFrame(summary_frame, fg_color="transparent")
        period_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            period_frame, text="Период:", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 10))

        self.period_var = ctk.StringVar(value="all")
        periods = [("Все время", "all"), ("Неделя", "week"), ("Месяц", "month")]

        for text, value in periods:
            btn = ctk.CTkRadioButton(
                period_frame,
                text=text,
                variable=self.period_var,
                value=value,
                command=self.update_finance_display,
                fg_color=self.colors["accent"],
            )
            btn.pack(side="left", padx=5)

        # Карточка со статистикой
        stats_frame = ctk.CTkFrame(summary_frame, fg_color="transparent")
        stats_frame.pack(fill="x")

        self.income_label = ctk.CTkLabel(
            stats_frame,
            text="💰 Доход: 0 ₽",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["success"],
        )
        self.income_label.pack(side="left", padx=(0, 20))

        self.expense_label = ctk.CTkLabel(
            stats_frame,
            text="💸 Расход: 0 ₽",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["error"],
        )
        self.expense_label.pack(side="left", padx=(0, 20))

        self.profit_label = ctk.CTkLabel(
            stats_frame,
            text="📈 Прибыль: 0 ₽",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        )
        self.profit_label.pack(side="left")

        # Таблица финансов
        table_card = ModernCard(parent, self.colors)
        table_card.pack(fill="both", expand=True)

        ctk.CTkLabel(
            table_card,
            text="📊 Список завершённых заказов",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=15, pady=(10, 5))

        tree_container = ctk.CTkFrame(table_card, fg_color="transparent")
        tree_container.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # Стиль для таблицы
        style = ttk.Style()
        style.configure(
            "Finance.Treeview",
            background=self.colors["bg_secondary"],
            foreground=self.colors["text_primary"],
            fieldbackground=self.colors["bg_secondary"],
            borderwidth=0,
            font=("Segoe UI", 11),
            rowheight=30,
        )
        style.configure(
            "Finance.Treeview.Heading",
            background=self.colors["bg_tertiary"],
            foreground=self.colors["text_primary"],
            borderwidth=0,
            font=("Segoe UI", 11, "bold"),
        )

        columns = ("Заказ №", "Дата выдачи", "Доход", "Расход", "Прибыль")

        self.finance_tree = ttk.Treeview(
            tree_container,
            columns=columns,
            show="headings",
            height=15,
            style="Finance.Treeview",
        )

        column_widths = [100, 120, 120, 120, 120]
        for col, width in zip(columns, column_widths, strict=False):
            self.finance_tree.heading(col, text=col)
            self.finance_tree.column(col, width=width, minwidth=80)

        # Авто-скрываемые скроллбары
        from gui.widgets.auto_scroll import attach_auto_scrollbars

        attach_auto_scrollbars(tree_container, self.finance_tree)

        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        # Привязываем двойной клик для редактирования расхода
        self.finance_tree.bind("<Double-Button-1>", self.edit_expense)

        # Оверлей на время фоновой загрузки (Task O) — поверх tree_container,
        # не участвует в geometry management соседних виджетов (place, а не
        # pack/grid).
        self._finance_overlay = LoadingOverlay(tree_container, self.colors)

    def update_finance_display(self):
        """Обновление отображения финансов — запрос к БД идёт в фоновом
        потоке (AsyncLoadMixin, Task O), таблицу на время загрузки закрывает
        LoadingOverlay."""
        # Ленивая загрузка: если вкладка финансов ещё не создана — пропускаем
        if not getattr(self, "_finance_loaded", False):
            return
        if not hasattr(self, "period_var"):
            return
        period = self.period_var.get()

        def _fetch():
            return self.db.get_finance_summary(period), self.db.get_finances(period)

        def _apply(result):
            summary, finances = result

            self.income_label.configure(
                text=f"💰 Доход: {format_price(str(summary['total_income']))}"
            )
            self.expense_label.configure(
                text=f"💸 Расход: {format_price(str(summary['total_expense']))}"
            )
            self.profit_label.configure(
                text=f"📈 Прибыль: {format_price(str(summary['total_profit']))}"
            )

            # Очищаем таблицу
            for item in self.finance_tree.get_children():
                self.finance_tree.delete(item)

            # Заполняем таблицу
            for finance in finances:
                order_number = format_order_number_for_display(
                    finance.get("order_number", "_")
                )
                completion_date = format_date(finance.get("completion_date", ""))
                income = format_price(str(finance.get("income", 0)))
                expense = format_price(str(finance.get("expense", 0)))
                profit = format_price(str(finance.get("profit", 0)))

                # Определяем цвет прибыли
                tags = ()
                profit_val = finance.get("profit", 0)
                if profit_val > 0:
                    tags = ("positive",)
                elif profit_val < 0:
                    tags = ("negative",)

                self.finance_tree.insert(
                    "",
                    "end",
                    values=(order_number, completion_date, income, expense, profit),
                    tags=tags,
                )

            # Настройка цветов
            self.finance_tree.tag_configure(
                "positive", background=self.colors.get("success_light", "#e6f4ea")
            )
            self.finance_tree.tag_configure(
                "negative", background=self.colors.get("error_light", "#fce8e8")
            )

        def _on_error(error):
            logger.exception(f"Ошибка фоновой загрузки финансов: {error}")
            messagebox.showerror("Ошибка", Msg.LOAD_FINANCE_FAILED.format(error=error))

        self._run_async(
            "finance_tab",
            _fetch,
            _apply,
            on_error=_on_error,
            busy_indicator=getattr(self, "_finance_overlay", None),
            busy_text=Msg.LOADING_FINANCE,
        )

    def edit_expense(self, event):
        """Редактирование расхода по заказу"""
        selected = self.finance_tree.selection()
        if not selected:
            return

        item = self.finance_tree.item(selected[0])
        values = item["values"]
        order_number_display = values[0]

        # Получаем номер заказа для БД
        order_number = format_order_number_for_db(order_number_display)

        # Находим запись в финансах
        finances = self.db.get_finances("all")
        finance_record = None
        for f in finances:
            if f.get("order_number") == order_number:
                finance_record = f
                break

        if not finance_record:
            return

        # Диалог для ввода расхода
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Редактирование расхода")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"Заказ №{order_number_display}",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=10)

        ctk.CTkLabel(dialog, text="Доход:").pack(anchor="w", padx=20)
        income_label = ctk.CTkLabel(
            dialog,
            text=format_price(str(finance_record.get("income", 0))),
            font=ctk.CTkFont(size=12),
        )
        income_label.pack(anchor="w", padx=20, pady=(0, 10))

        ctk.CTkLabel(dialog, text="Расход (₽):").pack(anchor="w", padx=20)
        expense_entry = ctk.CTkEntry(dialog, width=200)
        expense_entry.insert(0, str(finance_record.get("expense", 0)))
        expense_entry.pack(pady=(0, 10))

        def save_expense():
            try:
                expense = float(expense_entry.get().replace(",", "."))
                if self.db.update_finance_expense(order_number, expense):
                    dialog.destroy()
                    self.update_finance_display()
                    messagebox.showinfo("Успех", "Расход обновлён")
                else:
                    messagebox.showerror("Ошибка", "Не удалось обновить расход")
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное число")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(
            btn_frame, text="Сохранить", command=save_expense, width=100
        ).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", command=dialog.destroy, width=100).pack(
            side="left", padx=5
        )
