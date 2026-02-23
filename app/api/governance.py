from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import (
    get_ai_service,
    get_observability,
    get_rag_service,
    require_roles,
)
from app.db.models import Role, User
from app.db.session import get_db
from app.schemas.governance import (
    GovernanceDecisionResponse,
    ReviewARequest,
    ReviewBRequest,
)
from app.services.gen_ai_service import GenAIService
from app.services import governance_service
from app.services.observability_service import ObservabilityService
from app.services.rag_service import RagService

router = APIRouter(prefix="/governance", tags=["governance"])


@router.post(
    "/creative-assets/{asset_id}/review-a", response_model=GovernanceDecisionResponse
)
def review_by_approver_a(
    asset_id: str,
    payload: ReviewARequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.APPROVER_A)),
) -> GovernanceDecisionResponse:
    return governance_service.review_by_approver_a(
        asset_id=asset_id, payload=payload, db=db, current_user=current_user
    )


@router.post(
    "/creative-assets/{asset_id}/audit-image", response_model=GovernanceDecisionResponse
)
def audit_with_image(
    asset_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.APPROVER_B)),
    ai_service: GenAIService = Depends(get_ai_service),
    rag_service: RagService = Depends(get_rag_service),
    observability: ObservabilityService = Depends(get_observability),
) -> GovernanceDecisionResponse:
    return governance_service.audit_with_image(
        asset_id=asset_id,
        file=file,
        db=db,
        current_user=current_user,
        ai_service=ai_service,
        rag_service=rag_service,
        observability=observability,
    )


@router.post(
    "/creative-assets/{asset_id}/review-b", response_model=GovernanceDecisionResponse
)
def review_by_approver_b(
    asset_id: str,
    payload: ReviewBRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.APPROVER_B)),
) -> GovernanceDecisionResponse:
    return governance_service.review_by_approver_b(
        asset_id=asset_id,
        payload=payload,
        db=db,
        current_user=current_user,
    )
