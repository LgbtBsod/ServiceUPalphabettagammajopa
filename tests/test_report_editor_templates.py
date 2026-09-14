#!/usr/bin/env python3

"""Тесты для reports/report_editor.py::load_template_data()/save_template_data()
— чтение/запись JSON-шаблонов акта.

Workflow-найденный баг: битый/усечённый JSON-файл шаблона раньше молча
перезаписывался дефолтами (уничтожая кастомизацию пользователя — лого,
цвет, порядок полей, условия/гарантию) без единого предупреждения, а сама
запись была неатомарной (open(path, "w") усекает файл до записи), так что
прерванная запись (сбой, kill процесса) сама создавала "повреждённый"
файл, который следующий load тут же затирал дефолтами."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("gui")  # обход циклического импорта, как в test_act_importer.py

from reports import report_editor


@pytest.fixture(autouse=True)
def _isolated_templates_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(report_editor, "_templates_dir", lambda: str(tmp_path))
    return tmp_path


class TestLoadTemplateDataBaseline:
    def test_creates_default_template_when_file_does_not_exist(self, tmp_path):
        data = report_editor.load_template_data("receipt")
        assert data == report_editor._DEFAULT_TEMPLATES["receipt"]
        assert (tmp_path / "receipt_act.json").exists()

    def test_save_then_load_round_trips_custom_data(self):
        custom = {"name": "Мой шаблон", "header_text": "КАСТОМНЫЙ ЗАГОЛОВОК", "fields": ["phone"]}
        assert report_editor.save_template_data("receipt", custom)
        assert report_editor.load_template_data("receipt") == custom


class TestCorruptedTemplateIsPreservedNotOverwritten:
    def test_corrupted_json_is_backed_up_not_silently_replaced(self, tmp_path):
        path = tmp_path / "receipt_act.json"
        path.write_text("{not valid json!!", encoding="utf-8")

        data = report_editor.load_template_data("receipt")

        # Возвращает дефолты (приложение не падает)...
        assert data == report_editor._DEFAULT_TEMPLATES["receipt"]
        # ...но НЕ ценой уничтожения оригинала — он сохранён рядом с
        # исходным содержимым нетронутым, для восстановления вручную.
        backup = tmp_path / "receipt_act.json.corrupted"
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == "{not valid json!!"

    def test_truncated_json_from_an_interrupted_write_is_also_backed_up(self, tmp_path):
        """Симулирует ровно то, что раньше оставляла неатомарная запись:
        файл усечён посередине объекта."""
        path = tmp_path / "completion_act.json"
        path.write_text('{"name": "Частичная запи', encoding="utf-8")

        data = report_editor.load_template_data("completion")

        assert data == report_editor._DEFAULT_TEMPLATES["completion"]
        backup = tmp_path / "completion_act.json.corrupted"
        assert backup.exists()

    def test_after_backup_the_next_load_uses_the_freshly_written_default(self, tmp_path):
        path = tmp_path / "receipt_act.json"
        path.write_text("not json at all", encoding="utf-8")

        report_editor.load_template_data("receipt")
        # load_template_data() уже написал дефолтный шаблон на диск (тот же
        # путь, что и для "шаблона ещё не было") — повторный вызов должен
        # штатно прочитать ЕГО, а не снова наткнуться на "повреждённый" файл.
        second = report_editor.load_template_data("receipt")
        assert second == report_editor._DEFAULT_TEMPLATES["receipt"]
        assert json.loads(path.read_text(encoding="utf-8")) == report_editor._DEFAULT_TEMPLATES["receipt"]


class TestSaveTemplateDataIsAtomic:
    def test_successful_save_leaves_no_stray_temp_file(self, tmp_path):
        assert report_editor.save_template_data("receipt", {"name": "X"})
        leftovers = [p for p in tmp_path.iterdir() if p.name != "receipt_act.json"]
        assert leftovers == []

    def test_failed_write_does_not_corrupt_the_previously_saved_file(self, tmp_path, monkeypatch):
        """Ключевой тест атомарности: запись падает ПОСЛЕ того, как старый
        файл существовал с валидными данными — старый файл должен остаться
        нетронутым (не усечённым, не частично перезаписанным), а не
        превратиться в новый источник 'повреждённого шаблона'."""
        original = {"name": "Оригинал", "header_text": "ОРИГИНАЛЬНЫЙ"}
        assert report_editor.save_template_data("receipt", original)

        def _boom(*_a, **_kw):
            raise RuntimeError("disk full (симуляция)")

        monkeypatch.setattr(report_editor.json, "dump", _boom)

        ok = report_editor.save_template_data("receipt", {"name": "Новый — не должен сохраниться"})
        assert ok is False

        # Оригинал должен быть невредим — атомарная запись не усекла его.
        path = tmp_path / "receipt_act.json"
        assert json.loads(path.read_text(encoding="utf-8")) == original
        # И никакого недописанного .tmp-файла не осталось валяться.
        leftovers = [p for p in tmp_path.iterdir() if p.name != "receipt_act.json"]
        assert leftovers == []
