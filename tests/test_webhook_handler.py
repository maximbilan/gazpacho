from __future__ import annotations

import json
from types import SimpleNamespace

from src.common.config import AppConfig
from src.handlers import webhook_handler


def _set_required_env(monkeypatch, *, target_chat_ids: str = "111111111") -> None:
    monkeypatch.setenv("SOURCE_CHAT_IDS", "@school")
    monkeypatch.setenv("TARGET_CHAT_IDS", target_chat_ids)
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("SCHEDULED_DIGEST_FUNCTION_NAME", "scheduled-function")
    monkeypatch.setenv("SECRETS_MANAGER_SECRET_ID", "test-secret")
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", "test-table")


def _telegram_event(
    text: str,
    *,
    chat_id: str = "111111111",
    secret: str = "telegram-secret",
) -> dict:
    return {
        "headers": {webhook_handler.TELEGRAM_SECRET_HEADER: secret},
        "body": json.dumps(
            {
                "message": {
                    "chat": {"id": int(chat_id)},
                    "text": text,
                }
            }
        ),
    }


def _install_common_fakes(monkeypatch):
    _set_required_env(monkeypatch)
    sent_messages: list[tuple[str, str]] = []
    notifiers: list[FakeNotifier] = []

    class FakeSecrets:
        openai_api_key = "openai-key"

        def require_webhook(self):
            return SimpleNamespace(
                telegram_bot_token="bot-token",
                telegram_webhook_secret="telegram-secret",
            )

    class FakeSecretsLoader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.secrets = FakeSecrets()

    class FakeNotifier:
        def __init__(self, bot_token: str) -> None:
            self.bot_token = bot_token
            self.closed = False
            notifiers.append(self)

        def send_text(self, chat_id: str, text: str):
            sent_messages.append((chat_id, text))
            return SimpleNamespace(parts_sent=1)

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(webhook_handler, "SecretsManagerLoader", FakeSecretsLoader)
    monkeypatch.setattr(webhook_handler, "TelegramBotNotifier", FakeNotifier)
    return sent_messages, notifiers


def test_handler_rejects_invalid_telegram_secret(monkeypatch) -> None:
    sent_messages, notifiers = _install_common_fakes(monkeypatch)

    response = webhook_handler.handler(_telegram_event("/start", secret="wrong"), None)

    assert response["statusCode"] == 401
    assert json.loads(response["body"]) == {"ok": False}
    assert sent_messages == []
    assert notifiers == []


