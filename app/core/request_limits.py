"""Request body limits enforced before FastAPI reads the body.

FastAPI parses the request body (and spools multipart uploads to disk) before
it runs dependencies such as authentication. Without this middleware an
anonymous client could push a huge JSON body into memory or a huge upload to
disk and only then get a 401. Here:

- every POST/PUT/PATCH body is capped (MAX_REQUEST_BODY_BYTES, 1 MiB);
- the few upload routes get their own, larger cap, and require a valid,
  unexpired Bearer token *before* any byte of the body is accepted
  (the role check itself still happens in the route).
"""

import json
import re
from collections.abc import Callable, Sequence

import jwt
from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

BODY_METHODS = {"POST", "PUT", "PATCH"}
# Multipart framing (boundaries, part headers) on top of the file itself.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class BodyTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=413,
            detail={"code": "REQUEST_TOO_LARGE", "message": "Request body is too large."},
        )

    def detail_body(self) -> dict:
        return {"detail": self.detail}


UploadRule = tuple[re.Pattern[str], Callable[[], int]]


class RequestLimitsMiddleware:
    def __init__(self, app: ASGIApp, upload_rules: Sequence[UploadRule] = ()):
        self.app = app
        self.upload_rules = list(upload_rules)

    def _upload_limit(self, path: str) -> int | None:
        for pattern, limit in self.upload_rules:
            if pattern.match(path):
                return limit() + MULTIPART_OVERHEAD_BYTES
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in BODY_METHODS:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope["headers"]}
        upload_limit = self._upload_limit(scope["path"])
        if upload_limit is not None and not _has_valid_bearer(headers):
            await _send_json(
                send,
                401,
                {"detail": "Not authenticated"},
                extra_headers=[(b"www-authenticate", b"Bearer")],
            )
            return
        limit = upload_limit if upload_limit is not None else settings.MAX_REQUEST_BODY_BYTES

        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    await _send_json(send, 413, BodyTooLarge().detail_body())
                    return
            except ValueError:
                await _send_json(send, 400, {"detail": "Invalid Content-Length"})
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Raised inside body reading; FastAPI re-raises
                    # HTTPException unchanged, so the client gets a 413.
                    raise BodyTooLarge()
            return message

        await self.app(scope, limited_receive, send)


def _has_valid_bearer(headers: dict[bytes, bytes]) -> bool:
    value = headers.get(b"authorization", b"").decode("latin-1")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    try:
        jwt.decode(token.strip(), settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.InvalidTokenError:
        return False
    return True


async def _send_json(
    send: Send,
    status_code: int,
    payload: dict,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    body = json.dumps(payload).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
                *(extra_headers or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
