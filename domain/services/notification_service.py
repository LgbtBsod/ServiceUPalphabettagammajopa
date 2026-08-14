"""
Notification domain service - сервис уведомлений.

Отвечает за отправку уведомлений клиентам через различные каналы:
- SMS
- Email
- Push-уведомления (PWA)
- Telegram бот
"""

from __future__ import annotations
import logging
from typing import List, Optional, Protocol, Dict, Any
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    """Протокол канала уведомлений."""
    
    def send(self, recipient: str, subject: str, message: str) -> bool: ...
    def is_available(self) -> bool: ...


class NotificationService:
    """
    Сервис управления уведомлениями.
    
    Реализует паттерн Strategy для поддержки различных каналов.
    Следует принципу Open/Closed - легко добавлять новые каналы.
    """
    
    def __init__(self):
        self._channels: Dict[str, NotificationChannel] = {}
        self._notification_log: List[Dict[str, Any]] = []
    
    def register_channel(
        self, 
        name: str, 
        channel: NotificationChannel,
        priority: int = 0,
    ) -> None:
        """
        Регистрация канала уведомлений.
        
        Args:
            name: Имя канала (sms, email, push, telegram)
            channel: Экземпляр канала
            priority: Приоритет (чем выше, тем важнее)
        """
        self._channels[name] = channel
        logger.info(f"Зарегистрирован канал уведомлений: {name}")
    
    def send_notification(
        self,
        recipient: str,
        subject: str,
        message: str,
        channels: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """
        Отправка уведомления через указанные каналы.
        
        Args:
            recipient: Получатель (телефон, email, etc.)
            subject: Тема уведомления
            message: Текст сообщения
            channels: Список каналов (если None, используются все доступные)
        
        Returns:
            Словарь {канал: успех}
        """
        results = {}
        
        channel_names = channels or list(self._channels.keys())
        
        for channel_name in channel_names:
            channel = self._channels.get(channel_name)
            
            if not channel:
                logger.warning(f"Канал {channel_name} не найден")
                results[channel_name] = False
                continue
            
            if not channel.is_available():
                logger.warning(f"Канал {channel_name} недоступен")
                results[channel_name] = False
                continue
            
            try:
                success = channel.send(recipient, subject, message)
                results[channel_name] = success
                
                # Логирование
                self._log_notification(
                    channel=channel_name,
                    recipient=recipient,
                    subject=subject,
                    success=success,
                )
                
                if success:
                    logger.info(f"Уведомление отправлено через {channel_name}: {recipient}")
                else:
                    logger.error(f"Не удалось отправить уведомление через {channel_name}")
                    
            except Exception as e:
                logger.error(f"Ошибка отправки через {channel_name}: {e}", exc_info=True)
                results[channel_name] = False
        
        return results
    
    def send_order_status_notification(
        self,
        client_phone: str,
        client_name: str,
        order_number: str,
        new_status: str,
        device_info: str,
    ) -> Dict[str, bool]:
        """
        Отправка уведомления об изменении статуса заказа.
        
        Шаблонизирует сообщение и отправляет через все доступные каналы.
        """
        subject = f"Заказ #{order_number} - статус изменен"
        
        message = (
            f"Уважаемый(ая) {client_name}!\n\n"
            f"Статус вашего заказа #{order_number} изменен: {new_status}\n"
            f"Устройство: {device_info}\n\n"
            f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"ServiceUP - Сервисный центр"
        )
        
        return self.send_notification(
            recipient=client_phone,
            subject=subject,
            message=message,
        )
    
    def send_order_ready_notification(
        self,
        client_phone: str,
        client_name: str,
        order_number: str,
        total_amount: float,
        address: str = "",
    ) -> Dict[str, bool]:
        """
        Отправка уведомления о готовности заказа к выдаче.
        """
        subject = f"Заказ #{order_number} готов к выдаче!"
        
        message = (
            f"Уважаемый(ая) {client_name}!\n\n"
            f"Ваш заказ #{order_number} готов к выдаче!\n"
            f"Сумма к оплате: {total_amount:.2f} руб.\n"
        )
        
        if address:
            message += f"Адрес выдачи: {address}\n"
        
        message += (
            f"\nДата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"ServiceUP - Сервисный центр"
        )
        
        return self.send_notification(
            recipient=client_phone,
            subject=subject,
            message=message,
        )
    
    def get_notification_history(
        self, 
        recipient: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Получение истории уведомлений.
        
        Args:
            recipient: Фильтр по получателю (None = все)
            limit: Максимальное количество записей
        """
        history = self._notification_log
        
        if recipient:
            history = [h for h in history if h.get('recipient') == recipient]
        
        # Сортировка по дате (новые сначала)
        history = sorted(
            history, 
            key=lambda x: x.get('timestamp', ''), 
            reverse=True
        )
        
        return history[:limit]
    
    def _log_notification(
        self,
        channel: str,
        recipient: str,
        subject: str,
        success: bool,
    ) -> None:
        """Логирование отправки уведомления."""
        self._notification_log.append({
            'timestamp': datetime.now().isoformat(),
            'channel': channel,
            'recipient': recipient,
            'subject': subject,
            'success': success,
        })
        
        # Ограничение размера лога в памяти
        if len(self._notification_log) > 1000:
            self._notification_log = self._notification_log[-500:]


# ============================================================================
# Примеры реализации каналов (для расширения)
# ============================================================================

class BaseNotificationChannel(ABC):
    """Базовый класс для каналов уведомлений."""
    
    @abstractmethod
    def send(self, recipient: str, subject: str, message: str) -> bool:
        """Отправка уведомления."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Проверка доступности канала."""
        pass


class SMSChannel(BaseNotificationChannel):
    """
    SMS-канал уведомлений.
    
    Для реальной реализации используйте:
    - twilio
    - sms.ru
    - prostor-sms
    """
    
    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._available = bool(api_key)
    
    def send(self, recipient: str, subject: str, message: str) -> bool:
        """Отправка SMS (заглушка)."""
        if not self._available:
            return False
        
        # TODO: Интеграция с SMS-провайдером
        logger.info(f"SMS отправлено на {recipient}: {message[:50]}...")
        return True
    
    def is_available(self) -> bool:
        return self._available


class EmailChannel(BaseNotificationChannel):
    """
    Email-канал уведомлений.
    
    Для реальной реализации используйте:
    - smtplib (стандартная библиотека)
    - aiosmtplib
    - sendgrid
    """
    
    def __init__(self, smtp_host: str = "", smtp_port: int = 0, login: str = ""):
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._login = login
        self._available = bool(smtp_host and login)
    
    def send(self, recipient: str, subject: str, message: str) -> bool:
        """Отправка Email (заглушка)."""
        if not self._available:
            return False
        
        # TODO: Интеграция с SMTP-сервером
        logger.info(f"Email отправлен на {recipient}: {subject}")
        return True
    
    def is_available(self) -> bool:
        return self._available


class TelegramChannel(BaseNotificationChannel):
    """
    Telegram-канал уведомлений.
    
    Для реальной реализации используйте:
    - python-telegram-bot
    - aiogram
    """
    
    def __init__(self, bot_token: str = ""):
        self._bot_token = bot_token
        self._available = bool(bot_token)
    
    def send(self, recipient: str, subject: str, message: str) -> bool:
        """Отправка сообщения в Telegram (заглушка)."""
        if not self._available:
            return False
        
        # TODO: Интеграция с Telegram Bot API
        logger.info(f"Telegram сообщение отправлено {recipient}: {subject}")
        return True
    
    def is_available(self) -> bool:
        return self._available


class PushChannel(BaseNotificationChannel):
    """
    Push-канал для PWA-приложения.
    
    Для реальной реализации используйте:
    - websockets
    - firebase cloud messaging
    """
    
    def __init__(self, websocket_url: str = ""):
        self._websocket_url = websocket_url
        self._available = bool(websocket_url)
        self._connected_clients: set = set()
    
    def send(self, recipient: str, subject: str, message: str) -> bool:
        """Отправка Push-уведомления (заглушка)."""
        if not self._available:
            return False
        
        # TODO: Интеграция с WebSocket сервером
        logger.info(f"Push отправлен клиенту {recipient}: {subject}")
        return True
    
    def is_available(self) -> bool:
        return self._available
    
    def connect_client(self, client_id: str) -> None:
        """Подключение клиента к WebSocket."""
        self._connected_clients.add(client_id)
    
    def disconnect_client(self, client_id: str) -> None:
        """Отключение клиента от WebSocket."""
        self._connected_clients.discard(client_id)
