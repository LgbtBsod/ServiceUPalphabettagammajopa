#!/usr/bin/env python3

"""Диалог с QR-кодом для подключения к PWA-версии."""

import logging

import customtkinter as ctk

from gui.widgets.modern import ModernButton, ModernCard, ModernLabel

logger = logging.getLogger(__name__)


class PWAQRDialog(ctk.CTkToplevel):
    """Окно с QR-кодом для подключения мобильного устройства.

    Показывает QR с URL сервера, инструкцию и кнопку остановки.
    """

    def __init__(
        self, parent, server_url: str, colors: dict, on_stop=None, settings=None
    ):
        super().__init__(parent)
        self.parent = parent
        self.server_url = server_url
        self.colors = colors
        self.on_stop = on_stop
        self.settings = settings

        self.title("📱 Мобильная версия")
        self.transient(parent)
        self.grab_set()

        # Адаптивная геометрия
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        except Exception:
            sw, sh = 1280, 720
        w, h = 420, 600
        x = (sw - w) // 2
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(380, 520)

        if settings:
            from utils.window_state import restore_window_geometry

            restore_window_geometry(
                settings,
                "pwa_qr",
                self,
                default_w=420,
                default_h=600,
                min_w=380,
                min_h=520,
            )

        self._qr_image = None  # удержание PhotoImage
        self.create_widgets()

    def create_widgets(self):
        """Создание интерфейса."""
        main = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"])
        main.pack(fill="both", expand=True, padx=15, pady=15)

        # Заголовок
        ModernLabel(
            main,
            self.colors,
            text="📱 Мобильная версия",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(pady=(5, 4))

        ModernLabel(
            main,
            self.colors,
            text="Сервер активен. Отсканируйте QR-код камерой\nтелефона для открытия приложения:",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
            justify="center",
        ).pack(pady=(0, 10))

        # QR-код
        qr_card = ModernCard(main, self.colors)
        qr_card.pack(pady=5)
        self.qr_label = ctk.CTkLabel(qr_card, text="")
        self.qr_label.pack(padx=20, pady=20)
        self._render_qr()

        # URL
        url_frame = ctk.CTkFrame(main, fg_color="transparent")
        url_frame.pack(fill="x", pady=(5, 10))

        ModernLabel(
            url_frame,
            self.colors,
            text="Адрес:",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
        ).pack(side="left")

        self.url_label = ModernLabel(
            url_frame,
            self.colors,
            text=self.server_url,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.colors["accent"],
        )
        self.url_label.pack(side="left", padx=(6, 0))

        # Инструкция
        ModernLabel(
            main,
            self.colors,
            text="💡 Подсказка:\n"
            "• Телефон и ПК должны быть в одной Wi-Fi сети\n"
            "• После открытия — «Добавить на главный экран»\n"
            "• Фото с камеры синхронизируются с ПК автоматически",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_secondary"],
            justify="left",
        ).pack(pady=(0, 12), anchor="w", padx=10)

        # Кнопки
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom", pady=(5, 0))

        if self.on_stop:
            ModernButton(
                btn_frame,
                self.colors,
                variant="danger",
                text="⏹ Остановить сервер",
                command=self._stop_server,
                height=38,
            ).pack(side="left", fill="x", expand=True, padx=2)

        ModernButton(
            btn_frame,
            self.colors,
            variant="secondary",
            text="✖ Закрыть окно",
            command=self._close,
            height=38,
        ).pack(side="right", padx=2)

    def _render_qr(self):
        """Рендерит QR-код из server_url через qrcode + PIL."""
        try:
            import qrcode

            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(self.server_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")

            # qrcode возвращает обёртку PilImage — получаем настоящий PIL.Image.
            # Дополнительно конвертируем из mode='1' (ч/б) в 'RGB', т.к. CTkImage
            # некорректно работает с 1-bit изображениями.
            pil_img = qr_img.get_image() if hasattr(qr_img, "get_image") else qr_img
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")

            # Конвертируем в CTkImage
            ctk_img = ctk.CTkImage(
                light_image=pil_img, dark_image=pil_img, size=(260, 260)
            )
            self._qr_image = ctk_img
            self.qr_label.configure(image=ctk_img, text="")
        except Exception as e:
            self.qr_label.configure(
                image=None,
                text=f"❌ Ошибка QR:\n{e}\n\nОткройте адрес вручную:\n{self.server_url}",
            )

    def _stop_server(self):
        """Останавливает сервер и закрывает окно."""
        try:
            if self.on_stop:
                self.on_stop()
        except Exception as e:
            logger.error(f"Ошибка остановки сервера: {e}", exc_info=True)
        self._close()

    def _close(self):
        """Закрывает окно (без остановки сервера)."""
        try:
            if self.settings:
                from utils.window_state import save_window_geometry

                save_window_geometry(self.settings, "pwa_qr", self)
        except Exception:
            pass
        self.destroy()
