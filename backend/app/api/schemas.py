"""Request/response models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.models import Turn


class TurnIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str

    def to_turn(self) -> Turn:
        return Turn(role=self.role, content=self.content)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    history: list[TurnIn] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    query: str = Field(min_length=1)
    answer: str | None = None
    rating: Literal[-1, 1]
    comment: str | None = None
    chunk_ids: list[int] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    id: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "down"]
