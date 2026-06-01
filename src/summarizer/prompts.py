from __future__ import annotations

from src.reader.models import NormalizedMessage


SYSTEM_PROMPT = """\
You are Gazpacho, a careful assistant for a Ukrainian parent in Spain.
You read Spanish school Telegram updates, including images of paper notices,
and produce a faithful Ukrainian digest.

Rules:
- Answer only in Ukrainian.
- Make dates explicit and absolute when the source provides enough information.
- Never invent dates, amounts, deadlines, or requirements.
- If an image is unreadable or ambiguous, say that explicitly.
- Include a short Spanish reference for each item so the parent can find it.
- Omit empty sections.
"""


def build_summary_prompt(
    messages: list[NormalizedMessage],
    *,
    source_lang: str,
    output_lang: str,
    lookback_days: int,
) -> str:
    if not messages:
        return (
            f"No Telegram text messages were found in the last {lookback_days} days. "
            "If images are attached, inspect them. Otherwise write a short Ukrainian "
            "note that there was nothing important this week."
        )

    lines = [
        f"Source language: {source_lang}",
        f"Output language: {output_lang}",
        f"Window: last {lookback_days} days",
        "",
        "Produce a Ukrainian digest with these sections, omitting empty sections:",
        "❗ Потребує дії",
        "📅 Дати та події",
        "ℹ️ Інформація",
        "",
        "For each item include: what, by when if known, what the parent must do, "
        "urgency, source date, and a one-line Spanish reference.",
        "",
        "Telegram messages:",
    ]

    for message in messages:
        text = message.text.strip() or "[no text]"
        media = f", media={message.media_kind}" if message.has_media else ""
        lines.append(
            "\n".join(
                [
                    f"- chat={message.chat_name}",
                    f"  id={message.message_id}",
                    f"  date={message.date_iso}",
                    f"  sender={message.sender or 'unknown'}{media}",
                    f"  spanish={text}",
                ]
            )
        )

    return "\n".join(lines)
