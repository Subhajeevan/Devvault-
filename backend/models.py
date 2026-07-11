"""Pydantic request/response schemas for the API layer."""
from pydantic import BaseModel, Field


class UrlIn(BaseModel):
    url: str = Field(..., description="A website URL to ingest.")


class NoteIn(BaseModel):
    title: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)


class AskIn(BaseModel):
    question: str = Field(..., min_length=1)
    source_ids: list[str] | None = Field(
        default=None,
        description="Optional subset of source IDs to restrict retrieval to.",
    )


class FlashcardsIn(BaseModel):
    count: int = Field(default=8, ge=1, le=30)
