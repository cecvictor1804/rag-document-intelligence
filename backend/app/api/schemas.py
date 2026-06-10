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


class MetricRequest(BaseModel):
    """A deterministic figure request: a canonical line item ("revenue"), a
    registered ratio ("gross_margin"), or a YoY growth ("revenue_yoy")."""

    entity: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    fiscal_year: int = Field(ge=1900, le=2200)
    fiscal_quarter: Literal[1, 2, 3, 4] | None = None
    basis: Literal["gaap", "non_gaap"] = "gaap"


class FactProvenance(BaseModel):
    """Where one input figure came from — down to the table cell."""

    line_item: str | None
    line_item_as_reported: str
    value: str  # Decimal serialized as string (exactness over float convenience)
    value_as_reported: str
    scale: int
    currency: str
    unit: str
    basis: str
    segment: str | None
    period: str
    doc_id: str
    page: int | None
    table_index: int | None
    row: int | None
    col: int | None


class MetricResponse(BaseModel):
    metric: str
    value: str  # Decimal as string
    unit: str
    currency: str | None
    period: str
    formula: str
    inputs: list[FactProvenance]
    disclaimer: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "down"]
