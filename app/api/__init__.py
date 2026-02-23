from app.api.auth import router as auth_router
from app.api.brand_manuals import router as brand_manuals_router
from app.api.creative_assets import router as creative_assets_router
from app.api.governance import router as governance_router

__all__ = [
    "auth_router",
    "brand_manuals_router",
    "creative_assets_router",
    "governance_router",
]
