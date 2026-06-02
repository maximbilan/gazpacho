from __future__ import annotations

from src.common.config import AppConfig


def test_app_config_parses_multiple_target_chat_ids() -> None:
    config = AppConfig.model_validate(
        {
            "source_chat_ids": "@school",
            "target_chat_ids": "111111111,222222222",
        }
    )

    assert config.target_chat_ids == ["111111111", "222222222"]
