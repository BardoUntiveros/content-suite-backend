from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import (
    AssetType,
    AuditVerdict,
    JourneyEventType,
    Role,
    WorkflowStatus,
)


class CreativeGenerateRequest(BaseModel):
    manual_id: str
    asset_type: AssetType
    brief: str = Field(min_length=8, max_length=2000)


class CreativeAssetResponse(BaseModel):
    id: str
    manual_id: str
    created_by_id: str
    asset_type: AssetType
    brief: str
    generated_text: str
    workflow_status: WorkflowStatus
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime


class CreativeGenerateResponse(BaseModel):
    asset: CreativeAssetResponse
    rag_context: list[str]


class CreativeAssetListResponse(BaseModel):
    items: list[CreativeAssetResponse]


class CreativeAssetHistoryItemResponse(CreativeAssetResponse):
    manual_product_name: str
    manual_markdown: str
    latest_audit_verdict: AuditVerdict | None
    latest_audit_explanation: str | None
    latest_audit_confidence: float | None
    latest_audit_at: datetime | None


class CreativeAssetHistoryListResponse(BaseModel):
    items: list[CreativeAssetHistoryItemResponse]


class JourneyEventResponse(BaseModel):
    id: str
    event_type: JourneyEventType
    from_status: WorkflowStatus | None
    to_status: WorkflowStatus
    note: str | None
    actor_id: str | None
    actor_name: str | None
    actor_role: Role | None
    payload: dict | None
    created_at: datetime


class CreativeAssetJourneyResponse(BaseModel):
    asset: CreativeAssetHistoryItemResponse
    events: list[JourneyEventResponse]
