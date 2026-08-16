#!/usr/bin/env python3
"""Skeleton-loading + busy-индикатор — переиспользуемые GUI-примитивы для
фоновой загрузки данных (см. AUDIT_REPORT_v25.md, Task O). Пока фоновый
поток (core.create_thread — см. gui/main_window_parts/async_load_mixin.py)
ждёт ответ от БД, пользователь сразу видит место под данные вместо
замороженного окна, вместо того чтобы GUI-поток стоял на self.db.method().

Ничто здесь не трогает Tk из чужого потока: все виджеты создаются и
обновляются только из главного потока — фоновый поток лишь считает данные и
возвращает результат, который вызывающий код обязан применить через
self.root.after(0, ...), см. AsyncLoadMixin.

Реальные потребители:
  - DevicesTableMixin — insert_skeleton_rows()/clear_skeleton_rows() в
    таблице заказов + BusyIndicator в статус-баре (load_devices/
    apply_filters/search_devices).
  - FinanceMixin — LoadingOverlay поверх таблицы финансов при первой
    ленивой загрузке вкладки и при смене периода."""

from __future__ import annotations

from enum import Enum, auto
from tkinter import ttk

import customtkinter as ctk

from utils.messages import Msg

# Публичная — используется и здесь, и в WidgetsMixin.create_devices_table()
# (tag_configure для стиля), чтобы имя тега не расходилось раздельными
# литералами в двух файлах (см. AUDIT_REPORT_v25.md, Task O verify-пасс).
SKELETON_TAG = "skeleton"


class LoadingStage(Enum):
    """Состояние фоновой загрузки — вместо булевых флагов россыпью по коду."""

    IDLE = auto()
    LOADING = auto()
    ERROR = auto()


class SkeletonFrame(ctk.CTkFrame):
    """Плейсхолдер-полоса с лёгкой пульсацией цвета вместо настоящего
    контента, пока он не готов. Пульсация — обычный self.after()-таймер (тот
    же паттерн, что и heartbeat пессимистичной блокировки, см.
    device_form_parts/locking_mixin.py), сам себя останавливает при
    destroy() — не оставляет висящих after-колбэков на уничтоженном виджете."""

    def __init__(
        self,
        parent,
        colors: dict,
        *,
        width: int = 200,
        height: int = 14,
        pulse_ms: int = 550,
        **kwargs,
    ):
        self._color_dim = colors.get("bg_tertiary", "#333333")
        self._color_lit = colors.get("border", "#555555")
        self._pulse_ms = pulse_ms
        self._pulse_job: str | None = None
        self._lit = False
        super().__init__(
            parent,
            width=width,
            height=height,
            corner_radius=max(height // 2, 4),
            fg_color=self._color_dim,
            **kwargs,
        )
        self._schedule_pulse()

    def _schedule_pulse(self) -> None:
        self._pulse_job = self.after(self._pulse_ms, self._pulse)

    def _pulse(self) -> None:
        self._lit = not self._lit
        try:
            self.configure(fg_color=self._color_lit if self._lit else self._color_dim)
        except Exception:
            return  # виджет уже уничтожен между after() и колбэком
        self._schedule_pulse()

    def destroy(self) -> None:
        if self._pulse_job is not None:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        super().destroy()


class BusyIndicator(ctk.CTkFrame):
    """Индикатор фоновой активности: индетерминированный CTkProgressBar +
    текстовая подпись. Скрыт, пока не идёт загрузка (start()/stop()
    управляют видимостью через pack — не занимает место в layout, когда не
    нужен)."""

    def __init__(self, parent, colors: dict, *, label_font_size: int = 11, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.stage = LoadingStage.IDLE
        self._label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=label_font_size),
            text_color=colors.get("text_secondary"),
        )
        self._label.pack(side="left", padx=(0, 6))
        self._bar = ctk.CTkProgressBar(self, mode="indeterminate", width=90, height=6)
        self._bar.pack(side="left")
        self.pack_forget()  # скрыт по умолчанию — видимость включает start()

    def start(self, text: str = Msg.LOADING_GENERIC) -> None:
        """Показывает индикатор и запускает анимацию."""
        self.stage = LoadingStage.LOADING
        self._label.configure(text=text)
        self.pack(side="left", padx=(10, 0))
        self._bar.start()

    def stop(self, *, error: bool = False) -> None:
        """Прячет индикатор. error=True — только меняет self.stage
        (диагностика для вызывающего кода), сам индикатор всё равно
        скрывается: ошибку сообщает messagebox/статус-бар, а не эта полоска."""
        self.stage = LoadingStage.ERROR if error else LoadingStage.IDLE
        try:
            self._bar.stop()
        except Exception:
            pass
        self.pack_forget()


