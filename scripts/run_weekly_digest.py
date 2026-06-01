#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the weekly digest flow locally.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and summarize, but do not send the digest to Telegram",
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help="Directory for downloaded Telegram images; defaults to a temp directory",
    )
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> int:
    args = parse_args()

    from src.common.config import config_from_env
    from src.handlers.weekly_digest_handler import (
        WeeklyDigestCredentials,
        run_weekly_digest,
    )

    config = config_from_env()
    credentials = WeeklyDigestCredentials(
        telegram_api_id=int(required_env("TELEGRAM_API_ID")),
        telegram_api_hash=required_env("TELEGRAM_API_HASH"),
        telethon_string_session=required_env("TELETHON_STRING_SESSION"),
        telegram_bot_token=required_env("TELEGRAM_BOT_TOKEN"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )

    download_dir = Path(args.download_dir or tempfile.mkdtemp(prefix="gazpacho-weekly-"))
    result = asyncio.run(
        run_weekly_digest(
            config,
            credentials,
            download_dir=download_dir,
            send_digest=not args.dry_run,
        )
    )
    print(
        "weekly_digest_ok "
        f"messages={result.messages_read} "
        f"images={result.images_downloaded} "
        f"digest_chars={result.digest_chars} "
        f"telegram_parts={result.telegram_parts_sent} "
        f"download_dir={download_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
