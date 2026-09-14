"""Заказы: список, поиск, фильтр, создание/редактирование, смена статуса.

Использует те же методы Database, что и pwa/server.py (get_all_devices,
search_devices, get_devices_by_filters, add_device, update_device,
update_device_status) — тот же контракт данных, третий равноправный
потребитель одного и того же facade."""

from __future__ import annotations

import flet as ft

from database.sqlalchemy_database import OptimisticLockError
from domain.constants import PRIORITIES, STATUS_ISSUED, STATUSES, WARRANTIES

from . import theme
from .theme import PRIORITY_COLORS, STATUS_COLORS

_ALL = "Все"


def _opt(value: str, label: str | None = None) -> ft.dropdown.Option:
    """ft.dropdown.Option(value) сам по себе НЕ показывает текст — первый
    позиционный параметр это key, а text по умолчанию None (значение есть,
    подпись в UI пустая). Всегда задаём оба явно."""
    return ft.dropdown.Option(key=value, text=label if label is not None else (value or "—"))


def _print_act(app, device: dict, act_type: str) -> None:
    """Печать акта (приёма/выполненных работ) для реального заказа — тот же
    шаблон (reports/report_editor.py::load_template_data) и генератор
    (reports/report_renderer.py::ActPDFGenerator), что использует классический
    интерфейс (см. gui/main_window_parts/acts_mixin.py). Flet-шеллу нет смысла
    заводить отдельный предпросмотр — PDF открывается системным просмотрщиком,
    печать оттуда доступна как для любого другого документа."""
    import contextlib
    import os
    import subprocess
    import sys
    import tempfile

    from reports.report_editor import load_template_data
    from reports.report_renderer import ActPDFGenerator

    try:
        if act_type == "completion" and device.get("work_items"):
            from database.models import WorkItemsManager

            work_manager = WorkItemsManager()
            work_manager.from_json(device["work_items"])
            device = {**device, "completed_work": work_manager.get_description_summary()}

        template = load_template_data(act_type)
        gen = ActPDFGenerator(template_data=template)

        # Каждый клик по печати создавал НОВЫЙ temp PDF и никогда не удалял
        # ни один из них — репозиторий тем самым копил по одному
        # осиротевшему файлу на каждую печать за всё время работы процесса
        # (workflow-найденный гэп). Полный предпросмотр/редактирование, как
        # в classic-GUI (gui/dialogs/act_preview.py), — отдельная большая
        # фича; здесь, как первый шаг, удаляем ПРЕДЫДУЩИЙ temp-файл прямо
        # перед созданием следующего — тот же приём, что и в
        # act_preview.py::render_pdf_preview() (contextlib.suppress(OSError),
        # т.к. системный просмотрщик мог ещё держать файл открытым).
        last_path = getattr(app, "_last_act_print_path", None)
        if last_path and os.path.exists(last_path):
            with contextlib.suppress(OSError):
                os.remove(last_path)

        fd, path = tempfile.mkstemp(
            suffix=f"_{act_type}_{device.get('order_number', '')}.pdf"
        )
        os.close(fd)
        app._last_act_print_path = path
        ok = (
            gen.generate_completion_pdf(path, device)
            if act_type == "completion"
            else gen.generate_receipt_pdf(path, device)
        )
        if not ok or not os.path.exists(path):
            app.show_snackbar("Не удалось сформировать акт", error=True)
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
        app.show_snackbar("Акт сформирован и открыт для печати")

        # Печать акта выполненных работ = выдача устройства клиенту — тот же
        # рабочий процесс, что и в classic-GUI
        # (gui/main_window_parts/acts_mixin.py::print_completion_act()).
        # Flet-версия раньше вообще не трогала статус: заказы, выданные
        # через Flet, оставались в прежнем статусе, пока сотрудник не менял
        # его вручную — искажая дашборд/финансовые цифры, завязанные на
        # статус (workflow-найденный гэп).
        if act_type == "completion" and device.get("status") != STATUS_ISSUED:
            _ask_mark_issued(app, device)
    except Exception as e:
        app.show_snackbar(f"Ошибка печати акта: {e}", error=True)


