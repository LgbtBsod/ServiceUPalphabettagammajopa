"""Заказы: список, поиск, фильтр, создание/редактирование, смена статуса.

Использует те же методы Database, что и pwa/server.py (get_all_devices,
search_devices, get_devices_by_filters, add_device, update_device,
update_device_status) — тот же контракт данных, третий равноправный
потребитель одного и того же facade."""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import tempfile

import flet as ft

from database import OptimisticLockError
from database.models import WorkItem
from domain.constants import (
    PRIORITIES,
    STATUS_ISSUED,
    STATUSES,
    WARRANTIES,
    models_dict_type,
)
from utils.formatters import (
    generate_order_number,
    normalize_phone,
    parse_price_to_float,
)
from utils.messages import Msg
from utils.validators import validate_phone, validate_price

from . import theme
from .theme import PRIORITY_COLORS, STATUS_COLORS

_ALL = "Все"


def _tags_list(row: dict, key: str) -> list[str]:
    """Список текстов тегов из row[key] (JSON, [{"text": ..., ...}, ...]) —
    общий разбор и для defect_tags (неисправности устройства), и для
    order_tags (метки самого заказа); пусто, если ключ отсутствует/NULL
    (legacy-строка до соответствующей колонки) или список пуст ("[]")."""
    raw = row.get(key) or "[]"
    try:
        tags = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(tags, list):
        return []
    return [
        str(t.get("text", "")).strip()
        for t in tags
        if isinstance(t, dict) and str(t.get("text", "")).strip()
    ]


