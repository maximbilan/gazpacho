from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import boto3

from src.reader.models import DownloadedImage, NormalizedMessage


RUN_PK = "RUN"
LATEST_SK = "LATEST"


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