def _ask_mark_issued(app, device: dict) -> None:
    order_number = device.get("order_number", "")

    def _confirm(_e) -> None:
        app.page.pop_dialog()
        ok = app.db.update_device_status(device["id"], STATUS_ISSUED)
        if ok:
            app.show_snackbar(f"Заказ №{order_number} отмечен как «Выдан клиенту»")
            app.rerender()
        else:
            app.show_snackbar("Не удалось изменить статус", error=True)

    def _cancel(_e) -> None:
        app.page.pop_dialog()

    app.page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text("Выдача устройства"),
            content=ft.Text(
                f"Изменить статус заказа №{order_number} на «Выдан клиенту»?"
            ),
            actions=[
                ft.TextButton("Отмена", on_click=_cancel),
                ft.TextButton("Да", on_click=_confirm),
            ],
        )
    )


def _dropdown_options_with_fallback(
    current_value: str, known_values: list[str], legacy_label: str
) -> list[ft.dropdown.Option]:
    """Опции для Dropdown, + сам current_value первым пунктом, если он не
    входит в known_values — иначе Dropdown.value не находит совпадения ни по
    одному ключу, Flutter рисует пустую строку вместо текста ДАЖЕ когда
    реальное значение в БД корректно, и (что хуже) сохранение формы молча
    затирает это значение пустым, потому что Dropdown.value читается как ""
    (см. _status_options — тот же класс бага повторялся у warranty/priority,
    у которых в классическом интерфейсе поле — редактируемый CTkComboBox, а
    не закрытый список, так что произвольное легаси-значение там абсолютно
    легально)."""
    opts = [_opt(v) for v in known_values]
    if current_value and current_value not in known_values:
        opts.insert(0, _opt(current_value, label=f"{current_value} ({legacy_label})"))
    return opts


def _status_options(current_value: str) -> list[ft.dropdown.Option]:
    return _dropdown_options_with_fallback(current_value, STATUSES, "устаревший статус")


