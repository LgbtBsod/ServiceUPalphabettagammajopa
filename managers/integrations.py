#!/usr/bin/env python3

"""Менеджер интеграций (SMS, Email, Telegram)"""

import logging

from domain.constants import STATUS_READY
from utils.formatters import format_order_number_for_display

logger = logging.getLogger(__name__)


class IntegrationManager:
    """Класс для управления интеграциями"""

    def __init__(self, settings):
        self.settings = settings
        self.requests_available = self._check_requests()

    def _check_requests(self) -> bool:
        """Проверка доступности requests"""
        try:
            import importlib.util

            return importlib.util.find_spec("requests") is not None
        except (ImportError, AttributeError):
            return False

    def send_sms(self, phone: str, message: str) -> bool:
        """Отправка СМС через SMS.ru (https://sms.ru/api/send) — один
        API-ключ, без логина/пароля. Раньше это была заглушка (return True
        без единого реального запроса) — АУДИТ v25 нашёл, что пользователь,
        включивший галочку, получал полную тишину, думая, что уведомления
        отправляются. requests — опциональная зависимость приложения (см.
        requests_available), без неё честно возвращаем False."""
        if not self.settings.get("sms_notifications"):
            return False

        api_key = self.settings.get("sms_api_key")
        if not api_key or not self.requests_available:
            return False

        try:
            import requests

            response = requests.get(
                "https://sms.ru/sms/send",
                params={"api_id": api_key, "to": phone, "msg": message, "json": 1},
                timeout=10,
            )
            data = response.json()
            if data.get("status") != "OK":
                logger.warning(f"SMS.ru отклонил отправку: {data}")
                return False
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки СМС: {e}", exc_info=True)
            return False

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Отправка Email через SMTP (smtplib — стандартная библиотека, не
        привязывает к конкретному провайдеру: работает с любым сервисом,
        поддерживающим SMTP). Раньше это была заглушка (return True без
        единого реального запроса) — см. AUDIT_REPORT_v25.md."""
        if not self.settings.get("email_notifications"):
            return False

        host = self.settings.get("smtp_host")
        login = self.settings.get("email_login")
        password = self.settings.get("email_password")
        if not host or not login or not password:
            return False

        try:
            import smtplib
            from email.mime.text import MIMEText

            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = login
            msg["To"] = to_email

            port = int(self.settings.get("smtp_port", 587) or 587)
            with smtplib.SMTP(host, port, timeout=10) as server:
                if self.settings.get("smtp_use_tls", True):
                    server.starttls()
                server.login(login, password)
                server.sendmail(login, [to_email], msg.as_string())
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки email: {e}", exc_info=True)
            return False

    def send_telegram(self, message: str) -> bool:
        """Отправка сообщения в Telegram"""
        if not self.settings.get("telegram_bot") or not self.requests_available:
            return False

        token = self.settings.get("telegram_token")
        chat_id = self.settings.get("telegram_chat_id")

        if not token or not chat_id:
            return False

        try:
            import requests

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
            response = requests.post(url, data=data, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ошибка отправки Telegram: {e}", exc_info=True)
            return False

    def notify_order_ready(self, device: dict) -> None:
        """Уведомление о готовности заказа"""
        if not self.settings.get("notify_on_ready"):
            return

        client_name = device.get("client_name", "")
        phone = device.get("phone", "")
        order_number = format_order_number_for_display(device.get("order_number", ""))

        message = f"Уважаемый {client_name}, ваш заказ №{order_number} готов к выдаче!"

        if phone:
            self.send_sms(phone, message)

        if self.settings.get("email_notifications") and self.settings.get(
            "email_login"
        ):
            self.send_email(
                self.settings.get("email_login"),
                f"Заказ №{order_number} готов",
                message,
            )

        self.send_telegram(f"✅ Заказ №{order_number} готов для {client_name}")

    def on_device_status_changed(self, event) -> None:
        """Обработчик domain.events.DeviceStatusChangedEvent — подписан в
        bootstrap.py через core.subscribe(). Реагирует ТОЛЬКО на генуинный
        переход в "Готов к выдаче" (не на каждую публикацию события).

        Первый реальный потребитель core/events/event_bus.py в этом
        приложении: Database.update_device()/update_device_status()
        публикуют событие, ничего не зная про IntegrationManager — раньше
        notify_order_ready() приходилось звать напрямую из одного
        конкретного места в GUI (gui/dialogs/device_form.py), и путь
        "быстрая смена статуса" (update_device_status(), кнопка/PWA) вообще
        не уведомлял клиента. Событие приходит из ОБОИХ путей одинаково,
        см. AUDIT_REPORT_v25.md."""
        if event.new_status != STATUS_READY or event.old_status == STATUS_READY:
            return
        try:
            self.notify_order_ready(event.device_data)
        except Exception as e:
            logger.error(f"Ошибка обработки DeviceStatusChangedEvent: {e}", exc_info=True)
