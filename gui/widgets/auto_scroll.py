#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Автоматически скрывающиеся скроллбары для ttk.Treeview и других виджетов.

Скроллбар скрывается (grid_remove), когда контент полностью помещается
в видимую область, и появляется снова, когда появляется прокручиваемый контент.

Использование (вместо ручного создания ttk.Scrollbar):

    from gui.widgets.auto_scroll import attach_auto_scrollbars

    vsb, hsb = attach_auto_scrollbars(tree_container, self.tree)
    # vsb/hsb уже размещены через grid; настраивать rowconfigure/columnconfigure
    # для контейнера нужно как обычно (tree в (0,0), vsb в (0,1), hsb в (1,0)).
"""

from tkinter import ttk


def _make_visibility_checker(scrollbar, widget, orient):
    """Возвращает callback, который скрывает/показывает скроллбар.

    Для vertical: если вся высота контента <= высоты виджета — скрываем.
    Для horizontal: аналогично по ширине.
    """
    def check(*_args):
        try:
            if orient == "vertical":
                # yview возвращает (верхняя_доля, нижняя_доля) видимой области.
                # Если (нижняя - верхняя) >= 1.0 — весь контент виден.
                first, last = widget.yview()
                if last - first >= 0.999:
                    scrollbar.grid_remove()
                else:
                    scrollbar.grid()
            else:
                first, last = widget.xview()
                if last - first >= 0.999:
                    scrollbar.grid_remove()
                else:
                    scrollbar.grid()
        except Exception:
            # Виджет мог быть уничтожен
            pass
    return check


def attach_auto_scrollbars(parent, widget, row=0, column=0):
    """Создаёт вертикальный и горизонтальный авто-скрываемые скроллбары.

    Размещает:
      - виджет в parent[row, column]
      - vsb в parent[row, column+1] (sticky="ns")
      - hsb в parent[row+1, column] (sticky="ew")

    Возвращает (vsb, hsb). Контейнер parent должен иметь настроенные
    grid_rowconfigure(row, weight=1) и grid_columnconfigure(column, weight=1).
    """
    vsb = ttk.Scrollbar(parent, orient="vertical", command=widget.yview)
    hsb = ttk.Scrollbar(parent, orient="horizontal", command=widget.xview)
    widget.configure(yscrollcommand=lambda f, l: (_on_scroll(vsb, f, l), vsb.event_generate("<<AutoScrollCheck>>")))
    widget.configure(xscrollcommand=lambda f, l: (_on_scroll(hsb, f, l), hsb.event_generate("<<AutoScrollCheck>>")))

    widget.grid(row=row, column=column, sticky="nsew")
    vsb.grid(row=row, column=column + 1, sticky="ns")
    hsb.grid(row=row + 1, column=column, sticky="ew")

    check_v = _make_visibility_checker(vsb, widget, "vertical")
    check_h = _make_visibility_checker(hsb, widget, "horizontal")

    # Проверяем при изменении содержимого/размера виджета
    widget.bind("<<AutoScrollCheck>>", lambda e: (check_v(), check_h()), add="+")
    widget.bind("<Configure>", lambda e: (check_v(), check_h()), add="+")
    # Привязка событий Treeview на добавление/удаление строк
    try:
        widget.bind("<<TreeviewSelect>>", lambda e: (check_v(), check_h()), add="+")
    except Exception:
        pass
    # Периодическая проверка (ловит программные изменения содержимого)
    _schedule_periodic_check(widget, check_v, check_h)

    # Первоначальная проверка
    widget.after(200, lambda: (check_v(), check_h()))
    return vsb, hsb


def _on_scroll(scrollbar, first, last):
    """Проксирует set() скроллбару."""
    try:
        scrollbar.set(first, last)
    except Exception:
        pass


def _schedule_periodic_check(widget, check_v, check_h, interval_ms=800):
    """Периодически перепроверяет видимость скроллбаров.

    Это надёжно ловит программные вставки/удаления строк, которые не дают
    событий <Configure>. Планирует сам себя, пока виджет существует.
    """
    def tick():
        try:
            if not widget.winfo_exists():
                return
            check_v()
            check_h()
            widget.after(interval_ms, tick)
        except Exception:
            pass
    widget.after(interval_ms, tick)
