"""Telegram Bot API Adapter"""
from .notification_service import NotificationMessage, NotificationResult, NotificationChannel
import httpx

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
