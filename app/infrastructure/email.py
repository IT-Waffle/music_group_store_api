"""Minimal transactional email client (Brevo HTTP API).

HTTP instead of SMTP on purpose: DigitalOcean blocks outbound SMTP ports on
droplets by default, HTTPS is always open, and httpx is already a dependency.
"""

import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html: str
    text: str


class EmailDeliveryError(Exception):
    """Sending failed. `retryable` tells whether trying again may help."""

    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class BrevoEmailSender:
    def __init__(
        self,
        api_key: str,
        sender_email: str,
        sender_name: str,
        *,
        api_url: str = "https://api.brevo.com/v3/smtp/email",
        timeout: float = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._api_key = api_key
        self._sender = {"email": sender_email, "name": sender_name}
        self._api_url = api_url
        self._timeout = timeout
        self._transport = transport

    async def send(self, message: EmailMessage) -> None:
        payload = {
            "sender": self._sender,
            "to": [{"email": message.to}],
            "subject": message.subject,
            "htmlContent": message.html,
            "textContent": message.text,
        }
        headers = {
            "api-key": self._api_key,
            "accept": "application/json",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(self._api_url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise EmailDeliveryError("Email provider timed out", retryable=True) from exc
        except httpx.TransportError as exc:
            raise EmailDeliveryError("Email provider unreachable", retryable=True) from exc

        if response.is_success:
            return
        # 429 and 5xx are temporary; other 4xx (bad key, unverified sender,
        # invalid payload) will not fix themselves on retry.
        retryable = response.status_code == 429 or response.status_code >= 500
        raise EmailDeliveryError(
            f"Email provider returned HTTP {response.status_code}", retryable=retryable
        )


def get_email_sender() -> BrevoEmailSender | None:
    """FastAPI dependency: the configured sender, or None when disabled."""
    if not settings.NOTIFICATIONS_ENABLED or settings.BREVO_API_KEY is None:
        return None
    return BrevoEmailSender(
        api_key=settings.BREVO_API_KEY.get_secret_value(),
        sender_email=settings.MAIL_FROM or "",
        sender_name=settings.MAIL_FROM_NAME,
        api_url=settings.BREVO_API_URL,
        timeout=settings.NOTIFICATION_TIMEOUT_SECONDS,
    )
