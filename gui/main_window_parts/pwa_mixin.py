#!/usr/bin/env python3
"""PwaMixin — управление PWA-сервером (мобильная версия): авто-запуск,
QR-диалог, остановка, авто-синхронизация списка заказов. См.
AUDIT_REPORT_v25.md, Task T (перенесено из main_window.py без изменения
поведения)."""

from __future__ import annotations

import contextlib
import logging
from tkinter import messagebox

logger = logging.getLogger(__name__)


class PwaMixin:
    """Требует от финального класса ServiceCenterApp: self.settings,
    self.root, self.pwa_manager (инициализируется в __init__ как None)."""

    def _auto_start_pwa(self):
        """Авто-запуск PWA-сервера при старте программы (без показа QR-диалога)."""
        try:
            from pwa.server import PWAServerManager

            if self.pwa_manager is None:
                self.pwa_manager = PWAServerManager()
            if not self.pwa_manager.is_running:
                port = self.settings.get("pwa.port", 5000)
                if self.pwa_manager.start(port=port):
                    url = self.pwa_manager.get_url()
                    self.update_status_bar(f"📱 Мобильная версия активна: {url}")
        except Exception as e:
            logger.error(f"Авто-запуск PWA сервера не удался: {e}", exc_info=True)

    def toggle_mobile_server(self):
        """Запуск/просмотр мобильной версии (PWA-сервер)."""
        try:
            from pwa.server import PWAServerManager

            # Ленивая инициализация менеджера
            if not hasattr(self, "pwa_manager") or self.pwa_manager is None:
                self.pwa_manager = PWAServerManager()

            port = self.settings.get("pwa.port", 5000)

            # Если сервер не запущен — запускаем
            if not self.pwa_manager.is_running:
                started = self.pwa_manager.start(port=port)
                if not started:
                    messagebox.showerror(
                        "Ошибка",
                        "Не удалось запустить сервер мобильной версии.\n"
                        "Проверьте, что порт свободен.",
                    )
                    return
                # Небольшая пауза для старта Flask
                self.root.after(500, self._show_qr_dialog)

            # Если уже запущен — просто показываем QR
            else:
                self._show_qr_dialog()
        except ImportError:
            messagebox.showerror(
                "Ошибка",
                "Мобильная версия недоступна.\n"
                "Установите Flask: pip install flask qrcode",
            )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запустить сервер: {e}")

    def _show_qr_dialog(self):
        """Показывает диалог с QR-кодом."""
        from gui.dialogs.pwa_qr_dialog import PWAQRDialog

        if not self.pwa_manager or not self.pwa_manager.is_running:
            return
        url = self.pwa_manager.get_url()
        PWAQRDialog(
            self.root,
            url,
            self.colors,
            on_stop=self.stop_mobile_server,
            settings=self.settings,
        )

    def stop_mobile_server(self):
        """Останавливает PWA-сервер."""
        try:
            if hasattr(self, "pwa_manager") and self.pwa_manager is not None:
                self.pwa_manager.stop()
                self.update_status_bar("Мобильная версия остановлена")
        except Exception as e:
            logger.error(f"Ошибка остановки PWA-сервера: {e}", exc_info=True)

    def _start_auto_sync(self):
        """Запускает периодическое автообновление списка заказов.

        Интервал берётся из настроек pwa.sync_interval (секунд).
        Если 0 или auto_sync=False — автообновление выключено.
        Позволяет видеть изменения из PWA (фото, новые заказы) без ручного
        обновления.
        """
        self._auto_sync_after_id = None
        try:
            auto_sync = self.settings.get("pwa.auto_sync", True)
            interval = self.settings.get("pwa.sync_interval", 30)
        except Exception:
            auto_sync = False
            interval = 0

        if not auto_sync or not interval or interval <= 0:
            return

        def _tick():
            # Не обновляем, если открыто модальное окно (форма заказа и т.п.),
            # чтобы не сбить выбор пользователя.
            try:
                # Тихо перезагружаем, сохраняя текущие фильтры
                search_text = (
                    self.search_var.get().strip() if hasattr(self, "search_var") else ""
                )
                if search_text:
                    # При активном поиске автообновление не делаем (мешает)
                    pass
                else:
                    self.apply_filters()
            except Exception:
                pass
            # Планируем следующий тик
            self._auto_sync_after_id = self.root.after(interval * 1000, _tick)

        self._auto_sync_after_id = self.root.after(interval * 1000, _tick)

    def _stop_auto_sync(self):
        """Останавливает автообновление."""
        if getattr(self, "_auto_sync_after_id", None) is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._auto_sync_after_id)
            self._auto_sync_after_id = None