class _TagEditor:
    """Виджет «справочник-с-фолбэком на свободный текст + чипы с
    удалением» — общая механика для тегов-неисправностей
    (dict_type="defects", DeviceDefectRecord) и меток заказа
    (dict_type="order_tags", OrderTagRecord): оба — child-таблицы
    устройства с одинаковым dual-write-паттерном (см.
    database/facade/child_records_mixin.py), различается только
    справочник и подпись поля ввода."""

    def __init__(
        self, app, db, dict_type: str, label: str, initial_json: str, colors: dict
    ):
        self.app = app
        self.db = db
        self.dict_type = dict_type
        self.label = label
        self.colors = colors
        self.state: list[dict] = []
        # Workflow-найденный баг: без try/except невалидный JSON в колонке
        # (битая ручная правка БД, повреждённая запись) ронял диалог
        # прямо в конструкторе — и, что хуже, self.mode уже успевал стать
        # "form" ДО падения (см. on_edit), так что экран Заказов оставался
        # намертво сломан при каждом следующем открытии до перезапуска
        # процесса. Тот же guard, что уже есть у _tags_list() ниже —
        # только там достаточно было её впервые добавить, а не забыть тут.
        try:
            _tags = json.loads(initial_json or "[]")
        except (json.JSONDecodeError, TypeError):
            _tags = []
        if isinstance(_tags, list):
            for _tag in _tags:
                if isinstance(_tag, dict) and str(_tag.get("text", "")).strip():
                    self.state.append(
                        {
                            "text": str(_tag.get("text", "")).strip(),
                            "is_from_dictionary": bool(_tag.get("is_from_dictionary", False)),
                        }
                    )
        self.chips_row = ft.Row(wrap=True, spacing=6, run_spacing=6, data=f"tags:{dict_type}")
        # Контейнер, а не сам Dropdown — после добавления тега поле нужно
        # ОЧИСТИТЬ, а простановка .value/.text = "" плюс page.update()
        # визуально НЕ очищает уже введённый текст (живой прогон: Flutter-
        # виджет редактируемого Dropdown держит свой TextEditingController
        # и не подхватывает такое обновление). Пересоздаём Dropdown с нуля
        # вместо попытки очистить старый — см. add() ниже.
        self.input_container = ft.Container(content=self._build_input(), expand=True)
        self._refresh_chips()

    def _build_input(self) -> ft.Dropdown:
        return ft.Dropdown(
            label=self.label, editable=True, enable_filter=True,
            options=[_opt(v) for v in self.db.get_dict_values(self.dict_type)],
        )

    def _refresh_chips(self) -> None:
        c = self.colors
        self.chips_row.controls = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text(tag["text"], size=12, color=c["text_primary"]),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE, icon_size=14, width=24, height=24,
                            tooltip="Удалить тег",
                            on_click=lambda _e, i=i: self._remove(i),
                        ),
                    ],
                    spacing=2, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=c["bg_card"], border=theme.card_border(c["border"]),
                border_radius=16, padding=ft.Padding(10, 2, 2, 2),
            )
            for i, tag in enumerate(self.state)
        ]

    def _remove(self, i: int) -> None:
        del self.state[i]
        self._refresh_chips()
        self.app.page.update()

    def add(self, _e=None) -> None:
        text = _editable_dropdown_value(
            self.input_container.content, "нет в справочнике"
        ).strip()
        if not text or any(t["text"] == text for t in self.state):
            return
        dict_values = self.db.get_dict_values(self.dict_type)
        self.state.append({"text": text, "is_from_dictionary": text in dict_values})
        self.input_container.content = self._build_input()
        self._refresh_chips()
        self.app.page.update()

    def row(self) -> ft.Control:
        return ft.Row(
            [
                self.input_container,
                ft.IconButton(
                    icon=ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="Добавить тег",
                    data=f"add:{self.dict_type}", on_click=self.add,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def to_json(self) -> str:
        return json.dumps(self.state, ensure_ascii=False)


class _WorkItemsEditor:
    """Позиции выполненных работ (описание + цена + количество) в форме
    заказа Flet — было ПОЛНОСТЬЮ отсутствующей фичёй (парность с
    classic-GUI, где это gui/widgets/work_table.py::WorkItemsTable +
    database/models.py::WorkItemsManager): без списка работ Flet-заказ не
    мог сформировать корректный акт выполненных работ (reports/ читает
    именно device.work_items) и стоимость приходилось вбивать вручную
    одной суммой, не отражая реальный состав работ. Тот же JSON-контракт,
    что и classic-GUI/facade (database/facade/child_records_mixin.py::
    _sync_work_items): [{"description": str, "price": str, "quantity": int}]."""

    def __init__(self, app, initial_json: str, colors: dict):
        self.app = app
        self.colors = colors
        self.items: list[dict] = []
        try:
            _items = json.loads(initial_json or "[]")
        except (json.JSONDecodeError, TypeError):
            _items = []
        if isinstance(_items, list):
            for it in _items:
                if not isinstance(it, dict):
                    continue
                # WorkItem.from_dict() — общий с classic GUI разбор
                # quantity (см. database/models.py::_safe_int/_clamp_quantity):
                # раньше здесь был независимый parse, который клэмпил
                # 0/отрицательное количество к 1 молча и БЕЗ ЛОГА при каждой
                # загрузке формы, тогда как classic GUI (WorkItem.total_price())
                # считал такую позицию как 0 ₽ — один и тот же сохранённый
                # заказ показывал разный итог в зависимости от того, в каком
                # интерфейсе он открыт (workflow-найденное расхождение).
                parsed = WorkItem.from_dict(it)
                desc = parsed.description.strip()
                if not desc:
                    continue
                self.items.append(
                    {"description": desc, "price": str(parsed.price).strip(), "quantity": parsed.quantity}
                )

        self.rows_column = ft.Column(spacing=4)
        self.total_text = ft.Text("", size=13, weight=ft.FontWeight.W_600)
        self.desc_field = ft.TextField(label="Описание работы", expand=True)
        self.price_field = ft.TextField(
            label="Цена", width=110, keyboard_type=ft.KeyboardType.NUMBER
        )
        self.qty_field = ft.TextField(
            label="Кол-во", width=90, value="1", keyboard_type=ft.KeyboardType.NUMBER
        )
        self._refresh()

    def _row_total(self, item: dict) -> float:
        return parse_price_to_float(item["price"]) * item["quantity"]

    def total(self) -> float:
        return sum(self._row_total(it) for it in self.items)

    def _refresh(self) -> None:
        c = self.colors
        self.rows_column.controls = [
            ft.Container(
                ft.Row(
                    [
                        ft.Text(it["description"], size=13, color=c["text_primary"], expand=True),
                        ft.Text(
                            f"{it['price']} ₽ × {it['quantity']} = {self._row_total(it):.0f} ₽",
                            size=12, color=c["text_secondary"],
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE, icon_size=14, width=24, height=24,
                            tooltip="Удалить позицию",
                            on_click=lambda _e, i=i: self._remove(i),
                        ),
                    ],
                    spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=c["bg_card"], border=theme.card_border(c["border"]),
                border_radius=8, padding=ft.Padding(10, 4, 4, 4),
            )
            for i, it in enumerate(self.items)
        ]
        self.total_text.value = f"Итого по работам: {self.total():.0f} ₽" if self.items else ""

    def _remove(self, i: int) -> None:
        del self.items[i]
        self._refresh()
        self.app.page.update()

    def add(self, _e=None) -> None:
        # Та же валидация, что classic GUI's WorkItemDialog.save() — раньше
        # эта форма молча клэмпила пустое/некорректное количество к 1 и не
        # проверяла цену вообще, вместо того чтобы явно отказать, как уже
        # делает classic (workflow-найденное расхождение).
        desc = (self.desc_field.value or "").strip()
        if not desc:
            self.app.show_snackbar(Msg.WorkItem.DESCRIPTION_REQUIRED, error=True)
            return
        price = (self.price_field.value or "").strip()
        if not price:
            self.app.show_snackbar(Msg.WorkItem.PRICE_REQUIRED, error=True)
            return
        if not validate_price(price):
            self.app.show_snackbar(Msg.WorkItem.PRICE_FORMAT_INVALID, error=True)
            return
        try:
            qty = int((self.qty_field.value or "1").strip())
        except ValueError:
            qty = 0  # ниже отклонится тем же путём, что и явный 0/отрицательный ввод
        if qty < 1:
            self.app.show_snackbar(Msg.WorkItem.QUANTITY_MIN_ONE, error=True)
            return
        self.items.append({"description": desc, "price": price, "quantity": qty})
        self.desc_field.value = ""
        self.price_field.value = ""
        self.qty_field.value = "1"
        self._refresh()
        self.app.page.update()

    def row(self) -> ft.Control:
        return ft.Row(
            [
                self.desc_field,
                self.price_field,
                self.qty_field,
                ft.IconButton(
                    icon=ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="Добавить работу",
                    data="add:work_items", on_click=self.add,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def to_json(self) -> str:
        return json.dumps(self.items, ensure_ascii=False)


class _PhotosEditor:
    """Фотографии устройства в форме заказа Flet — ещё одна ранее
    отсутствовавшая фича (паритет с gui/dialogs/device_form_parts/
    photos_mixin.py): без неё Flet-заказ нельзя было задокументировать
    фотографиями состояния/дефектов устройства на приёме.

    pick_files(with_data=True) отдаёт содержимое файла прямо в ответе
    (тот же приём, что ActBuilderView._on_import_click в
    views_act_builder.py) — не нужен отдельный upload_dir/upload_url,
    которые нужны были бы для потокового аплоада большого файла. Каждый
    выбранный файл пишется во временный файл и передаётся в
    managers/photo_manager.py::PhotoManager.save_photo() — тот же
    контракт (source_path на диске), что и у classic-GUI, только источник
    там — реальный путь из filedialog, а здесь — временный файл с
    байтами из браузера."""

    def __init__(
        self, app, photo_manager, file_picker: ft.FilePicker,
        client_name_field: ft.TextField, phone_field: ft.TextField,
        order_number: str, initial_csv: str, colors: dict,
    ):
        self.app = app
        self.photo_manager = photo_manager
        self.file_picker = file_picker
        self.client_name_field = client_name_field
        self.phone_field = phone_field
        self.order_number = order_number
        self.colors = colors
        self.paths: list[str] = [p.strip() for p in (initial_csv or "").split(",") if p.strip()]
        self.thumbnails_row = ft.Row(wrap=True, spacing=8, run_spacing=8)
        self._refresh()

    @staticmethod
    def _thumb_base64(path: str) -> str | None:
        try:
            from PIL import Image

            with Image.open(path) as img:
                img.thumbnail((80, 80))
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=70)
                return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None

    def _refresh(self) -> None:
        c = self.colors
        controls = []
        for i, path in enumerate(self.paths):
            b64 = self._thumb_base64(path)
            thumb = (
                ft.Image(
                    src_base64=b64, width=80, height=80,
                    fit=ft.ImageFit.COVER, border_radius=8,
                )
                if b64
                else ft.Container(
                    width=80, height=80, bgcolor=c["bg_card"], border_radius=8,
                    border=theme.card_border(c["border"]),
                )
            )
            controls.append(
                ft.Column(
                    [
                        thumb,
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE, icon_size=16, width=28, height=28,
                            tooltip="Удалить фото",
                            on_click=lambda _e, i=i: self._remove(i),
                        ),
                    ],
                    spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        self.thumbnails_row.controls = controls

    def _remove(self, i: int) -> None:
        path = self.paths.pop(i)
        with contextlib.suppress(Exception):
            self.photo_manager.delete_photos([path])
        self._refresh()
        self.app.page.update()

    def add(self, _e=None) -> None:
        async def _run() -> None:
            client_name = (self.client_name_field.value or "").strip()
            client_phone = (self.phone_field.value or "").strip()
            if not client_name or not client_phone:
                self.app.show_snackbar(
                    "Сначала укажите имя клиента и телефон", error=True
                )
                return
            try:
                files = await self.file_picker.pick_files(
                    dialog_title="Выберите фотографии",
                    file_type=ft.FilePickerFileType.IMAGE,
                    allow_multiple=True,
                    with_data=True,
                )
            except Exception as e:
                self.app.show_snackbar(f"Не удалось открыть выбор файлов: {e}", error=True)
                return
            if not files:
                return

            saved = 0
            for picked in files:
                if not picked.bytes:
                    continue
                suffix = os.path.splitext(picked.name)[1] or ".jpg"
                fd, tmp_path = tempfile.mkstemp(suffix=suffix)
                try:
                    with os.fdopen(fd, "wb") as out:
                        out.write(picked.bytes)
                    dest = self.photo_manager.save_photo(
                        tmp_path, client_name, client_phone, self.order_number, "device"
                    )
                    if dest:
                        self.paths.append(dest)
                        saved += 1
                finally:
                    with contextlib.suppress(OSError):
                        os.remove(tmp_path)

            if saved:
                self._refresh()
                self.app.show_snackbar(f"Добавлено фото: {saved}")
            else:
                self.app.show_snackbar("Не удалось сохранить фото", error=True)
            self.app.page.update()

        self.app.page.run_task(_run)

    def row(self) -> ft.Control:
        return ft.OutlinedButton("📷 Добавить фото", on_click=self.add)

    def to_csv(self) -> str:
        return ",".join(self.paths)


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
    печать оттуда доступна как для любого другого документа.

    on_click сам по себе синхронный (Flet этого требует) — вся реальная
    работа идёт внутри async _run(), запущенного через page.run_task(), а
    генерация PDF/запуск системного просмотрщика — через asyncio.to_thread()
    (оба блокирующие). Раньше всё это выполнялось синхронно прямо в
    обработчике клика — печать акта замораживала ВСЮ страницу этой
    браузерной сессии (никакой другой клик/обновление не обрабатывались) на
    время генерации PDF и запуска внешнего процесса, хотя рядом в этом же
    файле add() (загрузка фото) уже показывает правильный паттерн
    (workflow-найденное расхождение)."""

    async def _run() -> None:
        import asyncio
        import contextlib
        import os
        import subprocess
        import sys
        import tempfile

        from reports.report_editor import load_template_data
        from reports.report_renderer import ActPDFGenerator

        local_device = device
        try:
            if act_type == "completion" and local_device.get("work_items"):
                from database.models import WorkItemsManager

                work_manager = WorkItemsManager()
                work_manager.from_json(local_device["work_items"])
                local_device = {
                    **local_device,
                    "completed_work": work_manager.get_description_summary(),
                }

            template = load_template_data(act_type)
            gen = ActPDFGenerator(template_data=template)

            # Каждый клик по печати создавал НОВЫЙ temp PDF и никогда не
            # удалял ни один из них — репозиторий тем самым копил по одному
            # осиротевшему файлу на каждую печать за всё время работы
            # процесса (workflow-найденный гэп). Полный предпросмотр/
            # редактирование, как в classic-GUI (gui/dialogs/act_preview.py),
            # — отдельная большая фича; здесь, как первый шаг, удаляем
            # ПРЕДЫДУЩИЙ temp-файл прямо перед созданием следующего — тот же
            # приём, что и в act_preview.py::render_pdf_preview()
            # (contextlib.suppress(OSError), т.к. системный просмотрщик мог
            # ещё держать файл открытым).
            last_path = getattr(app, "_last_act_print_path", None)
            if last_path and os.path.exists(last_path):
                with contextlib.suppress(OSError):
                    os.remove(last_path)

            fd, path = tempfile.mkstemp(
                suffix=f"_{act_type}_{local_device.get('order_number', '')}.pdf"
            )
            os.close(fd)
            app._last_act_print_path = path

            def _generate() -> bool:
                return (
                    gen.generate_completion_pdf(path, local_device)
                    if act_type == "completion"
                    else gen.generate_receipt_pdf(path, local_device)
                )

            ok = await asyncio.to_thread(_generate)
            if not ok or not os.path.exists(path):
                app.show_snackbar(Msg.Act.GENERATE_FAILED, error=True)
                return

            def _open_in_system_viewer() -> None:
                if sys.platform == "win32":
                    os.startfile(path)
                elif sys.platform == "darwin":
                    subprocess.run(["open", path], check=False)
                else:
                    subprocess.run(["xdg-open", path], check=False)

            await asyncio.to_thread(_open_in_system_viewer)
            app.show_snackbar(Msg.Act.PRINTED)

            # Печать акта выполненных работ = выдача устройства клиенту —
            # тот же рабочий процесс, что и в classic-GUI (gui/main_window_
            # parts/acts_mixin.py::print_completion_act()). Flet-версия
            # раньше вообще не трогала статус: заказы, выданные через Flet,
            # оставались в прежнем статусе, пока сотрудник не менял его
            # вручную — искажая дашборд/финансовые цифры, завязанные на
            # статус (workflow-найденный гэп).
            if act_type == "completion" and local_device.get("status") != STATUS_ISSUED:
                _ask_mark_issued(app, local_device)
        except Exception as e:
            app.show_snackbar(Msg.Act.PRINT_FAILED.format(error=e), error=True)

    app.page.run_task(_run)


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


def _editable_dropdown_value(field: ft.Dropdown, legacy_label: str) -> str:
    """Читает текущее значение editable=True Dropdown (см. f_model) —
    свободно напечатанный текст, а НЕ обязательно то, что выбрано из
    списка. field.value — ключ ПОСЛЕДНЕГО выбранного option (обновляется
    только через on_select) — если пользователь напечатал текст, которого
    нет ни в одном option, ничего не выбирается, on_select не срабатывает,
    и .value молча остаётся тем, чем было ДО печати (пустая строка у
    нового заказа, старое значение при редактировании) — форма тихо
    сохраняла бы ПУСТУЮ/СТАРУЮ модель вместо только что введённой
    (workflow-найденный баг, живо воспроизведён). field.text — то, что
    реально показано в текстовом поле, всегда актуально независимо от
    источника (печать или выбор) — кроме случая выбора спец-опции
    "легаси"-значения (_dropdown_options_with_fallback выше), чей текст
    содержит поясняющий суффикс " (legacy_label)", не входящий в само
    значение — отрезаем его."""
    text = (field.text or "").strip()
    suffix = f" ({legacy_label})"
    if text.endswith(suffix):
        return text[: -len(suffix)]
    return text or (field.value or "")


def _status_options(current_value: str) -> list[ft.dropdown.Option]:
    return _dropdown_options_with_fallback(current_value, STATUSES, "устаревший статус")


class OrdersView:
    def __init__(self, app):
        self.app = app
        self.mode = "list"  # "list" | "form"
        self.editing_id: int | None = None
        self.search_text = ""
        self.status_filter = _ALL
        # Персистентный на весь OrdersView (не пересоздаётся на каждый
        # _render_form()) — тот же паттерн, что ActBuilderView._file_picker
        # в views_act_builder.py: FilePicker — service-контрол, повторная
        # регистрация в page.services на каждый рендер формы копила бы дубли.
        self._photo_picker = ft.FilePicker()
        self.app.page.services.append(self._photo_picker)

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
        defect_tags_summary = ", ".join(_tags_list(row, "defect_tags"))
        order_tags_list = _tags_list(row, "order_tags")

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
                            *(
                                [
                                    ft.Text(
                                        f"🔧 {defect_tags_summary}", size=11,
                                        color=c["text_secondary"], max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS, italic=True,
                                    )
                                ]
                                if defect_tags_summary
                                else []
                            ),
                            *(
                                [
                                    ft.Row(
                                        [
                                            ft.Container(
                                                ft.Text(t, size=10, color="white"),
                                                bgcolor=c["accent"], border_radius=8,
                                                padding=ft.Padding(6, 1, 6, 1),
                                            )
                                            for t in order_tags_list
                                        ],
                                        wrap=True, spacing=4, run_spacing=4,
                                    )
                                ]
                                if order_tags_list
                                else []
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

        order_preview = (
            existing["order_number"]
            if existing
            else generate_order_number(db.peek_next_order_number())
        )

        device_type_value = (existing or {}).get("device_type", "")
        brand_value = (existing or {}).get("brand", "")
        f_device_type = ft.Dropdown(
            label="Тип устройства", value=device_type_value,
            options=_dropdown_options_with_fallback(
                device_type_value, db.get_dict_values("device_types"), "нет в справочнике"
            ),
        )
        model_value = (existing or {}).get("model", "")
        # editable=True — в отличие от f_device_type/f_brand (закрытый
        # список), "Модель" должна поддерживать и выбор из справочника, и
        # свободный ввод (моделей у каждого бренда тысячи, справочник
        # заведомо неполон и растёт по мере ввода реальных заказов — явный
        # запрос пользователя "не убираем ручной ввод"). enable_filter
        # заодно даёт автодополнение по мере печати.
        f_model = ft.Dropdown(
            label="Модель", value=model_value, editable=True, enable_filter=True,
            options=_dropdown_options_with_fallback(
                model_value, db.get_dict_values(models_dict_type(brand_value)), "нет в справочнике"
            ),
        )

        def on_brand_change(e: ft.ControlEvent) -> None:
            # Модели — справочник ОТДЕЛЬНО НА КАЖДЫЙ БРЕНД (см.
            # domain.constants.models_dict_type) — при смене бренда переcчитываем список
            # подсказок модели, не трогая уже введённый пользователем текст.
            new_brand = e.control.value
            f_model.options = _dropdown_options_with_fallback(
                f_model.text or f_model.value,
                db.get_dict_values(models_dict_type(new_brand)),
                "нет в справочнике",
            )
            self.app.page.update()

        f_brand = ft.Dropdown(
            label="Бренд", value=brand_value, on_select=on_brand_change,
            options=_dropdown_options_with_fallback(
                brand_value, db.get_dict_values("brands"), "нет в справочнике"
            ),
        )
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

        # Теги-неисправности (DeviceDefectRecord) — ДОПОЛНЯЮТ f_defect выше
        # (свободный текст остаётся основным описанием), не заменяют его:
        # несколько коротких структурированных отметок на устройство, из
        # справочника "defects" или введённых вручную (is_from_dictionary
        # тогда False — задел под будущую аналитику, где ручные значения
        # бакетируются в общую группу "Прочее"). См. класс _TagEditor выше —
        # order_tag_editor ниже (метки самого заказа) использует ту же
        # механику с другим справочником.
        defect_tag_editor = _TagEditor(
            self.app, db, "defects", "Добавить тег неисправности",
            (existing or {}).get("defect_tags") or "[]", c,
        )

        # Метки заказа (OrderTagRecord) — НЕ описание поломки, произвольная
        # классификация самого заказа (VIP, срочно, повторное обращение...).
        order_tag_editor = _TagEditor(
            self.app, db, "order_tags", "Добавить тег заказа",
            (existing or {}).get("order_tags") or "[]", c,
        )

        # Позиции работ (WorkItemsManager) — параллель classic-GUI. Итог по
        # работам, если они есть, становится стоимостью заказа (та же
        # логика, что gui/dialogs/device_form_parts/save_mixin.py: сумма
        # работ приоритетнее вручную введённой цены).
        work_items_editor = _WorkItemsEditor(
            self.app, (existing or {}).get("work_items") or "[]", c
        )

        f_client_name = ft.TextField(label="Имя клиента", value=(existing or {}).get("client_name", ""))
        f_phone = ft.TextField(label="Телефон", value=(existing or {}).get("phone", ""))

        # Фотографии устройства — параллель classic-GUI (см. класс
        # _PhotosEditor выше). "new" — тот же сентинел, что classic-GUI
        # использует для ещё не сохранённого заказа (order_number станет
        # известен только после реального сохранения).
        photos_editor = _PhotosEditor(
            self.app, self.app.core.get_module_api("photos"), self._photo_picker,
            f_client_name, f_phone,
            (existing or {}).get("order_number") if existing else "new",
            (existing or {}).get("photos", ""), c,
        )

        f_price = ft.TextField(
            label="Стоимость",
            value=(
                str(int(work_items_editor.total()))
                if work_items_editor.items
                else str((existing or {}).get("total_price_num", "") or "")
            ),
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

        def _fail(message: str) -> None:
            error_text.value = message
            self.app.page.update()

        def on_save(_e) -> None:
            # Та же обязательность/формат, что и классический GUI
            # (gui/dialogs/device_form_parts/save_mixin.py::save()) — этот
            # путь раньше требовал только имя клиента и телефон, позволяя
            # создать заказ через Flet с пустыми типом/моделью/неисправностью
            # и неотформатированным (не normalize_phone()) телефоном, чего
            # классический GUI никогда не допускал (workflow-найденный баг).
            model_value = _editable_dropdown_value(f_model, "нет в справочнике")
            if not (f_device_type.value or "").strip():
                _fail(Msg.Order.DEVICE_TYPE_REQUIRED)
                return
            if not model_value.strip():
                _fail(Msg.Order.MODEL_REQUIRED)
                return
            if not (f_defect.value or "").strip():
                _fail(Msg.Order.DEFECT_REQUIRED)
                return
            if not f_client_name.value.strip():
                _fail(Msg.Order.CLIENT_NAME_REQUIRED)
                return
            if not f_phone.value.strip():
                _fail(Msg.Order.PHONE_REQUIRED)
                return
            if not validate_phone(f_phone.value):
                _fail(Msg.Order.PHONE_FORMAT_INVALID)
                return

            total_price_value = (
                str(int(work_items_editor.total()))
                if work_items_editor.items
                else (f_price.value or "0")
            )
            if not validate_price(total_price_value):
                _fail(Msg.Order.PRICE_FORMAT_INVALID)
                return
            if f_prepay.value and not validate_price(f_prepay.value):
                _fail(Msg.Order.PREPAYMENT_FORMAT_INVALID)
                return

            device_data = {
                "order_number": order_preview,
                "device_type": f_device_type.value,
                "brand": f_brand.value,
                "model": model_value,
                "serial_number": f_serial.value,
                "defect": f_defect.value,
                "defect_tags_json": defect_tag_editor.to_json(),
                "order_tags_json": order_tag_editor.to_json(),
                "client_name": f_client_name.value,
                "client_status": (existing or {}).get("client_status", "Новый"),
                "phone": normalize_phone(f_phone.value),
                # Сумма по позициям работ приоритетнее ручного ввода — та же
                # логика, что и в classic-GUI (save_mixin.py: wm_total > 0
                # побеждает total_price_entry).
                "total_price": total_price_value,
                "prepayment": f_prepay.value or "0",
                "status": f_status.value,
                "priority": f_priority.value,
                "engineer": f_engineer.value,
                "warranty": f_warranty.value or "",
                "notes": f_notes.value,
                # Эта форма не показывает completeness/appearance/expense —
                # но update_device() трактует ОТСУТСТВИЕ ключа как "очистить
                # всё" (device_data.get(key, "") -> пустая строка).
                # Пробрасываем текущие значения без изменений, а не молчим
                # о них.
                "completeness": (existing or {}).get("completeness", ""),
                "appearance": (existing or {}).get("appearance", ""),
                "expense": (existing or {}).get("expense", "0"),
                "work_items_json": work_items_editor.to_json(),
                "photos": photos_editor.to_csv(),
            }

            if editing:
                device_data["_expected_version"] = existing.get("version")
                try:
                    ok = db.update_device(self.editing_id, device_data)
                except OptimisticLockError as exc:
                    # Та же объясняющая формулировка, что классический GUI
                    # показывает при том же конфликте (save_mixin.py) — не
                    # только сырой текст исключения, который сам по себе не
                    # объясняет пользователю, что вообще произошло.
                    _fail(f"{Msg.Lock.OPTIMISTIC_CONFLICT}\n\n{exc}")
                    return
                if ok:
                    self.app.show_snackbar(Msg.Order.SAVED.format(order_number=order_preview))
                else:
                    _fail(Msg.Order.UPDATE_FAILED)
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
                real_order_number = generate_order_number(db.get_next_order_number())
                device_data["order_number"] = real_order_number
                device_data["receipt_date"] = _now_str()
                device_data["completion_date"] = ""
                new_id = db.add_device(device_data)
                if new_id is None:
                    _fail(Msg.Order.CREATE_FAILED)
                    return
                self.app.show_snackbar(Msg.Order.CREATED.format(order_number=real_order_number))

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
                    defect_tag_editor.row(),
                    defect_tag_editor.chips_row,
                    ft.Divider(color=c["border"]),
                    ft.ResponsiveRow([
                        ft.Container(f_client_name, col={"sm": 12, "md": 6}),
                        ft.Container(f_phone, col={"sm": 12, "md": 6}),
                    ]),
                    ft.Text("Фото", size=13, weight=ft.FontWeight.W_600, color=c["text_secondary"]),
                    photos_editor.thumbnails_row,
                    photos_editor.row(),
                    ft.Divider(color=c["border"]),
                    ft.Text("Работы", size=13, weight=ft.FontWeight.W_600, color=c["text_secondary"]),
                    work_items_editor.rows_column,
                    work_items_editor.row(),
                    work_items_editor.total_text,
                    ft.Divider(color=c["border"]),
                    ft.ResponsiveRow([
                        ft.Container(f_price, col={"sm": 12, "md": 6}),
                        ft.Container(f_prepay, col={"sm": 12, "md": 6}),
                    ]),
                    ft.ResponsiveRow([
                        ft.Container(f_status, col={"sm": 12, "md": 4}),
                        ft.Container(f_priority, col={"sm": 12, "md": 4}),
                        ft.Container(f_warranty, col={"sm": 12, "md": 4}),
                    ]),
                    order_tag_editor.row(),
                    order_tag_editor.chips_row,
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
