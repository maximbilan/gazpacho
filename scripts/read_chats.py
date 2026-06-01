#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_dotenv(path: str | Path) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_source_chat_ids(value: str) -> list[str]:
    stripped = value.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        if not isinstance(parsed, list):
            raise SystemExit("SOURCE_CHAT_IDS JSON must be a list")
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in stripped.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read recent Telegram chat messages through the Telethon user session."
    )
    parser.add_argument("--env-file", default=".env", help="Path to a local .env file")
    parser.add_argument("--api-id", type=int, default=None, help="Telegram API ID")
    parser.add_argument("--api-hash", default=None, help="Telegram API hash")
    parser.add_argument("--string-session", default=None, help="Telethon StringSession")
    parser.add_argument(
        "--source-chat-ids",
        default=None,
        help="Comma-separated chat refs; defaults to SOURCE_CHAT_IDS",
    )
    parser.add_argument("--lookback-days", type=int, default=None, help="Days to read")
    parser.add_argument(
        "--download-dir",
        default=None,
        help="Directory for downloaded images; defaults to a temp directory",
    )
    return parser.parse_args()


def env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def require_int(value: int | str | None, name: str) -> int:
    if isinstance(value, int):
        return value
    if value is None:
        raise SystemExit(f"{name} is required")
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer") from exc


async def async_main() -> int:
    args = parse_args()
    load_dotenv(args.env_file)

    api_id = require_int(args.api_id or env_value("TELEGRAM_API_ID", "telegram_api_id"), "api_id")
    api_hash = args.api_hash or env_value("TELEGRAM_API_HASH", "telegram_api_hash")
    string_session = args.string_session or env_value(
        "TELETHON_STRING_SESSION", "telethon_string_session"
    )
    source_chat_ids = parse_source_chat_ids(
        args.source_chat_ids or env_value("SOURCE_CHAT_IDS") or ""
    )
    lookback_days = require_int(
        args.lookback_days or env_value("LOOKBACK_DAYS") or 7,
        "lookback_days",
    )

    if not api_hash:
        raise SystemExit("api_hash is required")
    if not string_session:
        raise SystemExit("string_session is required")
    if not source_chat_ids:
        raise SystemExit("SOURCE_CHAT_IDS is required")

    try:
        from src.reader.telegram_reader import TelegramReader
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Reader dependencies are not installed. Run: pip install -e \".[dev]\""
        ) from exc

    download_dir = Path(args.download_dir or tempfile.mkdtemp(prefix="gazpacho-reader-"))
    async with TelegramReader(api_id, api_hash, string_session) as reader:
        result = await reader.read_recent(
            source_chat_ids,
            lookback_days=lookback_days,
            download_dir=download_dir,
        )

    for message in result.messages:
        print(message.model_dump_json())

    print(
        json.dumps(
            {
                "message_count": len(result.messages),
                "image_count": len(result.images),
                "download_dir": str(download_dir),
            },
            ensure_ascii=False,
        )
    )

    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
