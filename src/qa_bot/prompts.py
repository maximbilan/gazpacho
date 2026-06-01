from __future__ import annotations

from typing import Any


QA_SYSTEM_PROMPT = """\
Ти персональний помічник українського батька/матері для шкільних повідомлень в Іспанії.
Відповідай українською, коротко і практично.
Використовуй тільки наданий контекст: останній дайджест, сирі повідомлення та коротку історію розмови.
Не вигадуй дат, сум, вимог або назв. Якщо відповіді немає в контексті, скажи, що в останніх збережених
повідомленнях цього немає, і запропонуй запустити /refresh.
Якщо є дата або дедлайн, називай її явно.
"""


def build_qa_prompt(
    *,
    question: str,
    latest_digest: dict[str, Any] | None,
    recent_conversation: list[dict[str, str]],
) -> str:
    digest_text = "Немає збереженого дайджесту."
    raw_messages_text = "Немає збережених сирих повідомлень."

    if latest_digest:
        generated_at = latest_digest.get("generated_at", "невідомо")
        digest_text = f"Згенеровано: {generated_at}\n\n{latest_digest.get('summary', '')}".strip()
        raw_messages = latest_digest.get("raw_messages", [])
        if isinstance(raw_messages, list) and raw_messages:
            lines = []
            for index, message in enumerate(raw_messages[:80], start=1):
                if not isinstance(message, dict):
                    continue
                lines.append(
                    "\n".join(
                        [
                            f"{index}. Чат: {message.get('chat_name', '')}",
                            f"Дата: {message.get('date_iso', '')}",
                            f"Відправник: {message.get('sender', '')}",
                            f"Оригінал: {message.get('text', '') or '[без тексту]'}",
                        ]
                    )
                )
            raw_messages_text = "\n\n".join(lines) or raw_messages_text

    conversation_text = "Немає попередньої розмови."
    if recent_conversation:
        conversation_text = "\n".join(
            f"{item['role']}: {item['text']}" for item in recent_conversation[-10:]
        )

    return f"""\
Питання користувача:
{question}

Останній збережений дайджест:
{digest_text}

Сирі повідомлення з Telegram:
{raw_messages_text}

Коротка історія розмови:
{conversation_text}

Дай відповідь українською. Якщо потрібно, вкажи конкретні дії для батька/матері.
"""