class OrdersView:
    def __init__(self, app):
        self.app = app
        self.mode = "list"  # "list" | "form"
        self.editing_id: int | None = None
        self.search_text = ""
        self.status_filter = _ALL

    # ── публичный рендер ─────────────────────────────────────

    def render(self) -> ft.Control:
        return self._render_form() if self.mode == "form" else self._render_list()

    # ── список ───────────────────────────────────────────────

    def _fetch_rows(self) -> list[dict]:
        db = self.app.db
        if self.search_text.strip():
            rows = db.search_devices(self.search_text, include_completed=True)
            if self.status_filter != _ALL:
                rows = [r for r in rows if r["status"] == self.status_filter]
            return rows
        return db.get_devices_by_filters(
            status_filter=self.status_filter, priority_filter=_ALL, include_completed=True
        )

    def _render_list(self) -> ft.Control:
        c = self.app.colors
        rows = self._fetch_rows()

        def on_search_change(e: ft.ControlEvent) -> None:
            # НЕ вызывает rerender() на каждый символ: rerender()
            # пересобирает весь список Column'ом с нуля — ни один из его
            # контролов не задаёт key=, поэтому Flet-реконсилиатор видит
            # НОВОЕ текстовое поле поиска (а не патч уже существующего) и
            # демонтирует/монтирует его заново, теряя фокус ввода после
            # КАЖДОГО символа (workflow-найденный баг — многосимвольный
            # поиск был фактически неюзабелен). Значение копим здесь,
            # реальный поиск запускается по Enter/кнопке ниже.
            self.search_text = e.control.value

        def on_search_submit(_e) -> None:
            self.app.rerender()

        def on_status_filter(e: ft.ControlEvent) -> None:
            self.status_filter = e.control.value
            self.app.rerender()

        def on_new(_e) -> None:
            self.mode = "form"
            self.editing_id = None
            self.app.rerender()

        header = ft.Row(
            [
                ft.Text("Заказы", size=24, weight=ft.FontWeight.BOLD, color=c["text_primary"]),
                ft.Container(expand=True),
                ft.ElevatedButton("+ Новый заказ", on_click=on_new,
                                   bgcolor=c["accent"], color="white"),
            ],
        )
        toolbar = ft.Row(
            [
                ft.TextField(
                    label="Поиск (клиент, телефон, номер заказа...) — Enter для поиска",
                    value=self.search_text, on_change=on_search_change,
                    on_submit=on_search_submit, expand=True, dense=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.SEARCH, tooltip="Найти", on_click=on_search_submit,
                ),
                ft.Dropdown(
                    label="Статус", value=self.status_filter, width=220, dense=True,
                    options=[_opt(_ALL)] + [_opt(s) for s in STATUSES],
                    on_select=on_status_filter,
                ),
            ],
            spacing=12,
        )

        if not rows:
            # ft.alignment.center не существует в этой версии Flet (нет
            # готовых констант в модуле) — Alignment(0, 0) эквивалентен
            # Flutter Alignment.center. Не сработал ни один прежний живой
            # прогон (тестовая БД никогда не была пустой) — вскрылось только
            # на СВЕЖЕЙ базе frozen-сборки (%LOCALAPPDATA%\ServiceUP только
            # что создан, заказов ещё нет).
            body = ft.Container(
                ft.Text("Заказов не найдено.", color=c["text_secondary"]),
                padding=30, alignment=ft.alignment.Alignment(0, 0),
            )
        else:
            body = ft.Column([self._order_card(r) for r in rows], spacing=10)

        return ft.Column([header, ft.Container(height=12), toolbar, ft.Container(height=16), body], spacing=0)

    def _order_card(self, row: dict) -> ft.Control:
        c = self.app.colors
        status_color = STATUS_COLORS.get(row["status"], c["text_secondary"])
        priority_color = PRIORITY_COLORS.get(row["priority"], c["text_secondary"])

        def on_edit(_e) -> None:
            self.mode = "form"
            self.editing_id = row["id"]
            self.app.rerender()

        def on_status_change(e: ft.ControlEvent) -> None:
            new_status = e.control.value
            ok = self.app.db.update_device_status(row["id"], new_status)
            if ok:
                self.app.show_snackbar(f"Статус заказа #{row['order_number']} изменён на «{new_status}»")
            else:
                self.app.show_snackbar("Не удалось изменить статус", error=True)
            self.app.rerender()

        def on_delete_click(_e) -> None:
            # gui/main_window_parts/devices_table_mixin.py::_quick_delete_selected()
            # — единственный путь удаления заказа в classic-GUI; в Flet его
            # не было вообще (workflow-найденный гэп) — ошибочный/тестовый
            # заказ, созданный через Flet, можно было удалить только
            # переключившись на классический интерфейс.
            def _confirm(_e2) -> None:
                self.app.page.pop_dialog()
                ok = self.app.db.delete_device(row["id"])
                if ok:
                    self.app.show_snackbar(f"Заказ №{row['order_number']} удалён")
                else:
                    self.app.show_snackbar("Не удалось удалить заказ", error=True)
                self.app.rerender()

            def _cancel(_e2) -> None:
                self.app.page.pop_dialog()

            self.app.page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Удаление заказа"),
                    content=ft.Text(f"Удалить заказ №{row['order_number']}?"),
                    actions=[
                        ft.TextButton("Отмена", on_click=_cancel),
                        ft.TextButton("Удалить", on_click=_confirm),
                    ],
                )
            )

        title = f"№{row['order_number']}  ·  {row['device_type']} {row['brand']} {row['model']}".strip()
        subtitle = f"{row['client_name']}  ·  {row['phone']}" if row["client_name"] else row["phone"]

        return ft.Container(
            ft.Row(
                [
                    ft.Container(width=4, bgcolor=status_color, border_radius=4, height=54),
                    ft.Column(
                        [
                            # max_lines=1 + overflow=ELLIPSIS: без них, когда
                            # окно достаточно узкое (в сумме фиксированных
                            # элементов строки — бейджа, суммы, dropdown'а
                            # шириной 190, 4 IconButton — легко набегает
                            # больше 900px), Flutter сжимает expand=True
                            # столбец до нулевой ширины, и Text без явного
                            # ограничения переносит КАЖДЫЙ символ на свою
                            # строку — карточка заказа раздувается на весь
                            # экран (живой прогон: обычное окно 900px,
                            # список заказов становится нечитаемым).
                            #
                            # Фикс в два шага: (1) max_lines/overflow сами
                            # по себе только меняют "как рвётся текст" — при
                            # width=0 текст просто исчезает, а не рвётся, что
                            # немногим лучше; (2) поэтому здесь ФИКСИРОВАННАЯ
                            # ширина вместо expand=True, а весь Row ниже —
                            # scroll=ft.ScrollMode.AUTO, так что на узких
                            # окнах карточка скроллится по горизонтали
                            # целиком, а не сжимает текст до нуля.
                            ft.Text(
                                title, size=14, weight=ft.FontWeight.W_600,
                                color=c["text_primary"], max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                subtitle, size=12, color=c["text_secondary"],
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=2, width=240,
                    ),
                    ft.Container(
                        ft.Text(row["priority"], size=11, color="white"),
                        bgcolor=priority_color, border_radius=6, padding=ft.Padding(8, 3, 8, 3),
                    ),
                    ft.Text(f"{row['total_price']} ₽", size=14, weight=ft.FontWeight.W_600,
                            color=c["text_primary"], width=100, text_align=ft.TextAlign.RIGHT),
                    ft.Dropdown(
                        # 190 обрезало самую длинную легаси-метку ("Готов
                        # (устаревший статус)") и даже штатный "Ожидание
                        # запчастей" — по просьбе пользователя расширено;
                        # card_row теперь scroll=ft.ScrollMode.AUTO, так что
                        # рост этой ширины не возвращает баг сжатия текста
                        # на узких окнах (см. коммит про layout narrow-width).
                        value=row["status"], width=230, dense=True,
                        options=_status_options(row["status"]),
                        on_select=on_status_change,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DESCRIPTION_OUTLINED, tooltip="Печать акта приёма",
                        on_click=lambda _e, r=row: _print_act(self.app, r, "receipt"),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.BUILD_OUTLINED, tooltip="Печать акта выполненных работ",
                        on_click=lambda _e, r=row: _print_act(self.app, r, "completion"),
                    ),
                    ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip="Открыть", on_click=on_edit),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE, tooltip="Удалить заказ",
                        icon_color=c["error"], on_click=on_delete_click,
                    ),
                ],
                spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
            ),
            bgcolor=c["bg_card"], border_radius=10, padding=ft.Padding(14, 10, 14, 10),
            border=theme.card_border(c["border"]),
        )

    # ── форма создания/редактирования ───────────────────────

    def _render_form(self) -> ft.Control:
        c = self.app.colors
        db = self.app.db
        editing = self.editing_id is not None
        existing = db.get_device(self.editing_id) if editing else None
        if editing and existing is None:
            self.app.show_snackbar("Заказ не найден — возможно, уже удалён.", error=True)
            self.mode = "list"
            return self._render_list()

        order_preview = existing["order_number"] if existing else str(db.peek_next_order_number())

        device_type_value = (existing or {}).get("device_type", "")
        brand_value = (existing or {}).get("brand", "")
        f_device_type = ft.Dropdown(
            label="Тип устройства", value=device_type_value,
            options=_dropdown_options_with_fallback(
                device_type_value, db.get_dict_values("device_types"), "нет в справочнике"
            ),
        )
        f_brand = ft.Dropdown(
            label="Бренд", value=brand_value,
            options=_dropdown_options_with_fallback(
                brand_value, db.get_dict_values("brands"), "нет в справочнике"
            ),
        )
        f_model = ft.TextField(label="Модель", value=(existing or {}).get("model", ""))
        f_serial = ft.TextField(label="Серийный номер", value=(existing or {}).get("serial_number", ""))
        # min_lines/max_lines: multiline=True одной строкой рисуется как
        # обычное однострочное поле (высота не растёт под текст) — то же
        # для f_notes ниже. classic-GUI даёт под эти поля CTkTextbox(60px)/
        # (50px) под неисправность/заметки; здесь эквивалент — несколько
        # видимых строк, а не одна.
        f_defect = ft.TextField(
            label="Неисправность", value=(existing or {}).get("defect", ""),
            multiline=True, min_lines=3, max_lines=6,
        )
        f_client_name = ft.TextField(label="Имя клиента", value=(existing or {}).get("client_name", ""))
        f_phone = ft.TextField(label="Телефон", value=(existing or {}).get("phone", ""))
        f_price = ft.TextField(
            label="Стоимость", value=str((existing or {}).get("total_price_num", "") or ""),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        f_prepay = ft.TextField(
            label="Предоплата", value=str((existing or {}).get("prepayment_num", "") or ""),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        f_status = ft.Dropdown(
            label="Статус", value=(existing or {}).get("status", STATUSES[0]),
            options=_status_options((existing or {}).get("status", STATUSES[0])),
        )
        f_priority = ft.Dropdown(
            label="Приоритет", value=(existing or {}).get("priority", "Обычный"),
            options=_dropdown_options_with_fallback(
                (existing or {}).get("priority", "Обычный"), PRIORITIES, "нет в списке"
            ),
        )
        f_engineer = ft.TextField(label="Инженер", value=(existing or {}).get("engineer") or "")
        # .get("warranty", "") НЕ защищает от явного None — Device.warranty
        # nullable (в отличие от status/priority, у которых default на
        # уровне колонки), а device_to_row() всегда включает ключ "warranty"
        # (так что .get()'овский default вообще не срабатывает). Для записи
        # с warranty=None Dropdown получал бы value=None, не совпадающее ни
        # с одной опцией (пустая строка "" в WARRANTIES — не то же самое,
        # что None) — та же blank-Dropdown болезнь, что и у статуса/
        # приоритета, только раньше не проявлялась на данных с непустым
        # warranty (workflow-найденный баг).
        f_warranty = ft.Dropdown(
            label="Гарантия", value=(existing or {}).get("warranty") or "",
            options=_dropdown_options_with_fallback(
                (existing or {}).get("warranty") or "", WARRANTIES, "нет в списке"
            ),
        )
        f_notes = ft.TextField(
            label="Заметки", value=(existing or {}).get("notes", ""),
            multiline=True, min_lines=2, max_lines=5,
        )

        error_text = ft.Text("", color=c["error"], size=12)

        def on_cancel(_e) -> None:
            self.mode = "list"
            self.app.rerender()

        def on_save(_e) -> None:
            if not f_client_name.value.strip() or not f_phone.value.strip():
                error_text.value = "Укажите имя клиента и телефон."
                self.app.page.update()
                return

            device_data = {
                "order_number": order_preview,
                "device_type": f_device_type.value,
                "brand": f_brand.value,
                "model": f_model.value,
                "serial_number": f_serial.value,
                "defect": f_defect.value,
                "client_name": f_client_name.value,
                "client_status": (existing or {}).get("client_status", "Новый"),
                "phone": f_phone.value,
                "total_price": f_price.value or "0",
                "prepayment": f_prepay.value or "0",
                "status": f_status.value,
                "priority": f_priority.value,
                "engineer": f_engineer.value,
                "warranty": f_warranty.value or "",
                "notes": f_notes.value,
                # Эта форма не показывает completeness/appearance/expense/
                # фото/работы — но update_device()/_sync_photos()/
                # _sync_work_items() трактуют ОТСУТСТВИЕ ключа как "очистить
                # всё" (device_data.get(key, "") -> пустая строка -> все
                # существующие фото/работы удаляются). Пробрасываем текущие
                # значения без изменений, а не молчим о них.
                "completeness": (existing or {}).get("completeness", ""),
                "appearance": (existing or {}).get("appearance", ""),
                "expense": (existing or {}).get("expense", "0"),
                "work_items_json": (existing or {}).get("work_items", ""),
                "photos": (existing or {}).get("photos", ""),
            }

            if editing:
                device_data["_expected_version"] = existing.get("version")
                try:
                    ok = db.update_device(self.editing_id, device_data)
                except OptimisticLockError as exc:
                    error_text.value = str(exc)
                    self.app.page.update()
                    return
                if ok:
                    self.app.show_snackbar(f"Заказ №{order_preview} сохранён")
                else:
                    error_text.value = "Не удалось сохранить изменения."
                    self.app.page.update()
                    return
            else:
                # order_preview — это peek_next_order_number() (для превью в
                # заголовке формы), он НЕ увеличивает счётчик. Использовать
                # его как реальный order_number привело бы к тому, что два
                # заказа подряд, созданных через Flet, получали бы один и тот
                # же номер и падали на unique-ограничении devices.order_number
                # — реальный номер берём здесь, непосредственно перед
                # вставкой (та же точка, что и save_mixin.py в классическом
                # интерфейсе).
                real_order_number = str(db.get_next_order_number())
                device_data["order_number"] = real_order_number
                device_data["receipt_date"] = _now_str()
                device_data["completion_date"] = ""
                new_id = db.add_device(device_data)
                if new_id is None:
                    error_text.value = "Не удалось создать заказ."
                    self.app.page.update()
                    return
                self.app.show_snackbar(f"Заказ №{real_order_number} создан")

            self.mode = "list"
            self.app.rerender()

        title = f"Редактирование заказа №{order_preview}" if editing else f"Новый заказ №{order_preview}"

        form_card = ft.Container(
            ft.Column(
                [
                    ft.ResponsiveRow([
                        ft.Container(f_device_type, col={"sm": 12, "md": 4}),
                        ft.Container(f_brand, col={"sm": 12, "md": 4}),
                        ft.Container(f_model, col={"sm": 12, "md": 4}),
                    ]),
                    f_serial,
                    f_defect,
                    ft.Divider(color=c["border"]),
                    ft.ResponsiveRow([
                        ft.Container(f_client_name, col={"sm": 12, "md": 6}),
                        ft.Container(f_phone, col={"sm": 12, "md": 6}),
                    ]),
                    ft.ResponsiveRow([
                        ft.Container(f_price, col={"sm": 12, "md": 6}),
                        ft.Container(f_prepay, col={"sm": 12, "md": 6}),
                    ]),
                    ft.ResponsiveRow([
                        ft.Container(f_status, col={"sm": 12, "md": 4}),
                        ft.Container(f_priority, col={"sm": 12, "md": 4}),
                        ft.Container(f_warranty, col={"sm": 12, "md": 4}),
                    ]),
                    f_engineer,
                    f_notes,
                    error_text,
                    ft.Row(
                        [
                            ft.FilledButton("Сохранить", on_click=on_save, bgcolor=c["accent"]),
                            ft.OutlinedButton("Отмена", on_click=on_cancel),
                            *(
                                [
                                    ft.Container(expand=True),
                                    ft.OutlinedButton(
                                        "📄 Акт приёма",
                                        on_click=lambda _e: _print_act(self.app, existing, "receipt"),
                                    ),
                                    ft.OutlinedButton(
                                        "🔧 Акт выполненных работ",
                                        on_click=lambda _e: _print_act(self.app, existing, "completion"),
                                    ),
                                ]
                                if editing
                                else []
                            ),
                        ],
                        spacing=10,
                    ),
                ],
                spacing=14,
            ),
            bgcolor=c["bg_card"], border_radius=12, padding=24, border=theme.card_border(c["border"]),
        )

        return ft.Column(
            [
                ft.Text(title, size=22, weight=ft.FontWeight.BOLD, color=c["text_primary"]),
                ft.Container(height=16),
                form_card,
            ],
            spacing=0,
        )


def _now_str() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
