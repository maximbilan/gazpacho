from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from src.reader.models import DownloadedImage, NormalizedMessage, ReaderResult

logger = logging.getLogger(__name__)


def parse_chat_ref(value: str) -> str | int:
    stripped = value.strip()
    if stripped.lstrip("-").isdigit():
        return int(stripped)
    return stripped


def media_kind(message: Any) -> str | None:
    if getattr(message, "photo", None):
        return "photo"

    document = getattr(message, "document", None)
    if document is not None:
        mime_type = getattr(document, "mime_type", None)
        if mime_type and mime_type.startswith("image/"):
            return "image_document"
        return "document"

    if getattr(message, "media", None):
        return "other_media"

    return None


def is_downloadable_image(message: Any) -> bool:
    return media_kind(message) in {"photo", "image_document"}


def document_mime_type(message: Any) -> str | None:
    document = getattr(message, "document", None)
    if document is None:
        return "image/jpeg" if getattr(message, "photo", None) else None
    return getattr(document, "mime_type", None)


def entity_name(entity: Any, fallback: str) -> str:
    for attr in ("title", "username", "first_name"):
        value = getattr(entity, attr, None)
        if value:
            return str(value)
    return fallback


async def sender_name(message: Any) -> str | None:
    if getattr(message, "post_author", None):
        return str(message.post_author)

    sender = await message.get_sender()
    if sender is None:
        sender_id = getattr(message, "sender_id", None)
        return str(sender_id) if sender_id else None

    parts = [
        getattr(sender, "first_name", None),
        getattr(sender, "last_name", None),
    ]
    display_name = " ".join(part for part in parts if part)
    if display_name:
        return display_name
    if getattr(sender, "username", None):
        return f"@{sender.username}"
    if getattr(sender, "id", None):
        return str(sender.id)
    return None


class TelegramReader:
    def __init__(self, api_id: int, api_hash: str, string_session: str) -> None:
        self.client = TelegramClient(StringSession(string_session), api_id, api_hash)

    async def __aenter__(self) -> "TelegramReader":
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError(
                "Telethon StringSession is not authorized. Run scripts/login.py again."
            )
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.client.disconnect()

    async def read_recent(
        self,
        chat_refs: list[str],
        lookback_days: int,
        download_dir: Path,
        now: datetime | None = None,
    ) -> ReaderResult:
        window_end = now or datetime.now(timezone.utc)
        if window_end.tzinfo is None:
            window_end = window_end.replace(tzinfo=timezone.utc)
        window_start = window_end - timedelta(days=lookback_days)

        download_dir.mkdir(parents=True, exist_ok=True)
        result = ReaderResult()

        for raw_ref in chat_refs:
            await self._read_chat(raw_ref, window_start, download_dir, result)

        result.messages.sort(key=lambda item: item.date_iso)
        return result

    async def _read_chat(
        self,
        raw_ref: str,
        window_start: datetime,
        download_dir: Path,
        result: ReaderResult,
    ) -> None:
        chat_ref = parse_chat_ref(raw_ref)
        chat_dir = download_dir / _safe_path_part(str(raw_ref))
        chat_dir.mkdir(parents=True, exist_ok=True)
        chat_name = str(raw_ref)
        seen_message_ids: set[int] = set()

        while True:
            try:
                entity = await self.client.get_entity(chat_ref)
                chat_name = entity_name(entity, str(raw_ref))

                logger.info(
                    "Reading Telegram chat %s since %s",
                    chat_name,
                    window_start.isoformat(),
                )

                async for message in self.client.iter_messages(entity):
                    if message.date is None:
                        continue

                    message_date = message.date
                    if message_date.tzinfo is None:
                        message_date = message_date.replace(tzinfo=timezone.utc)

                    if message_date < window_start:
                        break

                    if message.id in seen_message_ids:
                        continue
                    seen_message_ids.add(message.id)

                    normalized = NormalizedMessage(
                        chat_name=chat_name,
                        chat_ref=str(raw_ref),
                        message_id=message.id,
                        sender=await sender_name(message),
                        date_iso=message_date.astimezone(timezone.utc).isoformat(),
                        text=message.message or "",
                        has_media=bool(getattr(message, "media", None)),
                        media_kind=media_kind(message),
                    )
                    result.messages.append(normalized)

                    if is_downloadable_image(message):
                        downloaded_path = await message.download_media(file=str(chat_dir))
                        if downloaded_path:
                            result.images.append(
                                DownloadedImage(
                                    chat_name=chat_name,
                                    chat_ref=str(raw_ref),
                                    message_id=message.id,
                                    path=str(downloaded_path),
                                    mime_type=document_mime_type(message),
                                )
                            )
                return
            except FloodWaitError as exc:
                wait_seconds = int(getattr(exc, "seconds", 0))
                logger.warning(
                    "Telegram FloodWait for %s seconds while reading %s",
                    wait_seconds,
                    chat_name,
                )
                await asyncio.sleep(wait_seconds)


def _safe_path_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
    return cleaned.strip("._") or "chat"