class LoadingOverlay(ctk.CTkFrame):
    """Полноэкранный (относительно родителя) оверлей поверх контейнера с
    данными — показывается на время фоновой загрузки, скрывается по
    готовности. place() поверх родителя, а не pack/grid — не должен
    участвовать в геометрии соседних виджетов и не смещает их при
    появлении/исчезновении.

    Тот же интерфейс start()/stop(), что и у BusyIndicator — вызывающему
    коду (AsyncLoadMixin) не важно, какой именно "индикатор занятости" он
    показывает."""

    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, fg_color=colors.get("bg_secondary", "#1e1e1e"), **kwargs)
        self.stage = LoadingStage.IDLE

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        for _ in range(3):
            SkeletonFrame(center, colors, width=240, height=12).pack(pady=6)

        self._busy = BusyIndicator(center, colors, label_font_size=12)
        self._busy.pack(pady=(10, 0))

    def start(self, text: str = Msg.LOADING_GENERIC) -> None:
        """Показывает оверлей поверх родителя и запускает анимацию."""
        self.stage = LoadingStage.LOADING
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()
        self._busy.start(text)

    def stop(self, *, error: bool = False) -> None:
        """Прячет оверлей — родительский контейнер (уже заполненный реальными
        данными вызывающим кодом) снова становится видимым."""
        self.stage = LoadingStage.ERROR if error else LoadingStage.IDLE
        self._busy.stop(error=error)
        self.place_forget()


def insert_skeleton_rows(tree: ttk.Treeview, *, count: int = 6) -> None:
    """Заменяет ВСЁ текущее содержимое tree (старые реальные строки из
    предыдущей загрузки, а не только предыдущие skeleton-строки) на count
    плейсхолдер-строк, помеченных тегом SKELETON_TAG.

    Раньше строки только добавлялись поверх — вторая и все последующие
    загрузки (смена фильтра, повторный поиск, F5) показывали skeleton-строки
    ВМЕСТЕ со старыми данными, пока фоновый запрос не вернулся (найдено
    адверсарной проверкой, см. AUDIT_REPORT_v25.md, Task O). Именно поэтому
    очистка — обязательная часть этой функции, а не забота вызывающего кода:
    единственное место, где это легко забыть — самый частый путь вызова.

    Плейсхолдеры заменяются реальными данными обычным вызовом
    _clear_tree_and_populate() (тоже чистит всё) по готовности фонового
    потока, либо снимаются clear_skeleton_rows() при ошибке."""
    for item in tree.get_children():
        tree.delete(item)
    n_cols = len(tree["columns"]) or 1
    placeholder_row = ("░░░░░░",) * n_cols
    for _ in range(count):
        tree.insert("", "end", values=placeholder_row, tags=(SKELETON_TAG,))


def clear_skeleton_rows(tree: ttk.Treeview) -> None:
    """Удаляет только строки с тегом SKELETON_TAG — используется путём
    ошибки фоновой загрузки, когда подставить реальные данные нечем."""
    for item in tree.get_children():
        if SKELETON_TAG in tree.item(item, "tags"):
            tree.delete(item)
