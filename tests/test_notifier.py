from __future__ import annotations

from src.notifier.telegram_bot import split_telegram_message


def test_split_telegram_message_keeps_short_text_whole() -> None:
    assert split_telegram_message("hello", limit=100) == ["hello"]


def test_split_telegram_message_prefers_line_boundaries() -> None:
    text = "first line\nsecond line\nthird line"
    assert split_telegram_message(text, limit=24) == [
        "first line\nsecond line",
        "third line",
    ]


def test_split_telegram_message_falls_back_to_hard_limit() -> None:
    assert split_telegram_message("x" * 25, limit=10) == ["x" * 10, "x" * 10, "x" * 5]
