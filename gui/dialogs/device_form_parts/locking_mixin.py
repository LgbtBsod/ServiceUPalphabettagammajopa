#!/usr/bin/env python3
"""DeviceLockingMixin — пессимистичная блокировка заказа (баннер/heartbeat/
read-only режим) + перебиндинг полей формы после конфликта версий. См.
AUDIT_REPORT_v25.md, Task T (перенесено из device_form.py без изменения
поведения)."""

from __future__ import annotations

import contextlib
import logging
from tkinter import messagebox

import customtkinter as ctk

from utils.messages import Msg

logger = logging.getLogger(__name__)

# Heartbeat пессимистичной блокировки — раз в минуту с запасом внутри
# lock_ttl_seconds (по умолчанию 300с), не на каждое нажатие клавиши (см.
# managers/locking.py — блокировка живёт, пока диалог открыт, а не только
# пока пользователь буквально печатает).
LOCK_HEARTBEAT_MS = 60_000

# SSOT-список скалярных редактируемых полей Device, известных этому диалогу
# (без work_items/photos/completion_date — у них отдельное состояние и
# особая логика, см. _apply_scalar_fields). Раньше этот набор был
# независимо продублирован строковыми литералами в save() (дважды) и в
# _apply_scalar_fields — тройная ручная синхронизация без единого
# источника истины, см. AUDIT_REPORT_v25.md. _apply_scalar_fields ниже
# реально ИТЕРИРУЕТ этот список (не просто документирует его); save()'s
# device_data-литералы пока остаются отдельными (валидация/спец-логика
# конкретных полей делает безопасную механическую унификацию рискованнее,
# чем стоит прямо сейчас) — tests/test_device_field_consistency.py
# сверяет этот список с database/sqlalchemy_database.py::DEVICE_UPDATE_FIELDS,
# так что дрейф между ними теперь ловит тест, а не остаётся незамеченным.
SCALAR_FIELD_NAMES = (
    "device_type",
    "brand",
    "model",
    "serial_number",
    "defect",
    "appearance",
    "completeness",
    "client_name",
    "client_status",
    "phone",
    "total_price",
    "prepayment",
    "priority",
    "engineer",
    "warranty",
    "notes",
    "status",
)