def test_handler_start_replies_with_chat_id(monkeypatch) -> None:
    sent_messages, notifiers = _install_common_fakes(monkeypatch)

    response = webhook_handler.handler(_telegram_event("/start"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"ok": True}
    assert len(sent_messages) == 1
    assert sent_messages[0][0] == "111111111"
    assert "chat_id: 111111111" in sent_messages[0][1]
    assert notifiers[0].bot_token == "bot-token"
    assert notifiers[0].closed is True


def test_handler_summary_sends_latest_digest(monkeypatch) -> None:
    sent_messages, _notifiers = _install_common_fakes(monkeypatch)

    class FakeStorage:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_latest_digest_run(self):
            return {"summary": "Останній дайджест"}

    monkeypatch.setattr(webhook_handler, "DigestStorage", FakeStorage)

    response = webhook_handler.handler(_telegram_event("/summary"), None)

    assert response["statusCode"] == 200
    assert sent_messages == [("111111111", "Останній дайджест")]


def test_handler_summary_handles_missing_digest(monkeypatch) -> None:
    sent_messages, _notifiers = _install_common_fakes(monkeypatch)

    class FakeStorage:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_latest_digest_run(self):
            return None

    monkeypatch.setattr(webhook_handler, "DigestStorage", FakeStorage)

    response = webhook_handler.handler(_telegram_event("/summary"), None)

    assert response["statusCode"] == 200
    assert sent_messages == [
        ("111111111", "Поки немає збереженого дайджесту. Запусти /refresh.")
    ]


def test_handler_ignores_non_target_question(monkeypatch) -> None:
    sent_messages, _notifiers = _install_common_fakes(monkeypatch)

    def fail_answer(*_args, **_kwargs):
        raise AssertionError("_answer_question should not be called for non-target chats")

    monkeypatch.setattr(webhook_handler, "_answer_question", fail_answer)

    response = webhook_handler.handler(
        _telegram_event("Що завтра?", chat_id="999999999"),
        None,
    )

    assert response["statusCode"] == 200
    assert sent_messages == [
        (
            "999999999",
            "Цей бот налаштований для іншого chat_id.\nchat_id: 999999999",
        )
    ]


def test_handler_refresh_invokes_scheduled_digest(monkeypatch) -> None:
    sent_messages, _notifiers = _install_common_fakes(monkeypatch)
    invocations: list[dict] = []

    class FakeLambdaClient:
        def invoke(self, **kwargs):
            invocations.append(kwargs)
            return {"StatusCode": 202}

    def fake_boto3_client(service_name: str, *, region_name: str | None = None):
        assert service_name == "lambda"
        assert region_name == "eu-west-1"
        return FakeLambdaClient()

    monkeypatch.setattr(webhook_handler.boto3, "client", fake_boto3_client)

    response = webhook_handler.handler(_telegram_event("/refresh"), None)

    assert response["statusCode"] == 200
    assert invocations == [
        {
            "FunctionName": "scheduled-function",
            "InvocationType": "Event",
            "Payload": json.dumps({"source": "telegram_refresh"}).encode("utf-8"),
        }
    ]
    assert sent_messages == [
        ("111111111", "Запустив оновлення. Коли дайджест буде готовий, я надішлю його сюди.")
    ]


def test_handler_answer_question_replies_to_target_chat(monkeypatch) -> None:
    sent_messages, _notifiers = _install_common_fakes(monkeypatch)
    calls: list[tuple[str, str]] = []

    def fake_answer(config, openai_api_key, chat_id, question):
        assert config.target_chat_ids == ["111111111"]
        assert openai_api_key == "openai-key"
        calls.append((chat_id, question))
        return "Відповідь українською"

    monkeypatch.setattr(webhook_handler, "_answer_question", fake_answer)

    response = webhook_handler.handler(_telegram_event("Що завтра?"), None)

    assert response["statusCode"] == 200
    assert calls == [("111111111", "Що завтра?")]
    assert sent_messages == [("111111111", "Відповідь українською")]


def test_answer_question_uses_context_and_appends_conversation(monkeypatch) -> None:
    storage_instances: list[FakeStorage] = []

    class FakeStorage:
        def __init__(self, table_name: str, *, region_name: str | None = None) -> None:
            self.table_name = table_name
            self.region_name = region_name
            self.appended: dict | None = None
            storage_instances.append(self)

        def get_latest_digest_run(self):
            return {
                "summary": "Завтра екскурсія.",
                "raw_messages": [{"text": "Excursión mañana."}],
            }

        def get_recent_conversation(self, chat_id: str):
            assert chat_id == "111111111"
            return [{"role": "user", "text": "Попереднє питання"}]

        def append_conversation_turn(self, **kwargs):
            self.appended = kwargs
            return []

    class FakeLLM:
        def __init__(self) -> None:
            self.request: dict | None = None

        def complete(self, **kwargs):
            self.request = kwargs
            return "Так, завтра екскурсія."

    fake_llm = FakeLLM()

    def fake_make_llm_client(provider, *, region_name=None, openai_api_key=None):
        assert provider == "openai"
        assert region_name == "eu-west-1"
        assert openai_api_key == "openai-key"
        return fake_llm

    monkeypatch.setattr(webhook_handler, "DigestStorage", FakeStorage)
    monkeypatch.setattr(webhook_handler, "make_llm_client", fake_make_llm_client)

    config = AppConfig.model_validate(
        {
            "source_chat_ids": "@school",
            "target_chat_ids": "111111111",
            "aws_region": "eu-west-1",
            "dynamodb_table_name": "test-table",
            "llm_model_qa": "gpt-5-mini",
        }
    )

    answer = webhook_handler._answer_question(
        config,
        "openai-key",
        "111111111",
        "Чи завтра екскурсія?",
    )

    assert answer == "Так, завтра екскурсія."
    assert storage_instances[0].table_name == "test-table"
    assert storage_instances[0].region_name == "eu-west-1"
    assert storage_instances[0].appended == {
        "chat_id": "111111111",
        "question": "Чи завтра екскурсія?",
        "answer": "Так, завтра екскурсія.",
    }
    assert fake_llm.request is not None
    assert fake_llm.request["model_id"] == "gpt-5-mini"
    assert "Чи завтра екскурсія?" in fake_llm.request["user_text"]
    assert "Excursión mañana." in fake_llm.request["user_text"]
