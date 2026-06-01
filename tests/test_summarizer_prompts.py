from __future__ import annotations

from src.reader.models import NormalizedMessage
from src.summarizer.prompts import build_summary_prompt
from src.summarizer.summarizer import EMPTY_WEEK_DIGEST


def test_summary_prompt_includes_ukrainian_digest_sections() -> None:
    prompt = build_summary_prompt(
        [
            NormalizedMessage(
                chat_name="Clase",
                chat_ref="@clase",
                message_id=42,
                sender="School",
                date_iso="2026-06-01T08:00:00+00:00",
                text="Traer autorización firmada antes del viernes.",
            )
        ],
        source_lang="es",
        output_lang="uk",
        lookback_days=7,
    )

    assert "❗ Потребує дії" in prompt
    assert "📅 Дати та події" in prompt
    assert "ℹ️ Інформація" in prompt
    assert "Traer autorización firmada" in prompt


def test_empty_week_digest_is_ukrainian() -> None:
    assert "цього тижня" in EMPTY_WEEK_DIGEST.lower()