class DeviceLockingMixin:
    """Требует от финального класса DeviceFormDialog: self.is_new,
    self.device_data, self.lock_api, self.tabview, self.save_btn,
    self.main_container, self.colors, self.db — все выставляются в
    DeviceFormDialog.__init__/create_widgets (см. device_form.py)."""

    def _setup_pessimistic_lock(self) -> None:
        """Пытается захватить пессимистичную блокировку заказа (только для
        редактирования существующего — у нового заказа ещё нет строки в БД,
        нечего блокировать). Ничего не делает, если lock_api не передан или
        настройка pessimistic_locking_enabled выключена — диалог ведёт себя
        как раньше."""
        if self.is_new or not self.device_data or not self.lock_api:
            return
        with contextlib.suppress(Exception):
            if not self.lock_api.is_enabled():
                return
        device_id = self.device_data.get("id")
        if device_id is None:
            return
        result = self._try_acquire_lock()
        if result is not None and not result.ok:
            self._render_lock_banner(result)
            self._set_widgets_enabled(self.tabview, False)
            with contextlib.suppress(Exception):
                self.save_btn.configure(state="disabled")

    def _try_acquire_lock(self):
        """Один вызов try_acquire — используется и при открытии формы, и по
        кнопке "Обновить" в баннере конфликта."""
        device_id = self.device_data.get("id")
        try:
            result = self.lock_api.try_acquire("device", device_id)
        except Exception as e:
            logger.warning(f"Не удалось проверить блокировку заказа: {e}")
            return None
        if result.ok:
            self._holding_lock = True
            self._start_heartbeat()
        return result

    def _start_heartbeat(self) -> None:
        if self._heartbeat_job is not None:
            return  # уже тикает

        def _tick():
            self._heartbeat_job = None
            if not self._holding_lock or not self.winfo_exists():
                return
            device_id = self.device_data.get("id") if self.device_data else None
            if device_id is not None:
                refreshed = True
                with contextlib.suppress(Exception):
                    refreshed = self.lock_api.refresh("device", device_id)
                if not refreshed:
                    # Блокировку успел перехватить кто-то другой (TTL истёк
                    # раньше нашего heartbeat) — раньше это молча
                    # игнорировалось, и диалог до конца сессии вёл себя так,
                    # будто всё ещё эксклюзивно владеет записью (см.
                    # AUDIT_REPORT_v25.md). Переводим форму в то же
                    # состояние "заблокировано другим", что и при открытии.
                    self._holding_lock = False
                    result = self._try_acquire_lock()
                    if result is not None and not result.ok:
                        self._render_lock_banner(result)
                        self._set_widgets_enabled(self.tabview, False)
                        with contextlib.suppress(Exception):
                            self.save_btn.configure(state="disabled")
                    return  # не переустанавливаем tick — _try_acquire_lock
                    # сам запустит новый heartbeat, если блокировку удалось
                    # тут же перезахватить (result.ok=True)
            self._heartbeat_job = self.after(LOCK_HEARTBEAT_MS, _tick)

        self._heartbeat_job = self.after(LOCK_HEARTBEAT_MS, _tick)

    def _set_widgets_enabled(self, container, enabled: bool) -> None:
        """Рекурсивно включает/выключает все виджеты поддерева (read-only
        режим при конфликте блокировки) — обходит уже построенное дерево, не
        трогая код создания конкретных полей. Контейнеры (CTkFrame и т.п.),
        не поддерживающие state=, просто пропускаются (suppress) — обход
        продолжается вглубь."""
        state = "normal" if enabled else "disabled"
        for child in container.winfo_children():
            with contextlib.suppress(Exception):
                child.configure(state=state)
            self._set_widgets_enabled(child, enabled)

    def _render_lock_banner(self, result, still_held: bool = False) -> None:
        """Баннер "заказ заблокирован" вверху диалога (между заголовком и
        вкладками) + кнопка "Обновить", которая заново пробует захват — если
        блокировка к тому моменту снята, диалог переходит в редактирование
        БЕЗ пересоздания виджетов (см. _retry_lock_acquire). still_held=True
        — это повторный отказ (после клика "Обновить"), не первое
        обнаружение блокировки — текст короче (Msg.LOCK_STILL_HELD)."""
        started = result.started_at
        time_str = started.strftime("%H:%M") if hasattr(started, "strftime") else "?"
        holder = result.holder_label or result.holder_key or "?"
        # Терсер-текст на повторный отказ (still_held) — не повторяет
        # объяснение "можно смотреть, но не сохранить" при каждом клике
        # "Обновить", если блокировка так и не освободилась.
        text = (
            Msg.LOCK_STILL_HELD.format(holder=holder)
            if still_held
            else Msg.LOCK_HELD_BY_OTHER.format(holder=holder, time=time_str)
        )

        if self._lock_banner is not None:
            with contextlib.suppress(Exception):
                self._lock_banner.destroy()

        banner = ctk.CTkFrame(self.main_container, fg_color="#4a2f1a", corner_radius=8)
        banner.pack(fill="x", pady=(0, 10), before=self.tabview)

        label = ctk.CTkLabel(
            banner, text=text, text_color="#ffcc80", font=ctk.CTkFont(size=13, weight="bold")
        )
        label.pack(side="left", padx=12, pady=8)

        refresh_btn = ctk.CTkButton(
            banner,
            text="🔄 Обновить",
            command=self._retry_lock_acquire,
            width=110,
            height=28,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"],
        )
        refresh_btn.pack(side="right", padx=12, pady=8)

        self._lock_banner = banner

    def _hide_lock_banner(self) -> None:
        if self._lock_banner is not None:
            with contextlib.suppress(Exception):
                self._lock_banner.destroy()
            self._lock_banner = None

    def _retry_lock_acquire(self) -> None:
        result = self._try_acquire_lock()
        if result is None:
            return
        if result.ok:
            self._hide_lock_banner()
            self._set_widgets_enabled(self.tabview, True)
            with contextlib.suppress(Exception):
                self.save_btn.configure(state="normal")
            logger.info(Msg.LOCK_REACQUIRED)
        else:
            self._render_lock_banner(result, still_held=True)

    def _apply_scalar_fields(self, data: dict) -> None:
        """Перезаписывает скалярные текстовые/комбо-поля формы значениями
        из data — БЕЗ пересоздания виджетов (create_widgets не зовётся
        повторно). Используется "Обновить" при конфликте версий
        (_rebind_from_fresh_data). Сознательно НЕ трогает фото/работы —
        отдельное состояние (self.current_photos/self.work_manager),
        безопасный per-item merge для них сложнее простого перезатирания
        скаляра и не входит в объём этой правки.

        Итерирует модульный SCALAR_FIELD_NAMES (SSOT), а не свой
        собственный список строк — если в константу добавят имя поля без
        соответствующего сеттера ниже, setters[field_name] упадёт
        KeyError'ом ВНЕ suppress-блока (громко, при первом же ре-биндинге),
        а не молча проигнорирует поле."""

        def _set_entry(entry, value):
            entry.delete(0, "end")
            entry.insert(0, str(value if value is not None else ""))

        def _set_textbox(box, value):
            box.delete("1.0", "end")
            box.insert("1.0", str(value if value is not None else ""))

        setters = {
            "device_type": self.device_type_combo.set,
            "brand": self.brand_combo.set,
            "model": lambda v: _set_entry(self.model_entry, v),
            "serial_number": lambda v: _set_entry(self.serial_entry, v),
            "defect": lambda v: _set_textbox(self.defect_text, v),
            "appearance": self.appearance_combo.set,
            "completeness": self.completeness_combo.set,
            "client_name": lambda v: _set_entry(self.client_name_entry, v),
            "client_status": self.client_status_combo.set,
            "phone": lambda v: _set_entry(self.phone_entry, v),
            "total_price": lambda v: _set_entry(self.total_price_entry, v),
            "prepayment": lambda v: _set_entry(self.prepayment_entry, v),
            "priority": self.priority_combo.set,
            "engineer": self.engineer_combo.set,
            "warranty": self.warranty_combo.set,
            "notes": lambda v: _set_textbox(self.notes_text, v),
            "status": self.status_combo.set,
        }
        for field_name in SCALAR_FIELD_NAMES:
            setter = setters[field_name]  # KeyError громко, не проглатывается
            with contextlib.suppress(Exception):
                setter(data.get(field_name, ""))
        if hasattr(self, "expense_entry"):
            with contextlib.suppress(Exception):
                _set_entry(self.expense_entry, data.get("expense", ""))

    def _rebind_from_fresh_data(self) -> None:
        """"Обновить" в диалоге конфликта версий: подтягивает актуальные
        данные из БД и перезаписывает поля формы НА МЕСТЕ (без пересоздания
        окна/виджетов) — включая новую version, чтобы следующее "Сохранить"
        прошло проверку. Текущие несохранённые правки пользователя при этом
        ЗАТИРАЮТСЯ актуальными данными — сознательное упрощение (полный
        posle-конфликтный per-field merge сложнее и не запрошен явно), надо
        будет повторить правку поверх свежей версии."""
        device_id = self.device_data.get("id") if self.device_data else None
        if device_id is None:
            return
        fresh = self.db.get_device(device_id)
        if fresh is None:
            messagebox.showerror("Ошибка", "❌ Заказ больше не существует (возможно, удалён).")
            self.destroy()
            return
        self.device_data = fresh
        self._apply_scalar_fields(fresh)

    def _close_with_geometry(self):
        """Сохраняет геометрию окна в config и закрывает его."""
        from utils.window_state import close_dialog_with_geometry

        close_dialog_with_geometry(self, self.settings, "device_form")

    def destroy(self):
        """Единая точка снятия блокировки — все пути закрытия (Отмена,
        крестик/WM_DELETE_WINDOW, успешное сохранение) в итоге вызывают
        именно destroy(), в отличие от _close_with_geometry (Отмена его не
        зовёт, см. cancel_btn) — поэтому heartbeat/release живут здесь, а
        не там."""
        if self._heartbeat_job is not None:
            with contextlib.suppress(Exception):
                self.after_cancel(self._heartbeat_job)
            self._heartbeat_job = None
        if self._holding_lock and self.lock_api and self.device_data:
            device_id = self.device_data.get("id")
            if device_id is not None:
                with contextlib.suppress(Exception):
                    self.lock_api.release("device", device_id)
            self._holding_lock = False
        super().destroy()
