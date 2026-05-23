from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class MaterialCreate(BaseModel):
    topic_id: UUID
    title: str
    type: Literal["text", "note"]
    content: str


class MaterialResponse(BaseModel):
    id: UUID
    topic_id: UUID
    user_id: UUID
    type: str
    title: str
    content: Optional[str] = None
    file_key: Optional[str] = None
    file_size_bytes: Optional[int] = None
    processing_status: str
    processing_error: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReadPositionUpdate(BaseModel):
    position_data: Dict[str, Any]


class ReadPositionResponse(BaseModel):
    id: UUID
    material_id: UUID
    user_id: UUID
    position_data: Dict[str, Any]
    updated_at: datetime

    model_config = {"from_attributes": True}
