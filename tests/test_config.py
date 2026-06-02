from __future__ import annotations

from src.common.config import AppConfig, config_from_env


def test_app_config_parses_multiple_target_chat_ids() -> None:
    config = AppConfig.model_validate(
        {
            "source_chat_ids": "@school",
            "target_chat_ids": "111111111,222222222",
        }
    )

    assert config.target_chat_ids == ["111111111", "222222222"]


def test_config_accepts_legacy_weekly_function_env(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_CHAT_IDS", "@school")
    monkeypatch.setenv("TARGET_CHAT_IDS", "111111111")
    monkeypatch.delenv("SCHEDULED_DIGEST_FUNCTION_NAME", raising=False)
    monkeypatch.setenv("WEEKLY_DIGEST_FUNCTION_NAME", "legacy-function")

    config = config_from_env(load_local_env=False)

    assert config.scheduled_digest_function_name == "legacy-function"
