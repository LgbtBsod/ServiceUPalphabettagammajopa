"""Notifications Service - Multi-channel Communication Hub

SRP: Handles sending notifications through various channels.
Supports: Telegram, WhatsApp, VK, Email, Bluetooth Calls.

Uses Strategy Pattern for channel selection.
Uses Adapter Pattern for different messaging APIs.
"""

from .bluetooth_adapter import BluetoothCallAdapter
from .email_adapter import EmailAdapter
from .notification_service import (
    NotificationChannel,
    NotificationMessage,
    NotificationResult,
    NotificationService,
)
from .telegram_adapter import TelegramAdapter
from .vk_adapter import VKAdapter
from .whatsapp_adapter import WhatsAppAdapter

__all__ = [
    "BluetoothCallAdapter",
    "EmailAdapter",
    # Domain Models
    "NotificationChannel",
    "NotificationMessage",
    "NotificationResult",
    # Core Service
    "NotificationService",
    # Adapters (Strategy Pattern)
    "TelegramAdapter",
    "VKAdapter",
    "WhatsAppAdapter",
]
