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

    def query(self, **kwargs):
        projection = kwargs.get("ProjectionExpression", "")
        attribute_names = kwargs.get("ExpressionAttributeNames", {})
        projected_names = [
            attribute_names.get(name.strip(), name.strip())
            for name in projection.split(",")
            if name.strip()
        ]
        items = [
            item
            for (pk, sk), item in sorted(self.items.items())
            if pk == RUN_PK and sk.startswith("digest#")
        ]
        if projected_names:
            items = [
                {name: item[name] for name in projected_names if name in item}
                for item in items
            ]
        return {"Items": items}


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
        window_start="2026-06-01T08:00:00+00:00",
        window_end="2026-06-02T08:00:00+00:00",
    )

    run_item = table.items[(RUN_PK, stored.run_id)]
    latest_item = table.items[(RUN_PK, LATEST_SK)]
    assert run_item["summary"] == "Дайджест"
    assert run_item["window_start"] == "2026-06-01T08:00:00+00:00"
    assert run_item["window_end"] == "2026-06-02T08:00:00+00:00"
    assert run_item["message_count"] == 1
    assert run_item["image_count"] == 1
    assert "path" not in run_item["images"][0]
    assert latest_item["run_id"] == stored.run_id
    assert storage.get_latest_digest_run()["summary"] == "Дайджест"


def test_get_digest_runs_can_omit_raw_messages() -> None:
    table = FakeTable()
    table.put_item(
        Item={
            "pk": RUN_PK,
            "sk": "digest#2026-06-01T08:00:00+00:00",
            "entity_type": "digest_run",
            "run_id": "digest#2026-06-01T08:00:00+00:00",
            "generated_at": "2026-06-01T08:00:00+00:00",
            "summary": "Перший дайджест",
            "raw_messages": [{"text": "raw"}],
        }
    )
    storage = DigestStorage("ignored", table=table)

    runs = storage.get_digest_runs(include_raw_messages=False)

    assert runs == [
        {
            "pk": RUN_PK,
            "sk": "digest#2026-06-01T08:00:00+00:00",
            "entity_type": "digest_run",
            "run_id": "digest#2026-06-01T08:00:00+00:00",
            "generated_at": "2026-06-01T08:00:00+00:00",
            "summary": "Перший дайджест",
        }
    ]


def test_append_conversation_turn_caps_recent_messages() -> None:
    table = FakeTable()
    storage = DigestStorage("ignored", table=table)

    storage.append_conversation_turn(chat_id="123", question="one", answer="two", max_messages=3)
    messages = storage.append_conversation_turn(
        chat_id="123",
        question="three",
        answer="four",
        max_messages=3,
    )

    assert messages == [
        {"role": "assistant", "text": "two"},
        {"role": "user", "text": "three"},
        {"role": "assistant", "text": "four"},
    ]
    assert storage.get_recent_conversation("123") == messages
