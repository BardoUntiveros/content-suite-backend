from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    get_ai_service,
    get_current_user,
    get_observability,
    get_rag_service,
    require_roles,
)
from app.db.models import AssetType, Role, User, WorkflowStatus
from app.db.session import get_db
from app.schemas.creative_assets import (
    CreativeAssetHistoryListResponse,
    CreativeAssetJourneyResponse,
    CreativeAssetListResponse,
    CreativeGenerateRequest,
    CreativeGenerateResponse,
)
from app.services import creative_assets_service
from app.services.gen_ai_service import GenAIService
from app.services.observability_service import ObservabilityService
from app.services.rag_service import RagService

router = APIRouter(prefix="/creative-assets", tags=["creative-assets"])


@router.post("", response_model=CreativeGenerateResponse)
def generate_asset(
    payload: CreativeGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.CREATOR)),
    ai_service: GenAIService = Depends(get_ai_service),
    rag_service: RagService = Depends(get_rag_service),
    observability: ObservabilityService = Depends(get_observability),
) -> CreativeGenerateResponse:
    return creative_assets_service.generate_asset(
        payload=payload,
        db=db,
        current_user=current_user,
        ai_service=ai_service,
        rag_service=rag_service,
        observability=observability,
    )


@router.get("", response_model=CreativeAssetListResponse)
def list_assets(
    status_filter: WorkflowStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CreativeAssetListResponse:
    return creative_assets_service.list_assets(
        status_filter=status_filter, db=db, current_user=current_user
    )


@router.get("/history", response_model=CreativeAssetHistoryListResponse)
def list_assets_history(
    asset_type_filter: AssetType | None = Query(default=None, alias="asset_type"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> CreativeAssetHistoryListResponse:
    return creative_assets_service.list_assets_history(
        asset_type_filter=asset_type_filter, db=db
    )


@router.get("/{asset_id}/journey", response_model=CreativeAssetJourneyResponse)
def get_asset_journey(
    asset_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> CreativeAssetJourneyResponse:
    return creative_assets_service.get_asset_journey(asset_id=asset_id, db=db)
