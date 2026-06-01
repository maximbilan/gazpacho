from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import boto3


SUPPORTED_IMAGE_FORMATS = {"jpeg", "png", "gif", "webp"}


@dataclass(frozen=True)
class ImageInput:
    path: Path
    media_type: str | None = None


def bedrock_image_format(path: Path, media_type: str | None = None) -> str | None:
    if media_type:
        _, _, subtype = media_type.partition("/")
        subtype = subtype.lower()
        if subtype == "jpg":
            subtype = "jpeg"
        if subtype in SUPPORTED_IMAGE_FORMATS:
            return subtype

    suffix = path.suffix.lower().lstrip(".")
    if suffix == "jpg":
        suffix = "jpeg"
    return suffix if suffix in SUPPORTED_IMAGE_FORMATS else None


class BedrockLLMClient:
    def __init__(self, region_name: str | None = None, client: Any | None = None) -> None:
        self.client = client or boto3.client("bedrock-runtime", region_name=region_name)

    def complete(
        self,
        *,
        model_id: str,
        system_prompt: str,
        user_text: str,
        images: list[ImageInput] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> str:
        content: list[dict[str, Any]] = []

        for image in images or []:
            image_format = bedrock_image_format(image.path, image.media_type)
            if image_format is None:
                continue
            content.append(
                {
                    "image": {
                        "format": image_format,
                        "source": {"bytes": image.path.read_bytes()},
                    }
                }
            )

        content.append({"text": user_text})

        response = self.client.converse(
            modelId=model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        )
        return _extract_text(response)


def _extract_text(response: dict[str, Any]) -> str:
    message = response.get("output", {}).get("message", {})
    text_parts = [
        block["text"]
        for block in message.get("content", [])
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]
    return "\n".join(text_parts).strip()


def make_llm_client(
    provider: Literal["bedrock", "anthropic"], region_name: str | None = None
) -> BedrockLLMClient:
    if provider != "bedrock":
        raise NotImplementedError("Direct Anthropic API support is not implemented yet")
    return BedrockLLMClient(region_name=region_name)
