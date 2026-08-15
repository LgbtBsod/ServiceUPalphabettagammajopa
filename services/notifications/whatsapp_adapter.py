"""WhatsApp Business API Adapter"""

from .notification_service import (
    NotificationChannel,
    NotificationMessage,
    NotificationResult,
)


class WhatsAppAdapter:
    """WhatsApp Business API adapter (using Meta Graph API)"""

    def __init__(self, api_key: str, phone_number_id: str):
        self.api_key = api_key
        self.phone_number_id = phone_number_id
        self.base_url = "https://graph.facebook.com/v17.0"

    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Send WhatsApp message"""
        # Placeholder implementation
        return NotificationResult(
            success=False,
            channel=NotificationChannel.WHATSAPP,
            recipient=message.recipient,
            error="WhatsApp integration requires API configuration",
        )

    async def test_connection(self) -> bool:
        """Test WhatsApp API connection"""
        return False
