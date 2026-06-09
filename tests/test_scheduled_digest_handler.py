from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from src.common.config import AppConfig
from src.handlers import scheduled_digest_handler
from src.handlers.scheduled_digest_handler import (
    ScheduledDigestCredentials,
    run_scheduled_digest,
)
from src.reader.models import ReaderResult


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 6, 2, 16, 0, tzinfo=timezone.utc)
        return value if tz is None else value.astimezone(tz)


def test_run_scheduled_digest_reads_since_latest_stored_digest(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    class FakeReader:
        def __init__(self, *_args) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def read_since(self, chat_refs, *, window_start, download_dir):
            calls["chat_refs"] = chat_refs
            calls["window_start"] = window_start
            calls["download_dir"] = download_dir
            return ReaderResult()

    class FakeSummarizer:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def summarize(self, messages, images, *, window_label=None):
            calls["window_label"] = window_label
            return "Дайджест"

    class FakeStorage:
        def get_latest_digest_run(self):
            return {
                "generated_at": "2026-06-01T16:05:00+00:00",
                "window_end": "2026-06-01T16:00:00+00:00",
            }

        def store_digest_run(self, **kwargs):
            calls["stored"] = kwargs
            return type("Stored", (), {"run_id": "digest#test"})()

    monkeypatch.setattr(scheduled_digest_handler, "datetime", FixedDateTime)
    monkeypatch.setattr(scheduled_digest_handler, "TelegramReader", FakeReader)
    monkeypatch.setattr(scheduled_digest_handler, "Summarizer", FakeSummarizer)

    config = AppConfig.model_validate(
        {
            "source_chat_ids": "@school",
            "target_chat_ids": "111111111",
            "lookback_days": 7,
        }
    )
    credentials = ScheduledDigestCredentials(
        telegram_api_id=1,
        telegram_api_hash="hash",
        telethon_string_session="session",
        telegram_bot_token="bot",
        openai_api_key="openai",
    )

    result = asyncio.run(
        run_scheduled_digest(
            config,
            credentials,
            download_dir=Path(tmp_path),
            send_digest=False,
            storage=FakeStorage(),
        )
    )

    expected_start = datetime(2026, 6, 1, 16, 0, tzinfo=timezone.utc)
    assert calls["chat_refs"] == ["@school"]
    assert calls["window_start"] == expected_start
    assert calls["window_label"] == (
        "since the previous successful digest at 2026-06-01T16:00:00+00:00"
    )
    assert calls["stored"]["window_start"] == "2026-06-01T16:00:00+00:00"
    assert calls["stored"]["window_end"] == "2026-06-02T16:00:00+00:00"
    assert result.window_start == "2026-06-01T16:00:00+00:00"
    assert result.window_end == "2026-06-02T16:00:00+00:00"


def test_run_scheduled_digest_skips_send_when_nothing_to_summarize(
    monkeypatch, tmp_path
) -> None:
    sent: list[tuple[str, str]] = []
    stored: dict[str, object] = {}

    class FakeReader:
        def __init__(self, *_args) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def read_since(self, _chat_refs, *, window_start, download_dir):
            return ReaderResult()

    class FakeSummarizer:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def summarize(self, messages, images, *, window_label=None):
            return None

    class FakeNotifier:
        def __init__(self, *_args) -> None:
            raise AssertionError("notifier should not be constructed when digest is empty")

    class FakeStorage:
        def get_latest_digest_run(self):
            return None

        def store_digest_run(self, **kwargs):
            stored.update(kwargs)
            return type("Stored", (), {"run_id": "digest#empty"})()

    monkeypatch.setattr(scheduled_digest_handler, "datetime", FixedDateTime)
    monkeypatch.setattr(scheduled_digest_handler, "TelegramReader", FakeReader)
    monkeypatch.setattr(scheduled_digest_handler, "Summarizer", FakeSummarizer)
    monkeypatch.setattr(scheduled_digest_handler, "TelegramBotNotifier", FakeNotifier)

    config = AppConfig.model_validate(
        {
            "source_chat_ids": "@school",
            "target_chat_ids": "111111111",
            "lookback_days": 7,
        }
    )
    credentials = ScheduledDigestCredentials(
        telegram_api_id=1,
        telegram_api_hash="hash",
        telethon_string_session="session",
        telegram_bot_token="bot",
        openai_api_key="openai",
    )

    result = asyncio.run(
        run_scheduled_digest(
            config,
            credentials,
            download_dir=Path(tmp_path),
            send_digest=True,
            storage=FakeStorage(),
        )
    )

    assert sent == []
    assert result.telegram_parts_sent == 0
    assert result.digest_chars == 0
    assert stored["summary"] == ""
    assert result.stored_run_id == "digest#empty"


def test_resolve_window_start_caps_stale_latest_digest() -> None:
    class FakeStorage:
        def get_latest_digest_run(self):
            return {"generated_at": "2026-05-01T16:00:00+00:00"}

    config = AppConfig.model_validate(
        {
            "source_chat_ids": "@school",
            "target_chat_ids": "111111111",
            "lookback_days": 7,
        }
    )
    window_end = datetime(2026, 6, 2, 16, 0, tzinfo=timezone.utc)

    window_start, used_latest_cursor = scheduled_digest_handler._resolve_window_start(
        config,
        FakeStorage(),
        window_end,
    )

    assert window_start == datetime(2026, 5, 26, 16, 0, tzinfo=timezone.utc)
    assert used_latest_cursor is False
