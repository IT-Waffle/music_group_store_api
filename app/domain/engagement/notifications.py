"""Owner email about a new comment.

Runs as a FastAPI background task after the comment is committed and the
202 response is sent, so email problems never lose or delay a comment.
Delivery is retried a few times in-process; if it still fails the comment
simply stays without `notified_at` (visible in the moderation queue).
"""

import asyncio
import html
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.infrastructure.email import BrevoEmailSender, EmailDeliveryError, EmailMessage

from .models import Comment, ContentType
from .repository import EngagementRepository

logger = logging.getLogger(__name__)

# The owner reads Latvian; titles are taken in Latvian as well.
EMAIL_LANGUAGE = "lv"
TARGET_LABELS = {
    ContentType.PRODUCT: "Mākslas darbs",
    ContentType.MUSIC_TRACK: "Dziesma",
    ContentType.MUSIC_CLIP: "Videoklips",
}
SUBJECT_TITLE_MAX = 120


def _single_line(value: str) -> str:
    return " ".join(value.split())


def build_comment_email(
    *,
    to: str,
    author_name: str,
    body: str,
    target_type: ContentType,
    target_title: str,
    created_at: datetime,
) -> EmailMessage:
    """Plain template. All visitor-provided text is HTML-escaped."""
    label = TARGET_LABELS[target_type]
    title = _single_line(target_title) or "—"
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    when = created_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    subject_title = title if len(title) <= SUBJECT_TITLE_MAX else title[: SUBJECT_TITLE_MAX - 1] + "…"
    subject = f"Jauns komentārs: {subject_title}"

    text = (
        "Jauns komentārs gaida moderāciju.\n\n"
        f"{label}: {title}\n"
        f"Autors: {author_name}\n"
        f"Datums: {when}\n\n"
        f"Komentārs:\n{body}\n\n"
        "Komentārs nav publicēts, kamēr to neapstiprina administrācijas panelī.\n"
    )

    def esc(value: str) -> str:
        return html.escape(value, quote=True)

    body_html = esc(body).replace("\n", "<br>\n")
    html_content = f"""<!doctype html>
<html lang="lv">
<body style="font-family: Arial, sans-serif; color: #111; line-height: 1.5;">
  <h2 style="margin: 0 0 16px;">Jauns komentārs gaida moderāciju</h2>
  <p style="margin: 0 0 4px;"><strong>{esc(label)}:</strong> {esc(title)}</p>
  <p style="margin: 0 0 4px;"><strong>Autors:</strong> {esc(author_name)}</p>
  <p style="margin: 0 0 16px;"><strong>Datums:</strong> {esc(when)}</p>
  <div style="padding: 12px 16px; border-left: 4px solid #999; background: #f5f5f5;">{body_html}</div>
  <p style="margin: 16px 0 0; color: #666; font-size: 13px;">Komentārs nav publicēts, kamēr to neapstiprina administrācijas panelī.</p>
</body>
</html>
"""
    return EmailMessage(to=to, subject=subject, html=html_content, text=text)


async def _deliver(sender: BrevoEmailSender, message: EmailMessage, sleep) -> bool:
    attempts = settings.NOTIFICATION_MAX_ATTEMPTS
    for attempt in range(1, attempts + 1):
        try:
            await sender.send(message)
            return True
        except EmailDeliveryError as exc:
            if not exc.retryable or attempt == attempts:
                logger.error(
                    "Comment notification not delivered after %s attempt(s): %s",
                    attempt,
                    exc,
                )
                return False
            logger.warning("Comment notification attempt %s failed: %s", attempt, exc)
            await sleep(settings.NOTIFICATION_RETRY_BACKOFF_SECONDS * attempt)
    return False


async def notify_new_comment(
    comment_id: uuid.UUID,
    session_factory: async_sessionmaker,
    sender: BrevoEmailSender,
    *,
    sleep=asyncio.sleep,
) -> None:
    try:
        async with session_factory() as session:
            repository = EngagementRepository(session)
            comment = await repository.get_comment(comment_id)
            if comment is None or comment.notified_at is not None:
                return  # deleted meanwhile, or already notified
            target_type = ContentType(comment.target_type)
            titles = await repository.get_titles(
                [(target_type, comment.target_id)], EMAIL_LANGUAGE
            )
            message = build_comment_email(
                to=settings.COMMENT_NOTIFY_EMAIL or "",
                author_name=comment.author_name,
                body=comment.body,
                target_type=target_type,
                target_title=titles.get((target_type, comment.target_id), ""),
                created_at=comment.created_at,
            )

        # No DB connection is held while talking to the provider.
        if not await _deliver(sender, message, sleep):
            return

        async with session_factory() as session:
            await session.execute(
                update(Comment)
                .where(Comment.id == comment_id)
                .values(notified_at=datetime.now(timezone.utc))
            )
            await session.commit()
    except Exception:
        logger.exception("Unexpected error while sending comment notification")
