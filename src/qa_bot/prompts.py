from __future__ import annotations

from typing import Any


QA_SYSTEM_PROMPT = """\
Ти персональний помічник українського батька/матері для шкільних повідомлень в Іспанії.
Відповідай українською, коротко і практично.
Використовуй тільки наданий контекст: усі збережені дайджести, останні сирі повідомлення та коротку історію розмови.
Не вигадуй дат, сум, вимог або назв. Якщо відповіді немає в контексті, скажи, що в збережених
повідомленнях цього немає, і запропонуй запустити /refresh.
Якщо є дата або дедлайн, називай її явно.
"""


def build_qa_prompt(
    *,
    question: str,
    digest_runs: list[dict[str, Any]],
    raw_message_runs: list[dict[str, Any]] | None = None,
    recent_conversation: list[dict[str, str]],
) -> str:
    digest_text = "Немає збережених дайджестів."
    raw_messages_text = "Немає збережених останніх сирих повідомлень."

    if digest_runs:
        digest_lines = []

        for run_index, digest in enumerate(digest_runs, start=1):
            generated_at = digest.get("generated_at", "невідомо")
            window_start = digest.get("window_start") or ""
            window_end = digest.get("window_end") or ""
            window = (
                f"Вікно: {window_start} - {window_end}"
                if window_start or window_end
                else "Вікно: невідомо"
            )
            digest_lines.append(
                "\n".join(
                    [
                        f"{run_index}. Згенеровано: {generated_at}",
                        window,
                        str(digest.get("summary", "")).strip(),
                    ]
                ).strip()
            )

        digest_text = "\n\n".join(line for line in digest_lines if line) or digest_text

    if raw_message_runs:
        raw_lines = []
        raw_index = 1
        for digest in raw_message_runs:
            raw_messages = digest.get("raw_messages", [])
            if isinstance(raw_messages, list):
                for message in raw_messages:
                    if not isinstance(message, dict):
                        continue
                    raw_lines.append(
                        "\n".join(
                            [
                                f"{raw_index}. Чат: {message.get('chat_name', '')}",
                                f"Дата: {message.get('date_iso', '')}",
                                f"Відправник: {message.get('sender', '')}",
                                f"Оригінал: {message.get('text', '') or '[без тексту]'}",
                            ]
                        )
                    )
                    raw_index += 1

        raw_messages_text = "\n\n".join(raw_lines) or raw_messages_text

    conversation_text = "Немає попередньої розмови."
    if recent_conversation:
        conversation_text = "\n".join(
            f"{item['role']}: {item['text']}" for item in recent_conversation[-10:]
        )

    return f"""\
Питання користувача:
{question}

Усі збережені дайджести:
{digest_text}

Останні збережені сирі повідомлення з Telegram:
{raw_messages_text}

Коротка історія розмови:
{conversation_text}

Дай відповідь українською. Якщо потрібно, вкажи конкретні дії для батька/матері.
"""
