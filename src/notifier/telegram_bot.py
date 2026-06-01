from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096


@dataclass(frozen=True)
class SendResult:
    parts_sent: int


def split_telegram_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if limit < 1:
        raise ValueError("limit must be positive")

    normalized = text.strip() or " "
    if len(normalized) <= limit:
        return [normalized]

    parts: list[str] = []
    remaining = normalized
    while len(remaining) > limit:
        split_at = _find_split_point(remaining, limit)
        part = remaining[:split_at].rstrip()
        if not part:
            part = remaining[:limit]
            split_at = limit
        parts.append(part)
        remaining = remaining[split_at:].lstrip()

    if remaining:
        parts.append(remaining)
    return parts


class TelegramBotNotifier:
    def __init__(
        self,
        bot_token: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = 20,
    ) -> None:
        self.bot_token = bot_token
        self.client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def send_text(self, chat_id: str, text: str) -> SendResult:
        parts = split_telegram_message(text)
        for index, part in enumerate(parts, start=1):
            payload = {
                "chat_id": chat_id,
                "text": part,
                "disable_web_page_preview": True,
            }
            try:
                response = self.client.post(self._method_url("sendMessage"), json=payload)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Telegram sendMessage failed for part {index}") from exc
            body = response.json()
            if not body.get("ok"):
                raise RuntimeError(f"Telegram sendMessage failed for part {index}")
        logger.info("Sent Telegram digest in %s part(s)", len(parts))
        return SendResult(parts_sent=len(parts))

    def _method_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"


def _find_split_point(text: str, limit: int) -> int:
    window = text[:limit]
    for separator in ("\n\n", "\n", ". ", "; ", ", ", " "):
        index = window.rfind(separator)
        if index >= limit // 2:
            return index + len(separator)
    return limit
