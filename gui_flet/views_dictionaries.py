"""Управление справочниками (бренды, типы устройств, модели, инженеры, ...) —
Flet-эквивалент gui/dialogs/dictionaries.py.

Тот же generic dict_type-driven подход, что и в классическом интерфейсе
(domain.constants.DICTIONARY_TYPES описывает набор категорий и их значения
по умолчанию), тот же facade
(db.get_all_dict_items/add_dict_value/update_dict_value/delete_dict_value,
database/facade/dictionaries_mixin.py) — обе оболочки читают/пишут одни и
те же строки таблицы `dictionaries`."""

from __future__ import annotations

import flet as ft

from domain.constants import DICTIONARY_TYPES

from . import theme


class DictionariesView:
    def __init__(self, app):
        self.app = app
        self.current_type: str = next(iter(DICTIONARY_TYPES))
        self.selected_item_id: int | None = None

    def render(self) -> ft.Control:
        c = self.app.colors
        db = self.app.db
        config = DICTIONARY_TYPES[self.current_type]

        def on_type_change(e: ft.ControlEvent) -> None:
            self.current_type = e.control.value
            self.selected_item_id = None
            self.app.rerender()

        type_selector = ft.Dropdown(
            label="Справочник", value=self.current_type, width=280, dense=True,
            options=[
                ft.dropdown.Option(key=k, text=f"{cfg['icon']} {cfg['name']}")
                for k, cfg in DICTIONARY_TYPES.items()
            ],
            on_select=on_type_change,
        )

        items = db.get_all_dict_items(self.current_type)
        selected_item = next(
            (i for i in items if i["id"] == self.selected_item_id), None
        )

        value_field = ft.TextField(
            label="Значение*",
            value=(selected_item or {}).get("value", ""),
        )
        info_field = ft.TextField(
            label="Доп. информация",
            value=(selected_item or {}).get("additional_info") or "",
        )

        def on_row_click(item_id: int):
            def _handler(_e) -> None:
                self.selected_item_id = item_id
                self.app.rerender()

            return _handler

        def on_save(_e) -> None:
            value = value_field.value.strip()
            if not value:
                self.app.show_snackbar("Введите значение", error=True)
                return
            info = info_field.value.strip()
            if self.selected_item_id is not None:
                ok = db.update_dict_value(self.selected_item_id, value, info)
                message = "Значение обновлено" if ok else "Не удалось обновить значение"
            else:
                ok = db.add_dict_value(self.current_type, value, info)
                message = "Значение добавлено" if ok else "Такое значение уже существует"
            self.app.show_snackbar(message, error=not ok)
            if ok:
                self.selected_item_id = None
            self.app.rerender()

        def on_delete_confirmed(_e) -> None:
            self.app.page.pop_dialog()
            ok = db.delete_dict_value(self.selected_item_id)
            self.selected_item_id = None
            self.app.show_snackbar(
                "Элемент удалён" if ok else "Не удалось удалить элемент", error=not ok
            )
            self.app.rerender()

        def on_delete_cancelled(_e) -> None:
            self.app.page.pop_dialog()

        def on_delete_click(_e) -> None:
            if self.selected_item_id is None:
                self.app.show_snackbar("Выберите элемент для удаления", error=True)
                return
            self.app.page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Удаление"),
                    content=ft.Text("Удалить выбранный элемент справочника?"),
                    actions=[
                        ft.TextButton("Отмена", on_click=on_delete_cancelled),
                        ft.TextButton("Удалить", on_click=on_delete_confirmed),
                    ],
                )
            )

        def on_clear_click(_e) -> None:
            self.selected_item_id = None
            self.app.rerender()

        if items:
            rows: list[ft.Control] = [
                ft.ListTile(
                    title=ft.Text(item["value"], size=13, color=c["text_primary"]),
                    subtitle=(
                        ft.Text(item["additional_info"], size=11, color=c["text_secondary"])
                        if item.get("additional_info")
                        else None
                    ),
                    selected=item["id"] == self.selected_item_id,
                    selected_tile_color=c["accent"],
                    on_click=on_row_click(item["id"]),
                    dense=True,
                )
                for item in items
            ]
        else:
            rows = [
                ft.Container(
                    ft.Text(
                        "В этом справочнике пока нет значений.",
                        size=12, color=c["text_secondary"],
                    ),
                    padding=20,
                )
            ]

        list_card = ft.Container(
            ft.Column(
                [
                    ft.Text(
                        f"{config['icon']} {config['name']}", size=14,
                        weight=ft.FontWeight.W_600, color=c["text_primary"],
                    ),
                    ft.Container(height=8),
                    ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO, height=400),
                ],
            ),
            bgcolor=c["bg_card"], border_radius=12, padding=16, expand=True,
            border=theme.card_border(c["border"]),
        )

        edit_card = ft.Container(
            ft.Column(
                [
                    ft.Text(
                        "✏️ Редактирование" if selected_item else "➕ Новое значение",
                        size=14, weight=ft.FontWeight.W_600, color=c["text_primary"],
                    ),
                    ft.Container(height=8),
                    value_field,
                    info_field,
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ft.FilledButton(
                                "💾 Сохранить" if selected_item else "➕ Добавить",
                                on_click=on_save,
                            ),
                            ft.OutlinedButton("✖ Очистить", on_click=on_clear_click),
                            ft.OutlinedButton(
                                "🗑 Удалить", on_click=on_delete_click,
                                disabled=self.selected_item_id is None,
                            ),
                        ],
                        wrap=True, spacing=8,
                    ),
                ],
            ),
            bgcolor=c["bg_card"], border_radius=12, padding=16, expand=True,
            border=theme.card_border(c["border"]),
        )

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "Справочники", size=24, weight=ft.FontWeight.BOLD,
                            color=c["text_primary"],
                        ),
                        ft.Container(expand=True),
                        type_selector,
                    ],
                ),
                ft.Container(height=16),
                ft.ResponsiveRow(
                    [
                        ft.Container(list_card, col={"sm": 12, "md": 7}),
                        ft.Container(edit_card, col={"sm": 12, "md": 5}),
                    ],
                    spacing=16, run_spacing=16,
                ),
            ],
            spacing=0,
        )
