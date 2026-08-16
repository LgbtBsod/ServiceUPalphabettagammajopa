#!/usr/bin/env python3

"""Тесты для managers/integrations.py::IntegrationManager — реальные
реализации send_sms (SMS.ru)/send_email (SMTP), заменившие в этой сессии
заглушки, молча возвращавшие True без единого сетевого запроса (см.
AUDIT_REPORT_v25.md). Сеть замокана — реальных запросов тесты не делают."""

from unittest.mock import MagicMock, patch

import gui  # noqa: F401 — обход циклического импорта managers/__init__.py
from managers.integrations import IntegrationManager


class _FakeSettings:
    def __init__(self, **values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


class TestSendSms:
    def test_disabled_returns_false_without_network_call(self):
        mgr = IntegrationManager(_FakeSettings(sms_notifications=False))
        with patch("requests.get") as mock_get:
            assert mgr.send_sms("+79991234567", "текст") is False
            mock_get.assert_not_called()

    def test_missing_api_key_returns_false(self):
        mgr = IntegrationManager(_FakeSettings(sms_notifications=True, sms_api_key=""))
        with patch("requests.get") as mock_get:
            assert mgr.send_sms("+79991234567", "текст") is False
            mock_get.assert_not_called()

    def test_success_calls_sms_ru_api(self):
        mgr = IntegrationManager(
            _FakeSettings(sms_notifications=True, sms_api_key="APIKEY123")
        )
        mgr.requests_available = True
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK"}
        with patch("requests.get", return_value=mock_response) as mock_get:
            assert mgr.send_sms("+79991234567", "Ваш заказ готов") is True
            args, kwargs = mock_get.call_args
            assert args[0] == "https://sms.ru/sms/send"
            assert kwargs["params"]["api_id"] == "APIKEY123"
            assert kwargs["params"]["to"] == "+79991234567"

    def test_sms_ru_error_status_returns_false(self):
        mgr = IntegrationManager(
            _FakeSettings(sms_notifications=True, sms_api_key="APIKEY123")
        )
        mgr.requests_available = True
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ERROR", "status_text": "bad key"}
        with patch("requests.get", return_value=mock_response):
            assert mgr.send_sms("+79991234567", "текст") is False

    def test_network_exception_returns_false(self):
        mgr = IntegrationManager(
            _FakeSettings(sms_notifications=True, sms_api_key="APIKEY123")
        )
        mgr.requests_available = True
        with patch("requests.get", side_effect=RuntimeError("timeout")):
            assert mgr.send_sms("+79991234567", "текст") is False


class TestSendEmail:
    def test_disabled_returns_false(self):
        mgr = IntegrationManager(_FakeSettings(email_notifications=False))
        assert mgr.send_email("client@example.com", "Готов", "текст") is False

    def test_missing_credentials_returns_false(self):
        mgr = IntegrationManager(
            _FakeSettings(email_notifications=True, smtp_host="", email_login="", email_password="")
        )
        assert mgr.send_email("client@example.com", "Готов", "текст") is False

    def test_success_calls_smtp(self):
        mgr = IntegrationManager(
            _FakeSettings(
                email_notifications=True,
                smtp_host="smtp.example.com",
                smtp_port=587,
                smtp_use_tls=True,
                email_login="shop@example.com",
                email_password="secret",
            )
        )
        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        with patch("smtplib.SMTP", return_value=mock_smtp_cm) as mock_smtp:
            ok = mgr.send_email("client@example.com", "Заказ готов", "Приходите за заказом")
            assert ok is True
            mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("shop@example.com", "secret")
            mock_server.sendmail.assert_called_once()

    def test_smtp_exception_returns_false(self):
        mgr = IntegrationManager(
            _FakeSettings(
                email_notifications=True,
                smtp_host="smtp.example.com",
                email_login="shop@example.com",
                email_password="secret",
            )
        )
        with patch("smtplib.SMTP", side_effect=RuntimeError("connection refused")):
            assert mgr.send_email("client@example.com", "Готов", "текст") is False


class TestNotifyOrderReady:
    """notify_order_ready() — уже существовавшая координация всех трёх
    каналов, эта сессия чинит только сами send_sms/send_email; здесь просто
    подтверждаем, что она по-прежнему зовёт все включённые каналы."""

    def test_calls_sms_when_phone_present(self):
        mgr = IntegrationManager(
            _FakeSettings(notify_on_ready=True, sms_notifications=True, sms_api_key="X")
        )
        with patch.object(mgr, "send_sms", return_value=True) as mock_sms, \
             patch.object(mgr, "send_telegram", return_value=False):
            mgr.notify_order_ready(
                {"client_name": "Иван Иванов", "phone": "+79991234567", "order_number": "00001"}
            )
            mock_sms.assert_called_once()

    def test_noop_when_notify_on_ready_disabled(self):
        mgr = IntegrationManager(_FakeSettings(notify_on_ready=False))
        with patch.object(mgr, "send_sms") as mock_sms, \
             patch.object(mgr, "send_telegram") as mock_tg:
            mgr.notify_order_ready(
                {"client_name": "Иван Иванов", "phone": "+79991234567", "order_number": "00001"}
            )
            mock_sms.assert_not_called()
            mock_tg.assert_not_called()
