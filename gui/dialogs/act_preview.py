#!/usr/bin/env python3

"""Диалог предпросмотра акта с печатью.

Визуальный предпросмотр: рендер реального PDF в изображение через pypdfium2.
Если pypdfium2 недоступен — fallback на текстовый предпросмотр.
"""

import contextlib
import logging
import os
import tempfile
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from gui.widgets.modern import ModernButton, ModernCard, ModernLabel

logger = logging.getLogger(__name__)


def _pypdfium_available() -> bool:
    """Доступен ли pypdfium2 для рендера PDF в изображение."""
    try:
        import pypdfium2  # noqa: F401

        return True
    except Exception:
        return False


def _render_pdf_to_image(pdf_path: str, scale: float = 2.0):
    """Рендерит первую страницу PDF в PIL.Image через pypdfium2.

    Возвращает (PIL.Image, num_pages) или (None, 0) при ошибке.
    """
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(pdf_path)
        n_pages = len(pdf)
        if n_pages == 0:
            return None, 0
        page = pdf[0]
        bmp = page.render(scale=scale)
        img = bmp.to_pil()
        return img, n_pages
    except Exception as e:
        logger.error(f"Ошибка рендера PDF: {e}", exc_info=True)
        return None, 0


class ActPreviewWindow(ctk.CTkToplevel):
    """Окно предпросмотра акта с возможностью печати.

    Параметры:
        content — текстовый контент (fallback-предпросмотр).
        device_data — данные заказа для генерации PDF.
        template_data — опциональный шаблон из редактора актов (применяет
            заголовок/поля/цвет/условия/логотип к PDF).
    """

    def __init__(
        self,
        parent,
        title: str,
        content: str,
        colors: dict,
        act_type: str = "receipt",
        device_data: dict | None = None,
        template_data: dict | None = None,
        settings=None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.title_text = title
        self.content = content
        self.colors = colors
        self.act_type = act_type
        self.device_data = device_data or {}
        self.template_data = template_data or {}
        self.settings = settings  # опционально, для сохранения геометрии
        self.temp_file = None
        self._pdf_image = None  # держим ссылку на PhotoImage

        self.title(f"Предпросмотр: {title}")
        from utils.window_state import restore_window_geometry

        restore_window_geometry(
            self.settings,
            "act_preview",
            self,
            default_w=680,
            default_h=700,
            min_w=560,
            min_h=560,
        )

        self.transient(parent)
        self.grab_set()

        # Сохраняем геометрию при закрытии
        self.protocol("WM_DELETE_WINDOW", self._close_with_geometry)

        self._pdf_render_ok = _pypdfium_available()
        self.create_widgets()
        # Рендерим PDF после отображения окна
        if self._pdf_render_ok:
            self.after(100, self.render_pdf_preview)

    def _fit_window(self, default_w: int, default_h: int, min_w: int, min_h: int):
        """Адаптивный размер окна под текущий экран (для 1280x720 и меньше)."""
        from utils.window_state import fit_window_to_screen

        fit_window_to_screen(self, default_w, default_h, min_w, min_h, width_ratio=0.55)

    def _build_generator(self):
        """Создаёт ActPDFGenerator с учётом template_data (изменения редактора)."""
        from reports.report_renderer import ActPDFGenerator

        return ActPDFGenerator(template_data=self.template_data)

    def create_widgets(self):
        """Создание виджетов"""
        main_container = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"])
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Заголовок с кнопками
        title_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 10))

        icon_label = ctk.CTkLabel(
            title_frame,
            text="📄" if self.act_type == "receipt" else "🔧",
            font=ctk.CTkFont(size=28),
            text_color=self.colors["accent"],
        )
        icon_label.pack(side="left", padx=(0, 10))

        title_label = ctk.CTkLabel(
            title_frame,
            text=f"Предпросмотр: {self.title_text}",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors["accent"],
        )
        title_label.pack(side="left")

        # Кнопки действий
        btn_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        btn_frame.pack(side="right")

        # Кнопка печати
        print_btn = ModernButton(
            btn_frame,
            self.colors,
            variant="primary",
            text="🖨️ Печать",
            command=self.print_act,
            width=100,
            height=32,
        )
        print_btn.pack(side="left", padx=3)

        # Кнопка экспорта PDF
        pdf_btn = ModernButton(
            btn_frame,
            self.colors,
            variant="success",
            text="📄 PDF",
            command=self.export_pdf,
            width=80,
            height=32,
        )
        pdf_btn.pack(side="left", padx=3)

        # Кнопка двух актов на лист A4
        ModernButton(
            btn_frame,
            self.colors,
            variant="success",
            text="📋 2 на лист",
            command=self.export_dual_pdf,
            width=100,
            height=32,
        ).pack(side="left", padx=3)

        # Кнопка сохранения (текст)
        save_btn = ModernButton(
            btn_frame,
            self.colors,
            variant="secondary",
            text="💾 TXT",
            command=self.save_act,
            width=80,
            height=32,
        )
        save_btn.pack(side="left", padx=3)

        # Кнопка обновления предпросмотра
        if self._pdf_render_ok:
            refresh_btn = ModernButton(
                btn_frame,
                self.colors,
                variant="secondary",
                text="🔄",
                command=self.render_pdf_preview,
                width=45,
                height=32,
            )
            refresh_btn.pack(side="left", padx=3)

        # Кнопка закрытия
        close_btn = ModernButton(
            btn_frame,
            self.colors,
            variant="secondary",
            text="✖ Закрыть",
            command=self._close_with_geometry,
            width=80,
            height=32,
        )
        close_btn.pack(side="left", padx=3)

        # Область предпросмотра
        preview_card = ModernCard(main_container, self.colors)
        preview_card.pack(fill="both", expand=True)

        # Scrollable контейнер для изображения
        self.preview_container = ctk.CTkScrollableFrame(
            preview_card, fg_color=self.colors["bg_secondary"]
        )
        self.preview_container.pack(fill="both", expand=True, padx=8, pady=8)

        if self._pdf_render_ok:
            # Плейсхолдер до рендера
            self.pdf_label = ctk.CTkLabel(
                self.preview_container,
                text="⏳ Формирование предпросмотра...",
                font=ctk.CTkFont(size=13),
                text_color=self.colors["text_secondary"],
            )
            self.pdf_label.pack(expand=True, pady=40)
        else:
            # Fallback: текстовый предпросмотр
            self.text_widget = ctk.CTkTextbox(
                self.preview_container,
                wrap="word",
                font=ctk.CTkFont(family="Courier", size=11),
                fg_color=self.colors["bg_secondary"],
                text_color=self.colors["text_primary"],
                border_width=0,
            )
            self.text_widget.pack(fill="both", expand=True, padx=4, pady=4)
            self.text_widget.insert("1.0", self.content)
            self.text_widget.configure(state="disabled")

        # Статусная строка
        status_frame = ctk.CTkFrame(main_container, fg_color="transparent", height=30)
        status_frame.pack(fill="x", pady=(10, 0))

        mode = (
            "визуальный PDF"
            if self._pdf_render_ok
            else "текстовый (pypdfium2 недоступен)"
        )
        self.status_label = ModernLabel(
            status_frame,
            self.colors,
            text=f"✅ Готов к печати ({mode})",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["success"],
        )
        self.status_label.pack(side="left")

        date_label = ModernLabel(
            status_frame,
            self.colors,
            text=datetime.now().strftime("%d.%m.%Y %H:%M"),
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_secondary"],
        )
        date_label.pack(side="right")

    def render_pdf_preview(self):
        """Генерирует PDF во временный файл и рендерит его в изображение."""
        if not self._pdf_render_ok:
            return
        try:
            # Удаляем старый плейсхолдер/картинку
            for w in self.preview_container.winfo_children():
                w.destroy()

            # Генерируем PDF во временный файл
            gen = self._build_generator()
            suffix = "completion" if self.act_type == "completion" else "receipt"
            if self.temp_file and os.path.exists(self.temp_file):
                with contextlib.suppress(OSError):
                    os.remove(self.temp_file)
            fd, self.temp_file = tempfile.mkstemp(
                suffix=f"_{suffix}.pdf", prefix="act_preview_"
            )
            os.close(fd)

            if self.act_type == "completion":
                ok = gen.generate_completion_pdf(self.temp_file, self.device_data)
            else:
                ok = gen.generate_receipt_pdf(self.temp_file, self.device_data)

            if not ok or not os.path.exists(self.temp_file):
                self.pdf_label = ctk.CTkLabel(
                    self.preview_container,
                    text="❌ Не удалось сформировать PDF",
                    font=ctk.CTkFont(size=13),
                    text_color=self.colors["error"],
                )
                self.pdf_label.pack(expand=True, pady=40)
                return

            # Рендерим в изображение, подгоняя по ширине контейнера
            self.preview_container.update_idletasks()
            avail_w = max(self.preview_container.winfo_width() - 20, 300)
            # A5 ширина 148мм; scale ~ avail_w / (148mm в px). Считаем через pts.
            # 148 мм = 148 * 2.83465 pt; при scale s ширина px = 148*2.83465*s
            scale = max(1.0, avail_w / (148 * 2.83465))
            img, n_pages = _render_pdf_to_image(self.temp_file, scale=scale)
            if img is None:
                self.pdf_label = ctk.CTkLabel(
                    self.preview_container,
                    text="❌ Ошибка рендера PDF",
                    font=ctk.CTkFont(size=13),
                    text_color=self.colors["error"],
                )
                self.pdf_label.pack(expand=True, pady=40)
                return

            # Конвертация PIL -> CTkImage
            ctk_img = ctk.CTkImage(
                light_image=img, dark_image=img, size=(img.size[0], img.size[1])
            )
            self._pdf_image = ctk_img  # удерживаем ссылку
            self.pdf_label = ctk.CTkLabel(
                self.preview_container, image=ctk_img, text=""
            )
            self.pdf_label.pack(expand=True, padx=4, pady=4)

            self.status_label.configure(
                text=f"✅ Предпросмотр готов ({n_pages} стр.)",
                text_color=self.colors["success"],
            )
        except Exception as e:
            logger.error(f"Ошибка предпросмотра PDF: {e}", exc_info=True)
            try:
                self.pdf_label = ctk.CTkLabel(
                    self.preview_container,
                    text=f"❌ Ошибка: {e}",
                    font=ctk.CTkFont(size=12),
                    text_color=self.colors["error"],
                )
                self.pdf_label.pack(expand=True, pady=40)
            except Exception:
                pass

    def print_act(self):
        """Печать акта: генерация PDF (A5) во временный файл и отправка на принтер."""
        try:
            gen = self._build_generator()
            suffix = "completion" if self.act_type == "completion" else "receipt"
            # Переиспользуем PDF из предпросмотра, если есть
            print_file = None
            if (
                self.temp_file
                and os.path.exists(self.temp_file)
                and self.temp_file.endswith(".pdf")
            ):
                print_file = self.temp_file
            else:
                fd, print_file = tempfile.mkstemp(
                    suffix=f"_{suffix}.pdf", prefix="act_print_"
                )
                os.close(fd)
                if self.act_type == "completion":
                    ok = gen.generate_completion_pdf(print_file, self.device_data)
                else:
                    ok = gen.generate_receipt_pdf(print_file, self.device_data)
                if not ok or not os.path.exists(print_file):
                    # Запасной вариант — печать текста
                    txt_file = print_file + ".txt"
                    with open(txt_file, "w", encoding="utf-8") as f:
                        f.write(self.content)
                    print_file = txt_file

            # Печать через утилиту (с автоудалением временного файла)
            from reports.print_utils import print_act_pdf

            print_act_pdf(print_file, delete_after=True, delay_sec=60)
            self.status_label.configure(
                text="🖨️ Отправлено на печать (PDF A5)",
                text_color=self.colors["success"],
            )

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось напечатать: {e}")
            self.status_label.configure(
                text="❌ Ошибка печати", text_color=self.colors["error"]
            )

    def save_act(self):
        """Сохранение акта в текстовый файл"""
        from tkinter import filedialog

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"{self.title_text.replace(' ', '_')}.txt",
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.content)
                self.status_label.configure(
                    text=f"💾 Сохранено: {os.path.basename(file_path)}",
                    text_color=self.colors["success"],
                )
                messagebox.showinfo("Успех", f"Акт сохранен:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}")

    def export_pdf(self):
        """Экспорт в PDF (формат A5) — автосохранение в exports/ + открытие."""
        try:
            from reports.print_utils import create_temp_act_pdf, open_act_pdf

            order_number = str(self.device_data.get("order_number", ""))
            file_path = create_temp_act_pdf(self.act_type, order_number)

            gen = self._build_generator()
            if self.act_type == "completion":
                ok = gen.generate_completion_pdf(file_path, self.device_data)
            else:
                ok = gen.generate_receipt_pdf(file_path, self.device_data)

            if ok:
                self.status_label.configure(
                    text=f"📄 PDF сохранён: {os.path.basename(file_path)}",
                    text_color=self.colors["success"],
                )
                # Открываем в просмотрщике (файл удалится через 2 мин)
                open_act_pdf(file_path, delete_after=True, delay_sec=120)
            else:
                messagebox.showerror("Ошибка", "Не удалось создать PDF")
        except ImportError:
            messagebox.showerror(
                "Ошибка",
                "Для экспорта в PDF установите reportlab:\npip install reportlab",
            )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать PDF: {e}")

    def export_dual_pdf(self):
        """Экспорт двух копий акта на одном листе A4 — автосохранение + печать."""
        try:
            from reports.print_utils import create_temp_act_pdf, print_act_pdf

            order_number = str(self.device_data.get("order_number", ""))
            file_path = create_temp_act_pdf(self.act_type, order_number)

            gen = self._build_generator()
            ok = gen.generate_dual_pdf(
                file_path,
                self.device_data,
                self.device_data,
                act_type1=self.act_type,
                act_type2=self.act_type,
            )
            if ok:
                self.status_label.configure(
                    text="📋 2 акта на A4 — печать...",
                    text_color=self.colors["success"],
                )
                print_act_pdf(file_path, delete_after=True, delay_sec=60)
            else:
                messagebox.showerror("Ошибка", "Не удалось создать PDF")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать PDF: {e}")

    def _cleanup_temp(self):
        """Удаление временного файла"""
        if self.temp_file and os.path.exists(self.temp_file):
            with contextlib.suppress(OSError):
                os.remove(self.temp_file)
            self.temp_file = None

    def _close_with_geometry(self):
        """Сохраняет геометрию окна в config и закрывает его."""
        from utils.window_state import close_dialog_with_geometry

        close_dialog_with_geometry(self, self.settings, "act_preview")

    def destroy(self):
        """Очистка и закрытие окна"""
        self._cleanup_temp()
        super().destroy()
