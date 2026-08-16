#!/usr/bin/env python3
"""DevicesTableMixin — таблица заказов: фильтры, поиск, сортировка,
быстрое удаление, быстрые фильтры времени (сегодня/неделя/просрочено). См.
AUDIT_REPORT_v25.md, Task T (перенесено из main_window.py без изменения
поведения).

load_devices/apply_filters/search_devices идут через AsyncLoadMixin (Task O)
— запрос к БД выполняется в фоновом потоке, таблица сразу показывает
skeleton-строки вместо замирания GUI на время запроса."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from tkinter import messagebox
from typing import Any

from domain.constants import CLOSED_STATUSES
from gui.widgets.skeleton import clear_skeleton_rows, insert_skeleton_rows
from utils.formatters import (
    format_order_number_for_db,
    format_order_number_for_display,
    format_phone,
    format_price,
    get_days_since_receipt,
)
from utils.messages import Msg

logger = logging.getLogger(__name__)


class DevicesTableMixin:
    """Требует от финального класса ServiceCenterApp: self.db, self.tree,
    self.settings, self.status_filter/priority_filter/device_type_filter/
    brand_filter/hide_completed_var/search_var — все выставляются в
    WidgetsMixin.create_devices_table()/create_search_panel(); self._core,
    self.root, self.busy_indicator — для фоновой загрузки (AsyncLoadMixin)."""

    def toggle_completed(self):
        """Переключение отображения выполненных заказов"""
        self.settings.set("show_completed", self.hide_completed_var.get())
        self.apply_filters()

    def _save_column_state(self, _event=None):
        """Сохраняет порядок и ширину колонок в настройки."""
        try:
            # Получаем текущий порядок displaycolumns
            dc = self.tree["displaycolumns"]
            if dc and dc != ("#all",):
                order = list(dc)
                self.settings.set("column_order", order)

            # Получаем ширины
            widths = {}
            for col in self.tree["columns"]:
                widths[col] = int(self.tree.column(col, "width"))
            self.settings.set("column_widths", widths)
        except Exception:
            pass

    def _on_filter_changed(self, _choice=None):
        """Callback смены фильтра в выпадающих списках (статус/приоритет/тип/бренд).

        CTkComboBox с state='readonly' надёжнее через command, чем через
        bind('<<ComboboxSelected>>'), который не всегда срабатывает.
        """
        self.apply_filters()

    def _collect_filter_values(self, dict_type: str, db_column: str) -> list:
        """Собирает значения для фильтра: словарь + уникальные из заказов БД.

        Объединяет, чтобы в фильтре были и шаблонные значения, и те, что
        реально встречаются в заказах (могут не быть в словаре). Сортировка.
        """
        values = []
        try:
            # Из словаря
            values.extend(self.db.get_dict_values(dict_type))
            # Уникальные из заказов
            for d in self.db.get_all_devices(include_completed=True):
                v = (d.get(db_column) or "").strip()
                if v and v not in values:
                    values.append(v)
        except Exception as e:
            logger.exception(f"Ошибка сбора значений фильтра {dict_type}: {e}")
        return sorted(values)

    def _render_device_row(self, device: dict[str, Any]) -> tuple:
        """Формирует кортеж (values, tag) для вставки строки в таблицу устройств.

        Извлекает общий код из load_devices / apply_filters / search_devices.
        Включает колонку «Дней» (сколько дней в ремонте) и иконки приоритета.
        """
        # Имя устройства: brand+model или device_type+model или model
        if device.get("brand") and device.get("model"):
            device_name = f"{device['brand']} {device['model']}"
        elif device.get("device_type") and device.get("model"):
            device_name = f"{device['device_type']} {device['model']}"
        else:
            device_name = device.get("model", "")

        receipt_date = self.format_datetime_for_display(device.get("receipt_date", ""))
        completion_date = (
            self.format_datetime_for_display(device.get("completion_date", ""))
            if device.get("completion_date")
            else ""
        )

        # Колонка «Дней» — сколько дней заказ в ремонте
        receipt_date_raw = device.get("receipt_date", "")
        status_val = device.get("status", "")
        if status_val in CLOSED_STATUSES:
            days_str = "—"
        else:
            days = get_days_since_receipt(receipt_date_raw)
            days_str = str(days) if days > 0 else "0"

        defect = device.get("defect", "")
        if defect and len(defect) > 35:
            defect = defect[:35] + "..."

        photos = device.get("photos", "")
        photo_count = len(photos.split(",")) if photos else 0
        photo_indicator = f"📸 {photo_count}" if photo_count > 0 else "—"

        # Иконка приоритета
        priority_val = device.get("priority", "Обычный")
        priority_icon = {
            "Срочный": "⚡ Срочный",
            "Высокий": "▲ Высокий",
            "Обычный": "▬ Обычный",
            "Низкий": "▼ Низкий",
        }.get(priority_val, priority_val)

        # Тег строки для цветовой индикации — "urgent"/"warning" применяются
        # только если включена настройка "Напоминать о просроченных
        # заказах" (remind_overdue). Раньше эта подсветка работала
        # безусловно, флаг read'ился только overdue_days (порог), сам
        # remind_overdue нигде не проверялся, см. AUDIT_REPORT_v25.md.
        if status_val in CLOSED_STATUSES:
            tag = "completed"
        elif not self.settings.get("remind_overdue", True):
            tag = "normal"
        else:
            days = get_days_since_receipt(receipt_date_raw)
            if days > self.settings.get("overdue_days", 14):
                tag = "urgent"
            elif days > 7:
                tag = "warning"
            else:
                tag = "normal"

        values = (
            format_order_number_for_display(device.get("order_number", "")),
            receipt_date,
            days_str,
            completion_date,
            device_name,
            device.get("client_name", ""),
            format_phone(device.get("phone", "")),
            defect,
            status_val,
            priority_icon,
            device.get("engineer", ""),
            format_price(device.get("total_price", ""))
            if device.get("total_price")
            else "",
            photo_indicator,
        )
        return values, tag

    def _clear_tree_and_populate(self, devices, count_label_text=None):
        """Очищает таблицу и заполняет её списком устройств через _render_device_row."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        for device in devices:
            values, tag = self._render_device_row(device)
            self.tree.insert("", "end", values=values, tags=(tag,))

        # Обновляем статус-бар количеством заказов
        count = count_label_text or f"Заказов: {len(devices)}"
        if hasattr(self, "status_label"):
            self.update_status_bar(count)

    def _on_devices_load_error(self, error: Exception) -> None:
        """Общий обработчик ошибки фоновой загрузки таблицы заказов
        (load_devices/apply_filters/search_devices) — снимает skeleton-
        строки (заменить их нечем) и показывает сообщение через реестр
        Msg, см. utils/messages.py."""
        clear_skeleton_rows(self.tree)
        messagebox.showerror("Ошибка", Msg.LOAD_ORDERS_FAILED.format(error=error))

    def apply_filters(self):
        """Применение фильтров — запрос к БД идёт в фоновом потоке
        (AsyncLoadMixin, Task O), таблица сразу показывает skeleton-строки."""
        try:
            status = self.status_filter.get()
            priority = self.priority_filter.get()
            device_type = (
                self.device_type_filter.get()
                if hasattr(self, "device_type_filter")
                else "Все"
            )
            brand = self.brand_filter.get() if hasattr(self, "brand_filter") else "Все"
            hide_completed = self.hide_completed_var.get()
            insert_skeleton_rows(self.tree)
            self._run_async(
                "devices_table",
                lambda: self.db.get_devices_by_filters(
                    status, priority, not hide_completed, device_type, brand
                ),
                self._clear_tree_and_populate,
                on_error=self._on_devices_load_error,
                busy_indicator=getattr(self, "busy_indicator", None),
                busy_text=Msg.LOADING_ORDERS,
            )
        except Exception as e:
            logger.exception(f"Ошибка применения фильтров: {e}")

    def load_devices(self):
        """Загрузка устройств — запрос к БД идёт в фоновом потоке
        (AsyncLoadMixin, Task O), таблица сразу показывает skeleton-строки
        вместо замирания GUI на время запроса."""
        try:
            hide_completed = self.hide_completed_var.get()
            insert_skeleton_rows(self.tree)
            self._run_async(
                "devices_table",
                lambda: self.db.get_all_devices(include_completed=not hide_completed),
                self._clear_tree_and_populate,
                on_error=self._on_devices_load_error,
                busy_indicator=getattr(self, "busy_indicator", None),
                busy_text=Msg.LOADING_ORDERS,
            )
        except Exception as e:
            logger.exception(f"Ошибка загрузки устройств: {e}")

    def _quick_delete_selected(self):
        """Быстрое удаление выбранного заказа (Delete)."""
        selected = self.tree.selection()
        if not selected:
            return
        if self.settings.get("confirm_delete", True):
            if not messagebox.askyesno("Удаление", "Удалить выбранный заказ?"):
                return
        order_number_display = self.tree.item(selected[0])["values"][0]
        device_id = self.get_device_id_by_order_number(order_number_display)
        if device_id:
            try:
                # Удаляем через фасад Database вместо прямого SQL
                success = self.db.delete_device(device_id)
                if success:
                    self.load_devices()
                    self.dashboard.update_stats()
                    self.update_finance_display()
                    self.update_status_bar(f"Заказ #{order_number_display} удалён")
                else:
                    messagebox.showerror("Ошибка", "Не удалось удалить заказ")
            except Exception as e:
                logger.exception(f"Ошибка удаления: {e}")
                messagebox.showerror("Ошибка", f"Не удалось удалить заказ: {e}")

    def refresh_orders(self):
        """Ручное обновление списка заказов из БД (кнопка «🔄 Обновить»).

        Перезагружает данные с учётом текущих фильтров/поиска. Используется,
        чтобы увидеть изменения, внесённые через PWA (фото, новые заказы),
        без перезапуска программы.
        """
        try:
            # Если есть активный поиск — обновляем поиск, иначе фильтры
            search_text = (
                self.search_var.get().strip() if hasattr(self, "search_var") else ""
            )
            if search_text:
                self.search_devices()
            else:
                self.apply_filters()
            # Обновляем дашборд и финансы
            if hasattr(self, "dashboard"):
                self.dashboard.update_stats()
            if hasattr(self, "update_finance_display"):
                self.update_finance_display()
            self.update_status_bar("Список заказов обновлён")
        except Exception as e:
            logger.exception(f"Ошибка обновления: {e}")

    def show_overdue_orders(self):
        """Показ просроченных заказов (по умолчанию >14 дней в ремонте,
        настраивается в Настройках)."""
        try:
            threshold = self.settings.get("overdue_days", 14)
            # SQL-агрегация вместо питон-цикла по всем устройствам — закрывает
            # находку про 3-кратное дублирование этого фильтра (см. AUDIT_REPORT_v21.md)
            overdue = self.db.calculate("overdue_orders", threshold_days=threshold)
            self._clear_tree_and_populate(
                overdue, count_label_text=f"Просроченных: {len(overdue)}"
            )
            self.update_status_bar(f"⏰ Просроченных заказов: {len(overdue)}")
        except Exception as e:
            logger.exception(f"Ошибка фильтра просроченных: {e}")

    def show_today_orders(self):
        """Показ заказов, принятых сегодня."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            all_devices = self.db.get_all_devices(include_completed=True)
            today_orders = [
                d
                for d in all_devices
                if (d.get("receipt_date", "") or "")[:10] == today
            ]
            self._clear_tree_and_populate(
                today_orders, count_label_text=f"Сегодня: {len(today_orders)}"
            )
            self.update_status_bar(f"📅 Принято сегодня: {len(today_orders)}")
        except Exception as e:
            logger.exception(f"Ошибка фильтра «сегодня»: {e}")

    def show_week_orders(self):
        """Показ заказов за последнюю неделю."""
        try:
            week_ago = datetime.now() - timedelta(days=7)
            all_devices = self.db.get_all_devices(include_completed=True)
            week_orders = []
            for d in all_devices:
                rd = d.get("receipt_date", "")
                if rd:
                    try:
                        dt = datetime.strptime(rd[:10], "%Y-%m-%d")
                        if dt >= week_ago:
                            week_orders.append(d)
                    except (ValueError, TypeError):
                        pass
            self._clear_tree_and_populate(
                week_orders, count_label_text=f"За неделю: {len(week_orders)}"
            )
            self.update_status_bar(f"📅 За неделю: {len(week_orders)}")
        except Exception as e:
            logger.exception(f"Ошибка фильтра «неделя»: {e}")

    def search_devices(self):
        """Поиск устройств — запрос к БД идёт в фоновом потоке (AsyncLoadMixin,
        Task O), таблица сразу показывает skeleton-строки."""
        try:
            search_text = self.search_var.get().strip().lower()
            hide_completed = self.hide_completed_var.get()

            if not search_text:
                self.load_devices()
                return

            insert_skeleton_rows(self.tree)

            def _apply(devices):
                self._clear_tree_and_populate(
                    devices, count_label_text=f"Найдено: {len(devices)}"
                )

            self._run_async(
                "devices_table",
                lambda: self.db.search_devices(
                    search_text, include_completed=not hide_completed
                ),
                _apply,
                on_error=self._on_devices_load_error,
                busy_indicator=getattr(self, "busy_indicator", None),
                busy_text=Msg.LOADING_SEARCH,
            )
        except Exception as e:
            logger.exception(f"Ошибка поиска: {e}")

    def sort_treeview(self, col):
        """Сортировка таблицы"""
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False

        items = [
            (self.tree.set(item, col), item) for item in self.tree.get_children("")
        ]

        if col == "Цена":
            items.sort(
                key=lambda x: (
                    float(x[0].replace("₽", "").replace(" ", "").replace(",", ""))
                    if x[0] != "0 ₽"
                    else 0
                ),
                reverse=self.sort_reverse,
            )
        else:
            items.sort(reverse=self.sort_reverse)

        for index, (_, item) in enumerate(items):
            self.tree.move(item, "", index)

        for heading in self.tree["columns"]:
            if heading == col:
                self.tree.heading(
                    heading, text=f"{heading} {'▼' if self.sort_reverse else '▲'}"
                )
            else:
                self.tree.heading(heading, text=heading)

    def get_device_id_by_order_number(self, order_number_display: str) -> int | None:
        """Получение ID устройства по номеру заказа"""
        try:
            db_order_number = format_order_number_for_db(order_number_display)
            device = self.db.get_device_by_order_number(db_order_number)
            if device:
                return device.get("id")
            return None
        except Exception as e:
            logger.exception(f"Ошибка получения ID устройства: {e}")
            return None

    def on_device_double_click(self, event):
        """Обработка двойного клика"""
        self.edit_device()

    def edit_device(self):
        """Редактирование устройства"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите заказ")
            return

        order_number_display = self.tree.item(selected[0])["values"][0]
        device_id = self.get_device_id_by_order_number(order_number_display)

        if not device_id:
            messagebox.showerror(
                "Ошибка",
                f"Не удалось найти устройство с номером {order_number_display}",
            )
            return

        device = self.db.get_device(device_id)

        if device:
            self.open_edit_device_window(device)
        else:
            messagebox.showerror("Ошибка", "Не удалось загрузить данные")

    def format_datetime_for_display(self, date_str):
        """Форматирование даты и времени для отображения"""
        if not date_str:
            return ""
        try:
            if " " in date_str:
                dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%d.%m.%Y %H:%M")
            else:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                return dt.strftime("%d.%m.%Y")
        except (ValueError, TypeError):
            return date_str[:10] if date_str else ""
