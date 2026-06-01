from __future__ import annotations

from pydantic import BaseModel, Field


class NormalizedMessage(BaseModel):
    chat_name: str
    chat_ref: str
    message_id: int
    sender: str | None = None
    date_iso: str
    text: str = ""
    has_media: bool = False
    media_kind: str | None = None


class DownloadedImage(BaseModel):
    chat_name: str
    chat_ref: str
    message_id: int
    path: str
    mime_type: str | None = None


class ReaderResult(BaseModel):
    messages: list[NormalizedMessage] = Field(default_factory=list)
    images: list[DownloadedImage] = Field(default_factory=list)

