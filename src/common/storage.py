from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from src.reader.models import DownloadedImage, NormalizedMessage


RUN_PK = "RUN"
LATEST_SK = "LATEST"
CONVERSATION_PK_PREFIX = "CONVERSATION#"
CONVERSATION_SK = "RECENT"


@dataclass(frozen=True)
class StoredDigestRun:
    run_id: str
    generated_at: str


class DigestStorage:
    def __init__(self, table_name: str, region_name: str | None = None, table: Any | None = None) -> None:
        if table is not None:
            self.table = table
            return

        kwargs = {"region_name": region_name} if region_name else {}
        dynamodb = boto3.resource("dynamodb", **kwargs)
        self.table = dynamodb.Table(table_name)

    def store_digest_run(
        self,
        *,
        summary: str,
        raw_messages: list[NormalizedMessage],
        images: list[DownloadedImage],
        lookback_days: int,
        window_start: str | None = None,
        window_end: str | None = None,
    ) -> StoredDigestRun:
        generated_at = datetime.now(timezone.utc).isoformat()
        run_id = f"digest#{generated_at}"
        message_items = [message.model_dump(mode="json") for message in raw_messages]
        image_items = [
            {
                "chat_name": image.chat_name,
                "chat_ref": image.chat_ref,
                "message_id": image.message_id,
                "mime_type": image.mime_type,
            }
            for image in images
        ]

        run_item = {
            "pk": RUN_PK,
            "sk": run_id,
            "entity_type": "digest_run",
            "run_id": run_id,
            "generated_at": generated_at,
            "lookback_days": lookback_days,
            "window_start": window_start,
            "window_end": window_end,
            "summary": summary,
            "raw_messages": message_items,
            "images": image_items,
            "message_count": len(message_items),
            "image_count": len(image_items),
        }
        latest_item = {
            "pk": RUN_PK,
            "sk": LATEST_SK,
            "entity_type": "latest_digest_run",
            "run_id": run_id,
            "generated_at": generated_at,
        }

        self.table.put_item(Item=run_item)
        self.table.put_item(Item=latest_item)
        return StoredDigestRun(run_id=run_id, generated_at=generated_at)

    def get_latest_digest_run(self) -> dict[str, Any] | None:
        latest_response = self.table.get_item(Key={"pk": RUN_PK, "sk": LATEST_SK})
        latest = latest_response.get("Item")
        if not latest:
            return None

        run_id = latest.get("run_id")
        if not run_id:
            return None

        run_response = self.table.get_item(Key={"pk": RUN_PK, "sk": run_id})
        return run_response.get("Item")

    def get_digest_runs(self, *, include_raw_messages: bool = True) -> list[dict[str, Any]]:
        attribute_names = {
            "#pk": "pk",
            "#sk": "sk",
            "#entity_type": "entity_type",
            "#run_id": "run_id",
            "#generated_at": "generated_at",
            "#window_start": "window_start",
            "#window_end": "window_end",
            "#summary": "summary",
        }
        projected_attributes = [
            "#pk",
            "#sk",
            "#entity_type",
            "#run_id",
            "#generated_at",
            "#window_start",
            "#window_end",
            "#summary",
        ]
        if include_raw_messages:
            attribute_names["#raw_messages"] = "raw_messages"
            projected_attributes.append("#raw_messages")

        items: list[dict[str, Any]] = []
        query_kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(RUN_PK) & Key("sk").begins_with("digest#"),
            "ScanIndexForward": True,
            "ProjectionExpression": ", ".join(projected_attributes),
            "ExpressionAttributeNames": attribute_names,
        }

        while True:
            response = self.table.query(**query_kwargs)
            items.extend(
                item
                for item in response.get("Items", [])
                if isinstance(item, dict) and item.get("entity_type") == "digest_run"
            )
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            query_kwargs["ExclusiveStartKey"] = last_key

        return items

    def get_recent_conversation(self, chat_id: str) -> list[dict[str, str]]:
        response = self.table.get_item(
            Key={"pk": f"{CONVERSATION_PK_PREFIX}{chat_id}", "sk": CONVERSATION_SK}
        )
        item = response.get("Item") or {}
        messages = item.get("recent_messages", [])
        if not isinstance(messages, list):
            return []
        return [
            {"role": str(message.get("role", "")), "text": str(message.get("text", ""))}
            for message in messages
            if isinstance(message, dict) and message.get("role") and message.get("text")
        ]

    def append_conversation_turn(
        self,
        *,
        chat_id: str,
        question: str,
        answer: str,
        max_messages: int = 10,
    ) -> list[dict[str, str]]:
        recent_messages = self.get_recent_conversation(chat_id)
        recent_messages.extend(
            [
                {"role": "user", "text": question},
                {"role": "assistant", "text": answer},
            ]
        )
        recent_messages = recent_messages[-max_messages:]
        self.table.put_item(
            Item={
                "pk": f"{CONVERSATION_PK_PREFIX}{chat_id}",
                "sk": CONVERSATION_SK,
                "entity_type": "conversation",
                "chat_id": chat_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "recent_messages": recent_messages,
            }
        )
        return recent_messages
