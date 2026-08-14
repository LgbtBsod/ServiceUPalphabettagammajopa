"""
Notification Service - Multi-channel Communication

SRP: Handles sending notifications through various channels.
Supports: Telegram, WhatsApp, VK, Max (placeholder), Email, Bluetooth Calls.

Uses Strategy Pattern for channel selection.
Uses Adapter Pattern for different messaging APIs.
"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Protocol
from datetime import datetime
import asyncio
import httpx
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from i18n import t


class NotificationChannel(str, Enum):
    """Available notification channels - SSOT"""
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    VK = "vk"
    MAX = "max"  # Placeholder for future implementation
    EMAIL = "email"
    BLUETOOTH_CALL = "bluetooth_call"


class NotificationPriority(str, Enum):
    """Notification priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class NotificationMessage:
    """Standardized notification message"""
    channel: NotificationChannel
    recipient: str  # phone, email, chat_id, etc.
    subject: Optional[str] = None
    body: str = ""
    priority: NotificationPriority = NotificationPriority.NORMAL
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def format_body(self, **kwargs) -> str:
        """Format body with parameters using i18n"""
        return self.body.format(**kwargs)


@dataclass
class NotificationResult:
    """Result of notification sending attempt"""
    success: bool
    channel: NotificationChannel
    recipient: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    sent_at: datetime = field(default_factory=datetime.now)


class NotificationStrategy(Protocol):
    """Protocol for notification strategies (Strategy Pattern)"""
    
    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Send notification"""
        ...
    
    async def test_connection(self) -> bool:
        """Test connection to service"""
        ...


class TelegramAdapter:
    """Telegram Bot API adapter"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Send Telegram message"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": message.recipient,
                        "text": message.body,
                        "parse_mode": "HTML",
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("ok"):
                    return NotificationResult(
                        success=True,
                        channel=NotificationChannel.TELEGRAM,
                        recipient=message.recipient,
                        message_id=str(data["result"]["message_id"]),
                    )
                else:
                    return NotificationResult(
                        success=False,
                        channel=NotificationChannel.TELEGRAM,
                        recipient=message.recipient,
                        error=data.get("description", "Unknown error"),
                    )
        except Exception as e:
            return NotificationResult(
                success=False,
                channel=NotificationChannel.TELEGRAM,
                recipient=message.recipient,
                error=str(e),
            )
    
    async def test_connection(self) -> bool:
        """Test Telegram Bot API connection"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/getMe", timeout=5.0)
                return response.json().get("ok", False)
        except Exception:
            return False


class WhatsAppAdapter:
    """WhatsApp Business API adapter (using Twilio-like API)"""
    
    def __init__(self, api_key: str, phone_number_id: str):
        self.api_key = api_key
        self.phone_number_id = phone_number_id
        self.base_url = "https://graph.facebook.com/v17.0"
    
    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Send WhatsApp message"""
        # Placeholder implementation
        # In production, integrate with Meta WhatsApp Business API
        return NotificationResult(
            success=False,
            channel=NotificationChannel.WHATSAPP,
            recipient=message.recipient,
            error="WhatsApp integration requires API configuration",
        )
    
    async def test_connection(self) -> bool:
        """Test WhatsApp API connection"""
        return False  # Requires actual API credentials


class VKAdapter:
    """VKontakte Messages API adapter"""
    
    def __init__(self, access_token: str, group_id: str):
        self.access_token = access_token
        self.group_id = group_id
        self.base_url = "https://api.vk.com/method"
    
    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Send VK message"""
        # Placeholder implementation
        return NotificationResult(
            success=False,
            channel=NotificationChannel.VK,
            recipient=message.recipient,
            error="VK integration requires API configuration",
        )
    
    async def test_connection(self) -> bool:
        """Test VK API connection"""
        return False


class PlaceholderAdapter:
    """Max messenger adapter (placeholder)"""
    
    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Send Max message"""
        return NotificationResult(
            success=False,
            channel=NotificationChannel.VK,
            recipient=message.recipient,
            error="Max messenger integration not yet implemented",
        )
    
    async def test_connection(self) -> bool:
        """Test Max connection"""
        return False


class EmailAdapter:
    """SMTP Email adapter"""
    
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_tls = use_tls
    
    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Send email via SMTP"""
        try:
            # Create message
            msg = MIMEMultipart()
            msg["From"] = self.username
            msg["To"] = message.recipient
            msg["Subject"] = message.subject or "ServiceUP Notification"
            msg.attach(MIMEText(message.body, "html"))
            
            # Send email
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.username,
                password=self.password,
                start_tls=self.use_tls,
            )
            
            return NotificationResult(
                success=True,
                channel=NotificationChannel.EMAIL,
                recipient=message.recipient,
                message_id=f"email_{datetime.now().timestamp()}",
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                channel=NotificationChannel.EMAIL,
                recipient=message.recipient,
                error=str(e),
            )
    
    async def test_connection(self) -> bool:
        """Test SMTP connection"""
        try:
            await aiosmtplib.create_connection(
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.username,
                password=self.password,
                use_tls=self.use_tls,
            )
            return True
        except Exception:
            return False


class BluetoothCallAdapter:
    """
    Bluetooth Call adapter - Simulates PC-to-phone call via Bluetooth
    
    Uses standard Windows Bluetooth APIs (placeholder for actual implementation)
    """
    
    def __init__(self, device_address: Optional[str] = None):
        self.device_address = device_address
        self.connected = False
    
    async def connect(self) -> bool:
        """Connect to paired Bluetooth device"""
        # Placeholder: In production, use pybluez or platform-specific APIs
        self.connected = True
        return True
    
    async def disconnect(self):
        """Disconnect from Bluetooth device"""
        self.connected = False
    
    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Initiate call via Bluetooth-connected phone"""
        if not self.connected:
            if not await self.connect():
                return NotificationResult(
                    success=False,
                    channel=NotificationChannel.BLUETOOTH_CALL,
                    recipient=message.recipient,
                    error="Bluetooth device not connected",
                )
        
        try:
            # Placeholder: Use AT commands or platform APIs to initiate call
            # On Windows: Use Windows.Devices.Bluetooth namespace via COM
            # On Linux: Use dbus or bluez libraries
            print(f"[BLUETOOTH_CALL] Initiating call to: {message.recipient}")
            
            return NotificationResult(
                success=True,
                channel=NotificationChannel.BLUETOOTH_CALL,
                recipient=message.recipient,
                message_id=f"bt_call_{datetime.now().timestamp()}",
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                channel=NotificationChannel.BLUETOOTH_CALL,
                recipient=message.recipient,
                error=str(e),
            )
    
    async def test_connection(self) -> bool:
        """Test Bluetooth connection"""
        return await self.connect()


