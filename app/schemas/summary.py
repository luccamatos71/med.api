from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GlossaryItem(BaseModel):
    term: str
    definition: str


class SummarySection(BaseModel):
    heading: str
    bullets: list[str] = Field(default_factory=list)


class SummaryContent(BaseModel):
    """Structured summary payload (stored as summary_json)."""

    title: str
    tldr: str
    key_points: list[str] = Field(default_factory=list)
    sections: list[SummarySection] = Field(default_factory=list)
    glossary: list[GlossaryItem] = Field(default_factory=list)
    clinical_pearls: list[str] = Field(default_factory=list)
    mindmap_markdown: str = ""


class SummaryResponse(BaseModel):
    id: UUID
    material_id: UUID
    summary: SummaryContent
    created_at: datetime
    updated_at: datetime
