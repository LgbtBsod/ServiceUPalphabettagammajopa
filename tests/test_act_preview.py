#!/usr/bin/env python3

"""Тесты для gui/dialogs/act_preview.py::ActPreviewWindow — гонка между
print_utils.print_act_pdf()'s отложенным (lock-aware) удалением и
ActPreviewWindow._cleanup_temp()'s синхронным удалением ТОГО ЖЕ файла.

Workflow-найденный баг: print_act() при повторном использовании
self.temp_file (уже сгенерированного для предпросмотра PDF) передаёт его в
print_act_pdf(..., delete_after=True) — тот запускает свой фоновый поток,
который ждёт разблокировки файла (до 60с) перед удалением, специально
чтобы не стереть файл прямо во время печати/чтения спулером. Но
self.temp_file оставался присвоен — если окно закрывали сразу после
печати, destroy() -> _cleanup_temp() удалял тот же файл СИНХРОННО и БЕЗ
проверки блокировки, до того как принтер/спулер успевал его открыть."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("gui")

from gui.dialogs.act_preview import ActPreviewWindow
from utils.colors import get_colors


@pytest.fixture
def preview_window(tk_root):
    win = ActPreviewWindow(
        tk_root,
        "Test",
        "content",
        get_colors("light"),
        act_type="receipt",
        device_data={"order_number": "1", "client_name": "Тест", "phone": "+79990000000"},
    )
    yield win
    if win.winfo_exists():
        win.destroy()


class TestPrintActRelinquishesTempFileOwnership:
    def test_reusing_the_preview_file_clears_self_temp_file(self, preview_window, monkeypatch, tmp_path):
        pdf_path = str(tmp_path / "preview.pdf")
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4\n%%EOF")
        preview_window.temp_file = pdf_path

        captured = {}
        monkeypatch.setattr(
            "reports.print_utils.print_act_pdf",
            lambda path, **kw: captured.setdefault("path", path),
        )

        preview_window.print_act()

        assert captured["path"] == pdf_path
        assert preview_window.temp_file is None, (
            "self.temp_file must be cleared once ownership is handed to "
            "print_act_pdf(delete_after=True) — otherwise destroy() -> "
            "_cleanup_temp() can delete the same file out from under the "
            "print job print_act_pdf's own delayed thread is protecting"
        )

    def test_destroy_after_print_does_not_touch_the_file_print_utils_now_owns(
        self, preview_window, monkeypatch, tmp_path
    ):
        """Сквозная проверка: после печати с переиспользованием файла,
        закрытие окна (destroy -> _cleanup_temp) не удаляет файл — им
        теперь управляет (безопасно, с ожиданием разблокировки) поток
        print_utils, а не GUI-поток."""
        pdf_path = str(tmp_path / "preview.pdf")
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4\n%%EOF")
        preview_window.temp_file = pdf_path

        monkeypatch.setattr("reports.print_utils.print_act_pdf", lambda path, **kw: None)
        preview_window.print_act()

        preview_window.destroy()

        assert os.path.exists(pdf_path), (
            "the GUI's own destroy()/_cleanup_temp() deleted a file that "
            "print_utils.print_act_pdf() was supposed to own and delete "
            "safely (with a lock check) instead"
        )

    def test_generating_a_fresh_print_file_does_not_clear_an_unrelated_temp_file(
        self, preview_window, monkeypatch, tmp_path
    ):
        """Когда self.temp_file пуст (превью ещё не рендерилось), print_act()
        генерирует СВОЙ отдельный файл — фикс не должен трогать
        self.temp_file, если это НЕ тот же файл, что ушёл в print_act_pdf."""
        assert preview_window.temp_file is None

        captured = {}
        monkeypatch.setattr(
            "reports.print_utils.print_act_pdf",
            lambda path, **kw: captured.setdefault("path", path),
        )

        preview_window.print_act()

        assert "path" in captured
        assert captured["path"] != preview_window.temp_file
        assert preview_window.temp_file is None  # не тронут, как и был

        if os.path.exists(captured["path"]):
            os.remove(captured["path"])


class TestRenderPdfToImageClosesHandle:
    """Regression: _render_pdf_to_image() (module-level helper above)
    opened a pypdfium2.PdfDocument and never closed it — the identical bug
    already fixed at the equivalent call sites in reports/report_editor.py
    and reports/act_importer.py, just missed here. pypdfium2 does not
    release the file handle on GC, so an unclosed PdfDocument keeps its
    temp PDF locked on Windows even after gc.collect(); the NEXT
    render_pdf_preview() call's attempt to remove the previous temp_file
    (line ~309, wrapped in contextlib.suppress(OSError)) then silently
    fails, leaking one locked temp PDF per preview open/refresh for the
    life of the process."""

    def test_repeated_render_cleans_up_the_previous_temp_pdf(self, preview_window):
        preview_window.render_pdf_preview()
        first_pdf = preview_window.temp_file
        assert first_pdf is not None
        assert os.path.exists(first_pdf)

        preview_window.render_pdf_preview()
        second_pdf = preview_window.temp_file
        assert second_pdf is not None
        assert second_pdf != first_pdf
        assert not os.path.exists(first_pdf), (
            "the previous preview PDF should have been deleted before "
            "generating the next one — if this fails, the pdfium handle "
            "from the first render is still locking the file"
        )