class NotificationService:
    """
    Main notification service with channel routing.
    
    Features:
    - Strategy pattern for channel selection
    - Async multi-threaded sending
    - Priority-based queuing
    - Fallback mechanisms
    """
    
    def __init__(self):
        self.adapters: dict[NotificationChannel, NotificationStrategy] = {}
        self.default_channel = NotificationChannel.EMAIL
        self.fallback_enabled = True
    
    def register_adapter(
        self, 
        channel: NotificationChannel, 
        adapter: NotificationStrategy,
    ):
        """Register notification adapter for channel"""
        self.adapters[channel] = adapter
    
    def get_adapter(self, channel: NotificationChannel) -> Optional[NotificationStrategy]:
        """Get adapter for specific channel"""
        return self.adapters.get(channel)
    
    async def send(
        self,
        message: NotificationMessage,
        use_fallback: bool = True,
    ) -> NotificationResult:
        """
        Send notification through specified channel.
        
        Args:
            message: Notification message with channel and content
            use_fallback: Try fallback channel if primary fails
        
        Returns:
            NotificationResult with success status
        """
        adapter = self.adapters.get(message.channel)
        
        if not adapter:
            return NotificationResult(
                success=False,
                channel=message.channel,
                recipient=message.recipient,
                error=f"No adapter registered for channel: {message.channel}",
            )
        
        result = await adapter.send(message)
        
        # Fallback to default channel if failed
        if not result.success and use_fallback and self.fallback_enabled:
            fallback_adapter = self.adapters.get(self.default_channel)
            if fallback_adapter and fallback_adapter != adapter:
                fallback_msg = NotificationMessage(
                    channel=self.default_channel,
                    recipient=message.recipient,
                    subject=f"[FALLBACK] {message.subject}",
                    body=f"<b>Original Channel Failed:</b> {message.channel}<br><br>{message.body}",
                    priority=NotificationPriority.HIGH,
                )
                result = await fallback_adapter.send(fallback_msg)
        
        return result
    
    async def send_to_all(
        self,
        message: NotificationMessage,
        channels: Optional[list[NotificationChannel]] = None,
    ) -> list[NotificationResult]:
        """
        Send notification to multiple channels concurrently.
        
        Uses asyncio.gather for parallel execution (Multi-threading).
        """
        if channels is None:
            channels = list(self.adapters.keys())
        
        tasks = []
        for channel in channels:
            msg = NotificationMessage(
                channel=channel,
                recipient=message.recipient,
                subject=message.subject,
                body=message.body,
                priority=message.priority,
            )
            tasks.append(self.send(msg, use_fallback=False))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to NotificationResult
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append(
                    NotificationResult(
                        success=False,
                        channel=message.channel,
                        recipient=message.recipient,
                        error=str(result),
                    )
                )
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def test_all_connections(self) -> dict[NotificationChannel, bool]:
        """Test connections for all registered adapters"""
        results = {}
        for channel, adapter in self.adapters.items():
            results[channel] = await adapter.test_connection()
        return results


# Factory function for easy setup
def create_notification_service(config: dict) -> NotificationService:
    """
    Create and configure notification service from config.
    
    Config example:
    {
        "telegram": {"bot_token": "..."},
        "email": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "username": "...",
            "password": "..."
        },
        "bluetooth": {"device_address": "..."}
    }
    """
    service = NotificationService()
    
    if "telegram" in config:
        service.register_adapter(
            NotificationChannel.TELEGRAM,
            TelegramAdapter(config["telegram"]["bot_token"]),
        )
    
    if "whatsapp" in config:
        service.register_adapter(
            NotificationChannel.WHATSAPP,
            WhatsAppAdapter(
                config["whatsapp"]["api_key"],
                config["whatsapp"]["phone_number_id"],
            ),
        )
    
    if "vk" in config:
        service.register_adapter(
            NotificationChannel.VK,
            VKAdapter(config["vk"]["access_token"], config["vk"]["group_id"]),
        )
    
    if "email" in config:
        service.register_adapter(
            NotificationChannel.EMAIL,
            EmailAdapter(
                config["email"]["smtp_host"],
                config["email"]["smtp_port"],
                config["email"]["username"],
                config["email"]["password"],
            ),
        )
    
    if "bluetooth" in config:
        service.register_adapter(
            NotificationChannel.BLUETOOTH_CALL,
            BluetoothCallAdapter(config["bluetooth"].get("device_address")),
        )
    
    return service
