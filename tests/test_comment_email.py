import json
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings, settings
from app.domain.engagement.models import Comment, ContentType
from app.domain.engagement.notifications import build_comment_email
from app.infrastructure.email import (
    BrevoEmailSender,
    EmailDeliveryError,
    EmailMessage,
    get_email_sender,
)
from app.main import app
from tests.test_engagement import create_product

OWNER = "owner@example.com"


class FakeSender:
    """Records messages; fails with the given errors first, then succeeds."""

    def __init__(self, failures: list[EmailDeliveryError] | None = None):
        self.failures = list(failures or [])
        self.attempts = 0
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.attempts += 1
        if self.failures:
            raise self.failures.pop(0)
        self.sent.append(message)


@pytest.fixture
def email_on(monkeypatch):
    monkeypatch.setattr(settings, "NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "COMMENT_NOTIFY_EMAIL", OWNER)
    monkeypatch.setattr(settings, "NOTIFICATION_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "NOTIFICATION_RETRY_BACKOFF_SECONDS", 0)

    def use(sender):
        app.dependency_overrides[get_email_sender] = lambda: sender
        return sender

    return use


async def post_comment(client, product_id, **overrides):
    payload = {
        "author_name": "Jānis <b>",
        "body": "Labi!\n<script>alert(1)</script>",
        **overrides,
    }
    return await client.post(
        f"/api/v1/engagement/product/{product_id}/comments", json=payload
    )


async def stored_comment(db_factory) -> Comment:
    async with db_factory() as session:
        return (await session.scalars(select(Comment))).one()


@pytest.mark.asyncio
async def test_owner_is_emailed_about_new_comment(admin_client, db_factory, email_on):
    sender = email_on(FakeSender())
    product_id = await create_product(admin_client, is_published=True)

    response = await post_comment(admin_client, product_id)
    assert response.status_code == 202, response.text

    assert len(sender.sent) == 1
    message = sender.sent[0]
    assert message.to == OWNER
    # Title comes in Latvian (create_product uses "Glezna" for lv).
    assert message.subject == "Jauns komentārs: Glezna"
    assert "Mākslas darbs: Glezna" in message.text
    assert "Autors: Jānis <b>" in message.text
    assert "<script>alert(1)</script>" in message.text
    # HTML part must never contain visitor markup unescaped.
    assert "<script>" not in message.html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in message.html
    assert "Jānis &lt;b&gt;" in message.html

    comment = await stored_comment(db_factory)
    assert comment.notified_at is not None
    queue = (await admin_client.get("/api/v1/engagement/manage/comments")).json()
    assert queue["items"][0]["notified_at"] is not None


@pytest.mark.asyncio
async def test_transient_failures_are_retried(admin_client, db_factory, email_on):
    sender = email_on(
        FakeSender(
            [
                EmailDeliveryError("timeout", retryable=True),
                EmailDeliveryError("HTTP 503", retryable=True),
            ]
        )
    )
    product_id = await create_product(admin_client, is_published=True)
    assert (await post_comment(admin_client, product_id)).status_code == 202
    assert sender.attempts == 3
    assert len(sender.sent) == 1
    assert (await stored_comment(db_factory)).notified_at is not None


@pytest.mark.asyncio
async def test_comment_is_kept_when_email_keeps_failing(admin_client, db_factory, email_on):
    sender = email_on(
        FakeSender([EmailDeliveryError("down", retryable=True) for _ in range(5)])
    )
    product_id = await create_product(admin_client, is_published=True)

    response = await post_comment(admin_client, product_id)
    assert response.status_code == 202
    assert sender.attempts == 3  # NOTIFICATION_MAX_ATTEMPTS
    comment = await stored_comment(db_factory)
    assert comment.status == "pending"
    assert comment.notified_at is None


@pytest.mark.asyncio
async def test_permanent_failure_is_not_retried(admin_client, db_factory, email_on):
    sender = email_on(FakeSender([EmailDeliveryError("HTTP 401", retryable=False)]))
    product_id = await create_product(admin_client, is_published=True)
    assert (await post_comment(admin_client, product_id)).status_code == 202
    assert sender.attempts == 1
    assert (await stored_comment(db_factory)).notified_at is None


@pytest.mark.asyncio
async def test_no_email_when_disabled_or_honeypot(admin_client, db_factory, email_on):
    product_id = await create_product(admin_client, is_published=True)

    trapped_sender = email_on(FakeSender())
    await post_comment(admin_client, product_id, website="http://spam.example")
    assert trapped_sender.attempts == 0

    app.dependency_overrides[get_email_sender] = lambda: None  # disabled
    assert (await post_comment(admin_client, product_id)).status_code == 202
    assert (await stored_comment(db_factory)).notified_at is None


def test_email_template_shapes_subject_and_escapes():
    message = build_comment_email(
        to=OWNER,
        author_name='Anna" onmouseover="x',
        body="a & b\nsecond line",
        target_type=ContentType.MUSIC_CLIP,
        target_title="Line\r\nBreak " + "x" * 200,
        created_at=datetime(2026, 11, 11, 9, 30),
    )
    assert "\n" not in message.subject and "\r" not in message.subject
    assert len(message.subject) <= len("Jauns komentārs: ") + 120
    assert "Videoklips: Line Break" in message.text
    assert "11.11.2026 09:30 UTC" in message.text
    assert "a &amp; b<br>\nsecond line" in message.html
    assert 'Anna&quot; onmouseover=&quot;x' in message.html


# ---- Brevo client --------------------------------------------------------


def brevo(handler) -> BrevoEmailSender:
    return BrevoEmailSender(
        api_key="test-key",
        sender_email="noreply@example.com",
        sender_name="Amor Fati",
        transport=httpx.MockTransport(handler),
    )


MESSAGE = EmailMessage(to=OWNER, subject="S", html="<p>H</p>", text="T")


@pytest.mark.asyncio
async def test_brevo_request_format():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["api-key"]
        seen["json"] = json.loads(request.content)
        return httpx.Response(201, json={"messageId": "<id@brevo>"})

    await brevo(handler).send(MESSAGE)
    assert seen["url"] == "https://api.brevo.com/v3/smtp/email"
    assert seen["key"] == "test-key"
    assert seen["json"] == {
        "sender": {"email": "noreply@example.com", "name": "Amor Fati"},
        "to": [{"email": OWNER}],
        "subject": "S",
        "htmlContent": "<p>H</p>",
        "textContent": "T",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "retryable"), [(500, True), (503, True), (429, True), (400, False), (401, False)]
)
async def test_brevo_error_classification(status_code, retryable):
    sender = brevo(lambda request: httpx.Response(status_code, json={"message": "x"}))
    with pytest.raises(EmailDeliveryError) as error:
        await sender.send(MESSAGE)
    assert error.value.retryable is retryable
    assert "test-key" not in str(error.value)


@pytest.mark.asyncio
async def test_brevo_timeout_is_retryable():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(EmailDeliveryError) as error:
        await brevo(handler).send(MESSAGE)
    assert error.value.retryable is True


def test_enabling_notifications_requires_brevo_settings():
    base = {
        "POSTGRES_URL": "postgresql+asyncpg://u:p@localhost/db",
        "SECRET_KEY": "x" * 40,
        "NOTIFICATIONS_ENABLED": True,
    }
    with pytest.raises(ValueError, match="BREVO_API_KEY, MAIL_FROM, COMMENT_NOTIFY_EMAIL"):
        Settings(**base, _env_file=None)
    with pytest.raises(ValueError, match="MAIL_FROM must be an email"):
        Settings(
            **base,
            BREVO_API_KEY="k",
            MAIL_FROM="not-an-email",
            COMMENT_NOTIFY_EMAIL=OWNER,
            _env_file=None,
        )
    ok = Settings(
        **base,
        BREVO_API_KEY="k",
        MAIL_FROM="noreply@example.com",
        COMMENT_NOTIFY_EMAIL=OWNER,
        _env_file=None,
    )
    assert ok.BREVO_API_KEY.get_secret_value() == "k"
    assert "k" not in repr(ok.BREVO_API_KEY)
