from __future__ import annotations

from pathlib import Path

from src.common.llm import (
    BedrockLLMClient,
    ImageInput,
    OpenAILLMClient,
    bedrock_image_format,
    openai_image_data_url,
)


class FakeBedrockRuntime:
    def __init__(self) -> None:
        self.request = None

    def converse(self, **kwargs):
        self.request = kwargs
        return {
            "output": {
                "message": {
                    "content": [
                        {"text": "Перевірений дайджест"},
                    ]
                }
            }
        }


class FakeOpenAIResponses:
    def __init__(self) -> None:
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return {"output_text": "Український дайджест"}


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeOpenAIResponses()


def test_bedrock_image_format_from_mime_and_suffix() -> None:
    assert bedrock_image_format(Path("notice.jpg"), None) == "jpeg"
    assert bedrock_image_format(Path("notice.bin"), "image/png") == "png"
    assert bedrock_image_format(Path("notice.txt"), "text/plain") is None


def test_bedrock_client_builds_converse_request_with_image(tmp_path: Path) -> None:
    image_path = tmp_path / "notice.jpg"
    image_path.write_bytes(b"fake-image")
    fake_client = FakeBedrockRuntime()
    llm = BedrockLLMClient(client=fake_client)

    result = llm.complete(
        model_id="eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        system_prompt="system",
        user_text="summarize",
        images=[ImageInput(path=image_path, media_type="image/jpeg")],
    )

    assert result == "Перевірений дайджест"
    assert fake_client.request["modelId"] == "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert fake_client.request["system"] == [{"text": "system"}]
    content = fake_client.request["messages"][0]["content"]
    assert content[0]["image"]["format"] == "jpeg"
    assert content[0]["image"]["source"]["bytes"] == b"fake-image"
    assert content[1]["text"] == "summarize"


def test_openai_image_data_url_from_image(tmp_path: Path) -> None:
    image_path = tmp_path / "notice.png"
    image_path.write_bytes(b"fake-image")

    assert openai_image_data_url(image_path, "image/png") == (
        "data:image/png;base64,ZmFrZS1pbWFnZQ=="
    )


def test_openai_client_builds_responses_request_with_image(tmp_path: Path) -> None:
    image_path = tmp_path / "notice.jpg"
    image_path.write_bytes(b"fake-image")
    fake_client = FakeOpenAIClient()
    llm = OpenAILLMClient(client=fake_client)

    result = llm.complete(
        model_id="gpt-4.1-mini",
        system_prompt="system",
        user_text="summarize",
        images=[ImageInput(path=image_path, media_type="image/jpeg")],
    )

    assert result == "Український дайджест"
    request = fake_client.responses.request
    assert request["model"] == "gpt-4.1-mini"
    assert request["instructions"] == "system"
    content = request["input"][0]["content"]
    assert content[0]["type"] == "input_image"
    assert content[0]["image_url"] == "data:image/jpeg;base64,ZmFrZS1pbWFnZQ=="
    assert content[1] == {"type": "input_text", "text": "summarize"}
