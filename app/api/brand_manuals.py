from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    get_ai_service,
    get_current_user,
    get_observability,
    get_rag_service,
    require_roles,
)
from app.db.models import Role, User
from app.db.session import get_db
from app.schemas.brand_manuals import (
    BrandManualCreateRequest,
    BrandManualListResponse,
    BrandManualResponse,
)
from app.services import brand_manuals_service
from app.services.gen_ai_service import GenAIService
from app.services.observability_service import ObservabilityService
from app.services.rag_service import RagService

router = APIRouter(prefix="/brand-manuals", tags=["brand-manuals"])


@router.post("", response_model=BrandManualResponse)
def create_brand_manual(
    payload: BrandManualCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.CREATOR)),
    ai_service: GenAIService = Depends(get_ai_service),
    rag_service: RagService = Depends(get_rag_service),
    observability: ObservabilityService = Depends(get_observability),
) -> BrandManualResponse:
    return brand_manuals_service.create_brand_manual(
        payload=payload,
        db=db,
        current_user=current_user,
        ai_service=ai_service,
        rag_service=rag_service,
        observability=observability,
    )


@router.get("", response_model=BrandManualListResponse)
def list_brand_manuals(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> BrandManualListResponse:
    return brand_manuals_service.list_brand_manuals(db=db)
