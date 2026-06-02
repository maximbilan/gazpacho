from __future__ import annotations

from src.qa_bot.prompts import build_qa_prompt


def test_build_qa_prompt_includes_digest_raw_messages_and_history() -> None:
    prompt = build_qa_prompt(
        question="Що треба принести завтра?",
        digest_runs=[
            {
                "generated_at": "2026-05-30T18:00:00+00:00",
                "summary": "Стара інформація про форму.",
            },
            {
                "generated_at": "2026-06-01T18:00:00+00:00",
                "summary": "Принести дозвіл.",
            },
        ],
        raw_message_runs=[
            {
                "raw_messages": [
                    {
                        "chat_name": "School",
                        "date_iso": "2026-06-01T08:00:00+00:00",
                        "sender": "Teacher",
                        "text": "Traer autorización mañana.",
                    }
                ],
            },
        ],
        recent_conversation=[{"role": "user", "text": "Коли екскурсія?"}],
    )

    assert "Що треба принести завтра?" in prompt
    assert "Стара інформація про форму." in prompt
    assert "Принести дозвіл." in prompt
    assert "Traer autorización mañana." in prompt
    assert "Коли екскурсія?" in prompt
