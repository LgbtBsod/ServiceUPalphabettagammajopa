#!/usr/bin/env python3

"""Регрессия AUDIT_v25 (weak zone, HIGH): список редактируемых полей Device
раньше был независимо продублирован вручную в 3 местах (device_form.py's
save() x2, _apply_scalar_fields, update_device()'s new_values) без единого
источника истины — легко забыть добавить новое поле в одно из мест.

gui/dialogs/device_form.py::_SCALAR_FIELD_NAMES и _apply_scalar_fields
теперь СВЯЗАНЫ (последний реально итерирует первое, а не дублирует список
строк отдельно) — эти тесты держат оставшуюся связь: тот же набор имён
должен быть подмножеством того, что update_device() умеет принять
(database/sqlalchemy_database.py::DEVICE_UPDATE_FIELDS). Если кто-то добавит
поле в один список и забудет про другой, этот тест провалится, а не
промолчит."""

import gui  # noqa: F401 — обход циклического импорта managers/__init__.py

from database.sqlalchemy_database import DEVICE_UPDATE_FIELDS
from gui.dialogs.device_form import _SCALAR_FIELD_NAMES


def test_scalar_field_names_are_unique():
    assert len(_SCALAR_FIELD_NAMES) == len(set(_SCALAR_FIELD_NAMES))


def test_scalar_field_names_all_known_to_update_device():
    unknown = set(_SCALAR_FIELD_NAMES) - DEVICE_UPDATE_FIELDS
    assert not unknown, (
        f"Поля {unknown} есть в device_form.py::_SCALAR_FIELD_NAMES, но "
        "отсутствуют в database/sqlalchemy_database.py::DEVICE_UPDATE_FIELDS "
        "— update_device() не сможет их сохранить."
    )


def test_update_device_deliberately_excluded_fields_are_the_known_set():
    """work_items_json/photos/completion_date — отдельная логика/состояние
    (см. _apply_scalar_fields docstring). expense — тоже вне
    _SCALAR_FIELD_NAMES, но обрабатывается отдельной веткой внутри
    _apply_scalar_fields (за hasattr-проверкой — expense_entry существует
    только в edit-режиме, создаётся в двух разных вкладках). Если это
    множество вырастет незамеченно — стоит решить, специальный ли это
    случай или забытое поле."""
    excluded = DEVICE_UPDATE_FIELDS - set(_SCALAR_FIELD_NAMES)
    assert excluded == {"work_items_json", "photos", "completion_date", "expense"}
