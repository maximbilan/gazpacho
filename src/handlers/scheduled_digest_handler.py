from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from src.common.config import AppConfig, config_from_env
from src.common.secrets import SecretsManagerLoader
from src.common.storage import DigestStorage
from src.notifier.telegram_bot import TelegramBotNotifier
from src.reader.telegram_reader import TelegramReader
from src.summarizer.summarizer import Summarizer

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass(frozen=True)
class ScheduledDigestCredentials:
    telegram_api_id: int
    telegram_api_hash: str
    telethon_string_session: str
    telegram_bot_token: str
    openai_api_key: str | None = None


@dataclass(frozen=True)
class ScheduledDigestResult:
    messages_read: int
    images_downloaded: int
    digest_chars: int
    telegram_parts_sent: int
    window_start: str
    window_end: str
    stored_run_id: str | None = None


async def run_scheduled_digest(
    config: AppConfig,
    credentials: ScheduledDigestCredentials,
    *,
    download_dir: Path,
    send_digest: bool = True,
    storage: DigestStorage | None = None,
) -> ScheduledDigestResult:
    window_end = datetime.now(timezone.utc)
    window_start, used_latest_cursor = _resolve_window_start(config, storage, window_end)
    window_label = (
        f"since the previous successful digest at {window_start.isoformat()}"
        if used_latest_cursor
        else f"last {config.lookback_days} days"
    )

    async with TelegramReader(
        credentials.telegram_api_id,
        credentials.telegram_api_hash,
        credentials.telethon_string_session,
    ) as reader:
        reader_result = await reader.read_since(
            config.source_chat_ids,
            window_start=window_start,
            download_dir=download_dir,
        )

    logger.info(
        "Read %s Telegram message(s) and downloaded %s image(s)",
        len(reader_result.messages),
        len(reader_result.images),
    )

    digest = Summarizer(config, openai_api_key=credentials.openai_api_key).summarize(
        reader_result.messages,
        reader_result.images,
        window_label=window_label,
    )

    parts_sent = 0
    if send_digest:
        notifier = TelegramBotNotifier(credentials.telegram_bot_token)
        try:
            for target_chat_id in config.target_chat_ids:
                parts_sent += notifier.send_text(target_chat_id, digest).parts_sent
        finally:
            notifier.close()

    stored_run_id = None
    if storage is not None:
        stored_run = storage.store_digest_run(
            summary=digest,
            raw_messages=reader_result.messages,
            images=reader_result.images,
            lookback_days=config.lookback_days,
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
        )
        stored_run_id = stored_run.run_id
        logger.info("Stored digest run %s", stored_run_id)

    return ScheduledDigestResult(
        messages_read=len(reader_result.messages),
        images_downloaded=len(reader_result.images),
        digest_chars=len(digest),
        telegram_parts_sent=parts_sent,
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        stored_run_id=stored_run_id,
    )


def _resolve_window_start(
    config: AppConfig,
    storage: DigestStorage | None,
    window_end: datetime,
) -> tuple[datetime, bool]:
    fallback_start = window_end - timedelta(days=config.lookback_days)
    if storage is None:
        return fallback_start, False

    latest = storage.get_latest_digest_run()
    if not latest:
        return fallback_start, False

    cursor = _parse_utc_datetime(
        str(latest.get("window_end") or latest.get("generated_at") or "")
    )
    if cursor is None:
        return fallback_start, False

    cursor = cursor.astimezone(timezone.utc)
    if fallback_start < cursor < window_end:
        return cursor, True
    return fallback_start, False


def _parse_utc_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    config = config_from_env(load_local_env=False)
    secrets = SecretsManagerLoader(
        config.secrets_manager_secret_id,
        region_name=config.aws_region,
    ).secrets
    reader_secrets = secrets.require_reader()
    openai_api_key = secrets.openai_api_key
    if config.llm_provider == "openai":
        openai_api_key = secrets.require_openai().openai_api_key

    credentials = ScheduledDigestCredentials(
        telegram_api_id=reader_secrets.telegram_api_id,
        telegram_api_hash=reader_secrets.telegram_api_hash,
        telethon_string_session=reader_secrets.telethon_string_session,
        telegram_bot_token=reader_secrets.telegram_bot_token,
        openai_api_key=openai_api_key,
    )

    send_digest = not bool(event.get("dry_run"))
    store_digest = not bool(event.get("skip_storage"))
    storage = (
        DigestStorage(config.dynamodb_table_name, region_name=config.aws_region)
        if store_digest
        else None
    )
    with TemporaryDirectory(prefix="gazpacho-scheduled-") as temp_dir:
        result = asyncio.run(
            run_scheduled_digest(
                config,
                credentials,
                download_dir=Path(temp_dir),
                send_digest=send_digest,
                storage=storage,
            )
        )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "messages_read": result.messages_read,
                "images_downloaded": result.images_downloaded,
                "digest_chars": result.digest_chars,
                "telegram_parts_sent": result.telegram_parts_sent,
                "window_start": result.window_start,
                "window_end": result.window_end,
                "stored_run_id": result.stored_run_id,
            }
        ),
    }
