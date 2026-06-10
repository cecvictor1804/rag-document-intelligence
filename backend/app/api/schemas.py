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
    # Business segment for direct line-item lookups (None = consolidated).
    segment: str | None = None
    # Convert currency-unit results to this ISO code (annotated, never silent).
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class ConvertedValue(BaseModel):
    """An FX-converted rendition of the result — the applied rate and its
    as-of date are part of the answer, so conversion is never invisible."""

    currency: str
    value: str  # Decimal as string
    rate: str
    rate_date: str | None


class BasisAlternative(BaseModel):
    """The same line item/period on the other basis (GAAP ↔ non-GAAP)."""

    basis: str
    value: str
    label: str  # the as-reported label, e.g. "Adjusted operating income"


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
    converted: ConvertedValue | None = None
    non_gaap_alternative: BasisAlternative | None = None
    disclaimer: str


class ReviewIssue(BaseModel):
    id: int
    doc_id: str
    entity_id: str
    check: str
    detail: str
    expected: str | None
    actual: str | None
    created_at: str


class ReviewResponse(BaseModel):
    issues: list[ReviewIssue]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "down"]
