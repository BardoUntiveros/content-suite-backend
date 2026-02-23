from datetime import datetime

from pydantic import BaseModel, Field


class BrandManualCreateRequest(BaseModel):
    product_name: str = Field(min_length=3, max_length=200)
    tone: str = Field(min_length=3, max_length=200)
    audience: str = Field(min_length=3, max_length=200)
    extra_context: str = Field(default="", max_length=1500)


class BrandManualResponse(BaseModel):
    id: str
    product_name: str
    tone: str
    audience: str
    manual_markdown: str
    created_by_id: str
    created_at: datetime


class BrandManualListResponse(BaseModel):
    items: list[BrandManualResponse]
