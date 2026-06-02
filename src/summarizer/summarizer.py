from __future__ import annotations

from pathlib import Path

from src.common.config import AppConfig
from src.common.llm import ImageInput, make_llm_client
from src.reader.models import DownloadedImage, NormalizedMessage
from src.summarizer.prompts import SYSTEM_PROMPT, build_summary_prompt


EMPTY_WEEK_DIGEST = (
    "За цей період у шкільних чатах не знайдено "
    "важливих оновлень."
)


class Summarizer:
    def __init__(self, config: AppConfig, openai_api_key: str | None = None) -> None:
        self.config = config
        self.llm = make_llm_client(
            config.llm_provider,
            region_name=config.aws_region,
            openai_api_key=openai_api_key,
        )

    def summarize(
        self,
        messages: list[NormalizedMessage],
        images: list[DownloadedImage],
        *,
        window_label: str | None = None,
    ) -> str:
        if not messages and not images:
            return EMPTY_WEEK_DIGEST

        window_label = window_label or f"last {self.config.lookback_days} days"
        prompt = build_summary_prompt(
            messages,
            source_lang=self.config.source_lang,
            output_lang=self.config.output_lang,
            window_label=window_label,
        )
        image_inputs = [
            ImageInput(path=Path(image.path), media_type=image.mime_type)
            for image in images
            if Path(image.path).exists()
        ]

        return self.llm.complete(
            model_id=self.config.llm_model_summary,
            system_prompt=SYSTEM_PROMPT,
            user_text=prompt,
            images=image_inputs,
            max_tokens=4096,
            temperature=0.2,
        )
