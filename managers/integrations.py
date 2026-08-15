#!/usr/bin/env python3

"""Менеджер интеграций (SMS, Email, Telegram)"""

import logging

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
        """Отправка СМС"""
        if not self.settings.get("sms_notifications"):
            return False

        self.settings.get("sms_api_key")
        self.settings.get("sms_sender")

        # Здесь должна быть реализация конкретного СМС-провайдера
        logger.info(f"📱 Отправка СМС на {phone}: {message}")
        return True

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Отправка Email"""
        if not self.settings.get("email_notifications"):
            return False

        try:
            # Здесь должна быть реализация отправки email
            logger.info(f"📧 Отправка Email на {to_email}: {subject}")
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
