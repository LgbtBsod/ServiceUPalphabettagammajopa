"""SMTP Email Adapter"""

from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from .notification_service import (
    NotificationChannel,
    NotificationMessage,
    NotificationResult,
)


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
