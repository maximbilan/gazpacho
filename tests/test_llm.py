from __future__ import annotations

from pathlib import Path

from src.common.llm import BedrockLLMClient, ImageInput, bedrock_image_format


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
        model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
        system_prompt="system",
        user_text="summarize",
        images=[ImageInput(path=image_path, media_type="image/jpeg")],
    )

    assert result == "Перевірений дайджест"
    assert fake_client.request["modelId"] == "anthropic.claude-haiku-4-5-20251001-v1:0"
    assert fake_client.request["system"] == [{"text": "system"}]
    content = fake_client.request["messages"][0]["content"]
    assert content[0]["image"]["format"] == "jpeg"
    assert content[0]["image"]["source"]["bytes"] == b"fake-image"
    assert content[1]["text"] == "summarize"
