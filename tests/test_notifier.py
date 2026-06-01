from __future__ import annotations

from src.notifier.telegram_bot import TelegramBotNotifier, split_telegram_message


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


class FakeTelegramResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"ok": True}


class FakeTelegramClient:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def post(self, _url: str, *, json: dict):
        self.payloads.append(json)
        return FakeTelegramResponse()


def test_telegram_notifier_sends_to_requested_chat_id() -> None:
    client = FakeTelegramClient()
    notifier = TelegramBotNotifier("token", client=client)

    notifier.send_text("200911762", "hello")

    assert client.payloads == [
        {
            "chat_id": "200911762",
            "text": "hello",
            "disable_web_page_preview": True,
        }
    ]
