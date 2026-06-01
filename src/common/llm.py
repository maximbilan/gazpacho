from __future__ import annotations

import base64
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


class OpenAILLMClient:
    def __init__(self, api_key: str | None = None, client: Any | None = None) -> None:
        if client is not None:
            self.client = client
            return

        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "OpenAI SDK is not installed. Run: pip install -e \".[dev]\""
            ) from exc

        self.client = OpenAI(api_key=api_key)

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
            data_url = openai_image_data_url(image.path, image.media_type)
            if data_url is None:
                continue
            content.append(
                {
                    "type": "input_image",
                    "image_url": data_url,
                    "detail": "auto",
                }
            )

        content.append({"type": "input_text", "text": user_text})

        request: dict[str, Any] = {
            "model": model_id,
            "instructions": system_prompt,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": max_tokens,
        }
        if _openai_model_supports_temperature(model_id):
            request["temperature"] = temperature

        response = self.client.responses.create(**request)
        return _extract_openai_text(response)


def _extract_text(response: dict[str, Any]) -> str:
    message = response.get("output", {}).get("message", {})
    text_parts = [
        block["text"]
        for block in message.get("content", [])
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]
    return "\n".join(text_parts).strip()


def openai_image_data_url(path: Path, media_type: str | None = None) -> str | None:
    image_format = bedrock_image_format(path, media_type)
    if image_format is None:
        return None

    mime_type = media_type
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = f"image/{image_format}"

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_openai_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text.strip()

    if isinstance(response, dict):
        dict_output_text = response.get("output_text")
        if isinstance(dict_output_text, str):
            return dict_output_text.strip()
        output = response.get("output", [])
    else:
        output = getattr(response, "output", [])

    text_parts: list[str] = []
    for item in output or []:
        if isinstance(item, dict):
            content = item.get("content", [])
        else:
            content = getattr(item, "content", [])
        for block in content or []:
            if isinstance(block, dict):
                text = block.get("text")
            else:
                text = getattr(block, "text", None)
            if isinstance(text, str):
                text_parts.append(text)

    return "\n".join(text_parts).strip()


def _openai_model_supports_temperature(model_id: str) -> bool:
    model = model_id.lower()
    return not model.startswith(("gpt-5", "o1", "o3", "o4"))


def make_llm_client(
    provider: Literal["bedrock", "openai", "anthropic"],
    region_name: str | None = None,
    openai_api_key: str | None = None,
) -> BedrockLLMClient | OpenAILLMClient:
    if provider == "bedrock":
        return BedrockLLMClient(region_name=region_name)
    if provider == "openai":
        return OpenAILLMClient(api_key=openai_api_key)
    raise NotImplementedError("Direct Anthropic API support is not implemented yet")
