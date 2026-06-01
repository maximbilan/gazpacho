from __future__ import annotations

from src.common.storage import DigestStorage, LATEST_SK, RUN_PK
from src.reader.models import DownloadedImage, NormalizedMessage


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    def put_item(self, *, Item):
        self.items[(Item["pk"], Item["sk"])] = Item

    def get_item(self, *, Key):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": item} if item else {}


def test_store_digest_run_writes_run_and_latest_items() -> None:
    table = FakeTable()
    storage = DigestStorage("ignored", table=table)

    stored = storage.store_digest_run(
        summary="Дайджест",
        raw_messages=[
            NormalizedMessage(
                chat_name="School",
                chat_ref="@school",
                message_id=1,
                sender="Teacher",
                date_iso="2026-06-01T08:00:00+00:00",
                text="Traer autorización.",
            )
        ],
        images=[
            DownloadedImage(
                chat_name="School",
                chat_ref="@school",
                message_id=2,
                path="/tmp/notice.jpg",
                mime_type="image/jpeg",
            )
        ],
        lookback_days=7,
    )

    run_item = table.items[(RUN_PK, stored.run_id)]
    latest_item = table.items[(RUN_PK, LATEST_SK)]
    assert run_item["summary"] == "Дайджест"
    assert run_item["message_count"] == 1
    assert run_item["image_count"] == 1
    assert "path" not in run_item["images"][0]
    assert latest_item["run_id"] == stored.run_id
    assert storage.get_latest_digest_run()["summary"] == "Дайджест"
