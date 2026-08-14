"""
Notifications Service - Multi-channel Communication Hub

SRP: Handles sending notifications through various channels.
Supports: Telegram, WhatsApp, VK, Email, Bluetooth Calls.

Uses Strategy Pattern for channel selection.
Uses Adapter Pattern for different messaging APIs.
"""

from .telegram_adapter import TelegramAdapter
from .whatsapp_adapter import WhatsAppAdapter
from .vk_adapter import VKAdapter
from .email_adapter import EmailAdapter
from .bluetooth_adapter import BluetoothCallAdapter
from .notification_service import NotificationService, NotificationChannel, NotificationMessage, NotificationResult

__all__ = [
    # Core Service
    'NotificationService',
    
    # Domain Models
    'NotificationChannel',
    'NotificationMessage',
    'NotificationResult',
    
    # Adapters (Strategy Pattern)
    'TelegramAdapter',
    'WhatsAppAdapter',
    'VKAdapter',
    'EmailAdapter',
    'BluetoothCallAdapter',
]
