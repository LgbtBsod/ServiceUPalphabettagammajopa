#!/usr/bin/env python3
"""DeviceSaveMixin — валидация + сохранение формы (создание/обновление
заказа), включая тихое сохранение для "печать акта до явного Save". См.
AUDIT_REPORT_v25.md, Task T (перенесено из device_form.py без изменения
поведения)."""

from __future__ import annotations

import logging
from datetime import datetime
from tkinter import messagebox

from database.sqlalchemy_database import OptimisticLockError
from domain.constants import STATUS_ISSUED
from utils.formatters import (
    format_order_number_for_display,
    generate_order_number,
    normalize_phone,
)
from utils.messages import Msg
from utils.validators import validate_phone, validate_price

logger = logging.getLogger(__name__)


class DeviceSaveMixin:
    """Требует от финального класса DeviceFormDialog: все поля формы
    (self.device_type_combo, ...), self.db, self.client_db, self.is_new,
    self.device_data, self.employees_api, self.work_manager,
    self.current_photos, self._close_with_geometry(),
    self._rebind_from_fresh_data() (см. DeviceLockingMixin)."""

    def _do_save(self, silent: bool = False) -> bool:
        """Тихое сохранение без закрытия окна. Возвращает True при успехе."""
        try:
            from datetime import datetime as _dt

            from utils.formatters import normalize_phone

            client_name = self.client_name_entry.get().strip()
            phone_raw = self.phone_entry.get().strip()
            if not client_name or not phone_raw:
                if not silent:
                    messagebox.showerror("Ошибка", "Заполните имя и телефон!")
                return False

            phone = normalize_phone(phone_raw)
            order_counter = self.db.get_next_order_number()
            order_number = generate_order_number(order_counter)

            # Собираем work_items
            work_items_json = (
                self.work_manager.to_json() if self.work_manager.items else ""
            )

            try:
                wm_total = (
                    int(self.work_manager.get_total_price())
                    if self.work_manager.items
                    else 0
                )
            except Exception:
                wm_total = 0
            total_price = (
                str(wm_total) if wm_total > 0 else self.total_price_entry.get().strip()
            )

            now = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
            device_data = {
                "order_number": order_number,
                "receipt_date": now,
                "device_type": self.device_type_combo.get().strip()
                if hasattr(self, "device_type_combo")
                else "",
                "brand": self.brand_combo.get().strip()
                if hasattr(self, "brand_combo")
                else "",
                "model": self.model_entry.get().strip()
                if hasattr(self, "model_entry")
                else "",
                "serial_number": self.serial_entry.get().strip()
                if hasattr(self, "serial_entry")
                else "",
                "defect": self.defect_text.get("1.0", "end-1c").strip()
                if hasattr(self, "defect_text")
                else "",
                "appearance": self.appearance_combo.get().strip()
                if hasattr(self, "appearance_combo")
                else "",
                "completeness": self.completeness_combo.get().strip()
                if hasattr(self, "completeness_combo")
                else "",
                "work_items_json": work_items_json,
                "client_name": client_name,
                "client_status": self.client_status_combo.get().strip()
                if hasattr(self, "client_status_combo")
                else "Новый",
                "phone": phone,
                "total_price": total_price,
                "prepayment": self.prepayment_entry.get().strip()
                if hasattr(self, "prepayment_entry")
                else "",
                "status": self.status_combo.get().strip()
                if hasattr(self, "status_combo")
                else "Диагностика",
                "priority": self.priority_combo.get().strip()
                if hasattr(self, "priority_combo")
                else "Обычный",
                "engineer": self.engineer_combo.get().strip()
                if hasattr(self, "engineer_combo")
                else "",
                "warranty": self.warranty_combo.get().strip()
                if hasattr(self, "warranty_combo")
                else "",
                "notes": self.notes_text.get("1.0", "end-1c").strip()
                if hasattr(self, "notes_text")
                else "",
                "photos": ",".join(self.current_photos) if self.current_photos else "",
                "expense": self.expense_entry.get().strip()
                if hasattr(self, "expense_entry")
                else "0",
                "created_by_id": self.employees_api.get_current_employee_id()
                if self.employees_api
                else None,
            }

            device_id = self.db.add_device(device_data)
            if device_id:
                self.client_db.add_repair_to_client_history(
                    client_name, phone, device_data
                )
                self.is_new = False
                self.device_data = device_data
                self.device_data["id"] = device_id
                self.result = device_data
                if not silent:
                    messagebox.showinfo("Успех", f"Заказ №{order_number} создан!")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}", exc_info=True)
            return False

    def save(self):
        """Сохранение данных"""
        try:
            # Сбор данных
            device_type = self.device_type_combo.get().strip()
            brand = self.brand_combo.get().strip()
            model = self.model_entry.get().strip()
            serial_number = self.serial_entry.get().strip()
            defect = self.defect_text.get("1.0", "end-1c").strip()
            appearance = self.appearance_combo.get().strip()
            completeness = self.completeness_combo.get().strip()
            client_name = self.client_name_entry.get().strip()
            client_status = self.client_status_combo.get().strip()
            phone_raw = self.phone_entry.get().strip()
            # БЕРЁМ total_price из work_manager (актуальная сумма работ), а не только
            # из entry — entry мог быть пустым или не обновляться после правок работ.
            # Это исправляет «не отображается общая сумма» в истории клиента.
            try:
                wm_total = int(self.work_manager.get_total_price())
            except Exception:
                wm_total = 0
            total_price_from_entry = self.total_price_entry.get().strip()
            # Приоритет — фактическая сумма работ; иначе значение из поля (если вводили вручную)
            if wm_total > 0:
                total_price = str(wm_total)
                # Синхронизируем поле с актуальной суммой
                self.total_price_entry.delete(0, "end")
                self.total_price_entry.insert(0, str(wm_total))
            else:
                total_price = total_price_from_entry
            prepayment = self.prepayment_entry.get().strip()
            expense = (
                self.expense_entry.get().strip()
                if hasattr(self, "expense_entry")
                else "0"
            )
            priority = self.priority_combo.get().strip()
            engineer = self.engineer_combo.get().strip()
            warranty = self.warranty_combo.get().strip()
            notes = self.notes_text.get("1.0", "end-1c").strip()
            status = self.status_combo.get().strip()

            photos_str = ",".join(self.current_photos) if self.current_photos else ""
            work_items_json = (
                self.work_manager.to_json() if hasattr(self, "work_manager") else ""
            )

            # Получаем дату приема
            if hasattr(self, "receipt_datetime_label"):
                receipt_date_str = self.receipt_datetime_label.cget("text")
                try:
                    dt = datetime.strptime(receipt_date_str, "%d.%m.%Y %H:%M:%S")
                    receipt_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    receipt_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                receipt_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Валидация
            if not device_type:
                messagebox.showerror("Ошибка", "Выберите тип устройства!")
                return
            if not model:
                messagebox.showerror("Ошибка", "Заполните модель устройства!")
                return
            if not defect:
                messagebox.showerror("Ошибка", "Опишите неисправность!")
                return
            if not client_name:
                messagebox.showerror("Ошибка", "Заполните ФИО клиента!")
                return
            if not phone_raw:
                messagebox.showerror("Ошибка", "Заполните номер телефона!")
                return

            if not validate_phone(phone_raw):
                messagebox.showerror(
                    "Ошибка", "Неверный формат телефона!\nПример: +7 (123) 456-78-90"
                )
                return

            if total_price and not validate_price(total_price):
                messagebox.showerror("Ошибка", "Неверный формат цены!")
                return

            if prepayment and not validate_price(prepayment):
                messagebox.showerror("Ошибка", "Неверный формат предоплаты!")
                return

            if expense and not validate_price(expense):
                messagebox.showerror("Ошибка", "Неверный формат затрат!")
                return

            # Нормализуем телефон к единому каноничному виду.
            # Раньше телефон сохранялся «как ввёл пользователь» (с любыми
            # разделителями), из-за чего поиск по телефону ничего не находил.
            phone = normalize_phone(phone_raw)

            if self.is_new:
                # Создание нового заказа
                order_counter = self.db.get_next_order_number()
                order_number = generate_order_number(order_counter)

                device_data = {
                    "order_number": order_number,
                    "receipt_date": receipt_date,
                    "device_type": device_type,
                    "brand": brand,
                    "model": model,
                    "serial_number": serial_number,
                    "defect": defect,
                    "appearance": appearance,
                    "completeness": completeness,
                    "work_items_json": work_items_json,
                    "client_name": client_name,
                    "client_status": client_status,
                    "phone": phone,
                    "total_price": total_price,
                    "prepayment": prepayment,
                    "priority": priority,
                    "engineer": engineer,
                    "warranty": warranty,
                    "notes": notes,
                    "status": status,
                    "photos": photos_str,
                    "expense": expense,
                    "created_by_id": self.employees_api.get_current_employee_id()
                    if self.employees_api
                    else None,
                }

                device_id = self.db.add_device(device_data)

                if device_id:
                    # Сохраняем в историю клиента
                    self.client_db.add_repair_to_client_history(
                        client_name, phone, device_data
                    )

                    self.result = device_data
                    self._close_with_geometry()
                    messagebox.showinfo(
                        "Успех",
                        f"✅ Заказ #{format_order_number_for_display(order_number)} создан!",
                    )
                else:
                    messagebox.showerror("Ошибка", "❌ Не удалось создать заказ")
            else:
                # Обновление существующего заказа
                existing_order_number = self.device_data.get("order_number", "")
                completion_date = ""
                if status == STATUS_ISSUED:
                    completion_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                device_data = {
                    # КРИТИЧНО: order_number должен присутствовать в данных,
                    # иначе db.update_device() записывает в finances с пустым
                    # номером и нарушает UNIQUE(order_number).
                    "order_number": existing_order_number,
                    "device_type": device_type,
                    "brand": brand,
                    "model": model,
                    "serial_number": serial_number,
                    "defect": defect,
                    "appearance": appearance,
                    "completeness": completeness,
                    "work_items_json": work_items_json,
                    "client_name": client_name,
                    "client_status": client_status,
                    "phone": phone,
                    "total_price": total_price,
                    "prepayment": prepayment,
                    "priority": priority,
                    "engineer": engineer,
                    "warranty": warranty,
                    "notes": notes,
                    "status": status,
                    "photos": photos_str,
                    "completion_date": completion_date,
                    "expense": expense,
                    "created_by_id": self.employees_api.get_current_employee_id()
                    if self.employees_api
                    else None,
                    # Оптимистичная блокировка: версия, прочитанная при
                    # ОТКРЫТИИ формы (Database.get_device кладёт её в
                    # "version") — не пересчитываем на момент сохранения,
                    # иначе проверка ничего бы не ловила (см.
                    # database/sqlalchemy_database.py::update_device).
                    "_expected_version": self.device_data.get("version"),
                }

                try:
                    update_ok = self.db.update_device(self.device_data.get("id"), device_data)
                except OptimisticLockError as e:
                    if messagebox.askyesno(
                        "Конфликт версий",
                        f"{Msg.OPTIMISTIC_CONFLICT.format()}\n\n{e}\n\n"
                        "Обновить данные из базы сейчас?",
                    ):
                        self._rebind_from_fresh_data()
                    return

                if update_ok:
                    # Обновляем в истории клиента
                    self.client_db.update_repair_in_history(
                        client_name, phone, existing_order_number, device_data
                    )

                    # Уведомление клиента о готовности заказа — НЕ вызывается
                    # отсюда напрямую. Database.update_device() публикует
                    # DeviceStatusChangedEvent через Kernel EventBus,
                    # IntegrationManager подписан на него в bootstrap.py и
                    # сам решает, уведомлять ли (переход в "Готов к
                    # выдаче") — этот диалог не обязан знать об
                    # IntegrationManager вообще. См. AUDIT_REPORT_v25.md:
                    # то же событие срабатывает и для быстрой смены статуса
                    # (update_device_status(), кнопка/PWA), которую раньше
                    # прямой вызов отсюда вообще не мог покрыть.

                    self.result = device_data
                    self._close_with_geometry()
                    messagebox.showinfo("Успех", "✅ Заказ обновлен!")
                else:
                    messagebox.showerror("Ошибка", "❌ Не удалось обновить заказ")

        except Exception as e:
            messagebox.showerror("Ошибка", f"❌ Ошибка сохранения: {e!s}")
            import traceback

            traceback.print_exc()
