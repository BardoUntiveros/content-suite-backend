from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import AuditVerdict, WorkflowStatus


class ReviewARequest(BaseModel):
    decision: WorkflowStatus
    rejection_reason: str | None = Field(default=None, max_length=1000)


class ReviewBRequest(BaseModel):
    decision: WorkflowStatus
    rejection_reason: str | None = Field(default=None, max_length=1000)


class AuditResponse(BaseModel):
    id: str
    asset_id: str
    approver_id: str
    image_path: str
    verdict: AuditVerdict
    explanation: str
    confidence: float
    created_at: datetime


class GovernanceDecisionResponse(BaseModel):
    asset_id: str
    workflow_status: WorkflowStatus
    rejection_reason: str | None
    audit: AuditResponse | None = None
